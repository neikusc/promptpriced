import copy
import json
from contextlib import asynccontextmanager
from typing import Literal
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .config import ROOT, settings
from .history import History, public_result, public_run, variance_groups
from .litellm_client import LiteLLMClient, GatewayError
from .orchestrator import Runner
from .pricing import load_local_rates, normalize_rates
from .recorded import Recordings
from .tasks import get_task, load_tasks
from .workflow import workflow_context

class RunRequest(BaseModel):
    task_id: str = Field(max_length=200)
    models: list[str] = Field(default_factory=list, max_length=3)
    prompt: str = Field(default='', max_length=50000)
    blind: bool = True
    mode: Literal['live', 'recorded'] = 'live'
    recorded_run_id: str | None = None

class GradeRequest(BaseModel):
    reel_id: str
    check_id: str
    passed: bool

class WorkflowStepConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str = Field(min_length=1, max_length=200)
    calls: int | None = Field(default=None, ge=1, le=200)
    concurrency: int = Field(default=1, ge=1, le=200)
    bloated_prompt: bool = False
    turns: int | None = Field(default=None, ge=1, le=50)
    context: Literal['full', 'window'] = 'full'
    window_turns: int = Field(default=2, ge=0, le=50)

class WorkflowConfig(BaseModel):
    workflows_per_day: int = Field(ge=1, le=10000000)
    retry_rate: float = Field(ge=0, le=0.9, allow_inf_nan=False)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    steps: dict[str, WorkflowStepConfig]

@asynccontextmanager
async def lifespan(app):
    app.state.client = LiteLLMClient(settings)
    app.state.history = History(settings.database_path)
    app.state.recordings = Recordings(settings.recordings_path)
    app.state.models = []
    app.state.runner = Runner(app.state.client, app.state.history, app.state.recordings)
    yield
    await app.state.runner.close()
    await app.state.client.close()
    app.state.history.close()

app = FastAPI(title='PromptPriced', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic's default errors echo input. Never reflect arbitrary payloads.
    return JSONResponse(status_code=422, content={'detail': 'Invalid request. Check field types, required fields, and allowed ranges.'})

@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response

@app.get('/')
def index():
    return FileResponse(ROOT / 'web/index.html')

async def discover():
    try:
        app.state.models = await app.state.client.discover_models()
    except GatewayError:
        raise HTTPException(502, 'Cannot discover gateway models. Check .env and gateway connectivity; recorded mode is still available.') from None
    return app.state.models

@app.get('/api/models')
async def models():
    result = await discover()
    defaults = yaml.safe_load((ROOT / 'config/models.yaml').read_text()).get('defaults', [])
    return {'models': result, 'defaults': defaults}

@app.get('/api/tasks')
def tasks():
    return [{k: v for k, v in t.items() if k not in {'grading', 'answer_key', 'rubric'}} for t in load_tasks()]

@app.get('/api/budget')
def budget():
    return app.state.client.budget

@app.get('/api/recordings')
def recordings():
    return app.state.recordings.summaries()

@app.post('/api/run')
async def run(body: RunRequest):
    try:
        task = get_task(body.task_id)
    except KeyError:
        raise HTTPException(404, 'Task not found.') from None
    source = None
    if body.mode == 'recorded':
        source = app.state.recordings.get(body.recorded_run_id)
        if source is None:
            raise HTTPException(404, 'Recording not found.')
        if source['task_id'] != task['id']:
            raise HTTPException(422, 'Recording belongs to another task.')
    else:
        if not body.models or len(set(body.models)) != len(body.models):
            raise HTTPException(422, 'Select one to three distinct models.')
        if not app.state.models:
            await discover()
        if any(m not in {m['id'] for m in app.state.models} for m in body.models):
            raise HTTPException(422, 'Model is not an available chat model.')
        if not task.get('variants') and not body.prompt.strip():
            raise HTTPException(422, 'Prompt must not be empty.')
    run = app.state.runner.start(task, body.models, body.prompt, body.blind, source,
                                 {m['id']: m['rates'] for m in app.state.models})
    return {'run_id': run['id'], 'recorded': run['recorded'], 'reels': [
        {'reel_id': r['reel_id'], 'label': 'Reel ' + r['reel_id'],
         **({'model': r['model']} if not body.blind else {}), **({'variant': r['variant']} if r.get('variant') else {})} for r in run['reels']]}

def find_run(run_id):
    run = app.state.runner.runs.get(run_id) or app.state.history.get(run_id)
    if run is None:
        raise HTTPException(404, 'Run not found.')
    return run

@app.get('/api/run/{run_id}/events')
async def events(run_id: str, request: Request):
    run = find_run(run_id)
    try:
        after = int(request.headers.get('last-event-id', '-1'))
    except ValueError:
        raise HTTPException(400, 'Invalid Last-Event-ID.') from None
    async def stream():
        async for index, name, data in app.state.runner.events(run, after):
            if await request.is_disconnected():
                return
            yield f'id: {index}\nevent: {name}\ndata: {json.dumps(data, allow_nan=False)}\n\n'
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.post('/api/run/{run_id}/reveal')
def reveal(run_id: str):
    run = find_run(run_id)
    if not run['complete']:
        raise HTTPException(409, 'Wait for the run to complete.')
    run['revealed'] = True
    app.state.history.save(run)
    if not run['recorded']:
        app.state.recordings.capture(run)
    return {'results': [public_result(r, False) for r in run['results']], 'wall_ms': run.get('wall_ms')}

@app.post('/api/run/{run_id}/grade')
def override_grade(run_id: str, body: GradeRequest):
    run = find_run(run_id)
    if not run['complete']:
        raise HTTPException(409, 'Wait for the run to complete.')
    result = next((r for r in run['results'] if r['reel_id'] == body.reel_id), None)
    if result is None:
        raise HTTPException(404, 'Reel not found.')
    grade = result['grade']
    if result.get('truncated') or grade['status'] in {'truncated', 'ungraded'}:
        raise HTTPException(409, 'This result cannot be overridden.')
    check = next((c for c in grade['checks'] if c['id'] == body.check_id), None)
    if check is None:
        raise HTTPException(404, 'Check not found.')
    check.setdefault('original_passed', check['passed'])
    check.update(passed=body.passed, overridden=True)
    grade['passed'] = all(c['passed'] for c in grade['checks'])
    grade['status'] = 'pass' if grade['passed'] else 'fail'
    grade['summary'] = 'Presenter-reviewed result (override recorded).'
    app.state.history.save(run)
    if not run['recorded']:
        app.state.recordings.capture(run)
    return public_result(result, run['blind'] and not run['revealed'])

@app.get('/api/history')
def history():
    runs = app.state.history.list()
    return {'runs': [public_run(r) for r in runs], 'groups': variance_groups(runs)}

def estimator():
    return workflow_context(app.state.history, app.state.recordings, app.state.models, load_local_rates())

@app.get('/api/workflow')
async def workflow():
    if not app.state.models:
        try:
            await discover()
        except HTTPException:
            pass
    est = estimator()
    config = copy.deepcopy(est.workflow['as_built'])
    measured_models = {m for variants in est.samples.values() for models in variants.values() for m in models}
    measured_models |= {m for variants in est.timings.values() for models in variants.values() for m in models}
    ids = {m['id'] for m in app.state.models} or set(est.rates)
    ids |= measured_models
    models = []
    for name in sorted(ids):
        r = normalize_rates(est.rates.get(name))
        models.append({'id': name, 'pricing_known': r['input_cost_per_token'] is not None and r['output_cost_per_token'] is not None,
                       'measured_steps': [s['id'] for s in est.workflow['steps'] if est.measured(s['task_id'], name)],
                       'timed_steps': [s['id'] for s in est.workflow['steps'] if est.measured_timing(s['task_id'], name)]})
    for step in est.workflow['steps']:
        if not config['steps'][step['id']]['model'] and models:
            config['steps'][step['id']]['model'] = models[-1]['id']
    return {**{k: est.workflow[k] for k in ('title', 'description', 'days_per_month', 'steps')},
            'as_built': config, 'models': models, 'fix': est.fixed_design(config),
            'rates_source': 'gateway' if app.state.models else 'local table', 'estimate': est.estimate(config)}

@app.post('/api/workflow/estimate')
def estimate(body: WorkflowConfig):
    est = estimator()
    required = {s['id'] for s in est.workflow['steps']}
    if set(body.steps) != required:
        raise HTTPException(422, 'Every workflow step must be present.')
    for step in est.workflow['steps']:
        if (body.steps[step['id']].turns if step['kind'] == 'agent' else body.steps[step['id']].calls) is None:
            raise HTTPException(422, 'Agent turns and batch calls are required.')
    return est.estimate(body.model_dump())
