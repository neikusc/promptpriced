import asyncio
import importlib
import json
import httpx
import pytest
from promptpriced.config import Settings
from promptpriced.litellm_client import LiteLLMClient
from promptpriced.recorded import Recordings
from promptpriced.history import History, variance_groups

module=importlib.import_module('promptpriced.app')
ANSWER={'claim_id':'FN-2048','policyholder':'Avery Morgan','loss_date':'2026-03-14','reported_date':'2026-03-16',
        'cause':'water damage','estimated_loss_usd':18450.75,'deductible_usd':1000,'injuries':0,'police_report_id':None}

@pytest.fixture
async def api(tmp_path,monkeypatch):
    settings=Settings(database_path=tmp_path/'runs.db',recordings_path=tmp_path/'recorded.json',litellm_api_base='https://gateway.test/v1')
    monkeypatch.setattr(module,'settings',settings)
    async with module.app.router.lifespan_context(module.app):
        await module.app.state.client.close()
        def handle(req):
            if req.url.path.endswith('/models'):
                return httpx.Response(200,json={'data':[{'id':'alpha'},{'id':'beta'},{'id':'broken'}]})
            if req.url.path.endswith('/model/info'):
                return httpx.Response(200,json={'data':[{'model_name':m,'model_info':{'mode':'chat','input_cost_per_token':.000001,'output_cost_per_token':.000002}} for m in ('alpha','beta','broken')]})
            body=json.loads(req.content)
            if body['model']=='broken':return httpx.Response(500,text='secret API key upstream body')
            text=json.dumps(ANSWER)
            packets=[{'choices':[{'delta':{'content':text}}]},{'choices':[{'delta':{},'finish_reason':'stop'}]},
                     {'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':50}}]
            return httpx.Response(200,text=''.join('data: '+json.dumps(p)+'\n\n' for p in packets)+'data: [DONE]\n\n',headers={'x-litellm-response-cost':'.0003'})
        module.app.state.client=LiteLLMClient(settings,httpx.MockTransport(handle))
        module.app.state.runner.client=module.app.state.client
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test') as c:
            yield c

async def start(c,**kwargs):
    body={'task_id':'extraction','models':['alpha','beta'],'prompt':module.get_task('extraction')['prompt'],'blind':True,**kwargs}
    response=await c.post('/api/run',json=body)
    assert response.status_code==200,response.text
    rid=response.json()['run_id']
    await asyncio.gather(*list(module.app.state.runner.jobs))
    return rid,response.json()

async def test_task_secrets_and_validation(api):
    response=await api.get('/api/tasks');assert response.status_code==200
    assert all(not {'grading', 'answer_key', 'rubric'} & t.keys() for t in response.json())
    assert '"expected"' not in response.text
    for patch,code in [({'task_id':'missing'},404),({'models':[]},422),({'models':['alpha','alpha']},422),
                       ({'models':['unknown']},422),({'prompt':''},422),({'models':['alpha']*4},422),
                       ({'mode':'recorded','recorded_run_id':'missing'},404)]:
        r=await api.post('/api/run',json={'task_id':'extraction','models':['alpha'],'prompt':'test',**patch})
        assert r.status_code==code
    r=await api.post('/api/run',json={'task_id':'extraction','prompt':'SECRET-SHOULD-NOT-ECHO','models':True})
    assert 'SECRET-SHOULD-NOT-ECHO' not in r.text
    assert (await api.get('/')).status_code==200
    assert (await api.get('/static/app.js')).status_code==200

async def test_blind_events_history_reveal_recording_replay(api):
    rid,body=await start(api)
    assert all('model' not in r for r in body['reels'])
    events=await api.get(f'/api/run/{rid}/events')
    assert events.status_code==200 and 'run_done' in events.text
    for line in events.text.splitlines():
        if not line.startswith('data:'):continue
        packet=json.loads(line[5:])
        if 'result' in packet:
            assert not {'model','cost','usage','total_ms','ttft_ms'} & packet['result'].keys()
    history=(await api.get('/api/history')).json()
    assert not history['groups'] and 'reels' not in history['runs'][0]
    assert all('model' not in r for r in history['runs'][0]['results'])
    reveal=(await api.post(f'/api/run/{rid}/reveal')).json()
    assert len(reveal['results'])==2 and all(r['grade']['passed'] for r in reveal['results'])
    assert {r['model'] for r in reveal['results']}=={'alpha','beta'}
    assert len((await api.get('/api/recordings')).json())==1
    assert len((await api.get('/api/history')).json()['groups'])==2
    async def no_network(*args,**kwargs):raise AssertionError('Replay used network')
    module.app.state.runner.client.stream=no_network
    replay,_=await start(api,mode='recorded',models=[],recorded_run_id=rid)
    assert module.app.state.runner.runs[replay]['recorded']
    replay_result=(await api.post(f'/api/run/{replay}/reveal')).json()
    assert replay_result['results'][0]['text']==reveal['results'][0]['text']
    assert all(g['count']==1 for g in (await api.get('/api/history')).json()['groups'])

async def test_isolated_error_and_sse_header(api):
    rid,_=await start(api,models=['alpha','broken'],blind=False)
    run=module.app.state.runner.runs[rid]
    assert len(run['results'])==2 and sum('error' in r for r in run['results'])==1
    events=await api.get(f'/api/run/{rid}/events')
    assert 'secret API key' not in events.text
    assert not module.app.state.recordings.all()
    assert (await api.get(f'/api/run/{rid}/events',headers={'Last-Event-ID':'bad'})).status_code==400
    resumed=await api.get(f'/api/run/{rid}/events',headers={'Last-Event-ID':'999'})
    assert resumed.text==''

async def test_variant_and_override_persistence(api):
    rid,_=await start(api,task_id='prompt_bloat',models=['alpha'],prompt='ignored',blind=False)
    run=module.app.state.runner.runs[rid]
    assert len(run['reels'])==2 and {r['model'] for r in run['reels']}=={'alpha'}
    assert {r['variant'] for r in run['reels']}=={'Bloated instructions','Lean instructions'}
    rid,_=await start(api,models=['alpha'],blind=False)
    path=f'/api/run/{rid}/grade'
    body={'reel_id':'A','check_id':'claim_id','passed':False}
    assert (await api.post(path,json=body)).json()['grade']['status']=='fail'
    body['passed']=True
    assert (await api.post(path,json=body)).json()['grade']['status']=='pass'
    saved=module.app.state.history.get(rid)
    check=next(c for c in saved['results'][0]['grade']['checks'] if c['id']=='claim_id')
    assert check['original_passed'] is True and check['overridden']
    module.app.state.runner.runs.clear()
    assert (await api.post(path,json=body)).json()['grade']['passed']

async def test_conflicts_and_workflow_validation(api):
    rid,_=await start(api)
    run=module.app.state.runner.runs[rid];run['complete']=False
    assert (await api.post(f'/api/run/{rid}/reveal')).status_code==409
    assert (await api.post(f'/api/run/{rid}/grade',json={'reel_id':'A','check_id':'json','passed':True})).status_code==409
    run['complete']=True;run['results'][0]['grade']['status']='truncated'
    assert (await api.post(f'/api/run/{rid}/grade',json={'reel_id':run['results'][0]['reel_id'],'check_id':'json','passed':True})).status_code==409
    wf=(await api.get('/api/workflow')).json();assert wf['title']=='Fix the bill'
    cfg=wf['as_built'];cfg['steps']['extract'].pop('calls')
    assert (await api.post('/api/workflow/estimate',json=cfg)).status_code==422

async def test_offline_workflow(api):
    await module.app.state.client.close()
    module.app.state.models=[]
    async def fail():raise module.GatewayError('Safe error')
    module.app.state.client.discover_models=fail
    r=await api.get('/api/models');assert r.status_code==502 and 'recorded mode' in r.text
    r=await api.get('/api/workflow');assert r.status_code==200 and not r.json()['estimate']['available']


def test_history_variance_and_recording_guards(tmp_path):
    h=History(tmp_path/'db');r=Recordings(tmp_path/'rec.json')
    run={'id':'a','created_at':'2026-01-01','task_id':'x','blind':False,'revealed':True,'recorded':False,'complete':True,
         'reels':[{'model':'m'}],'results':[{'model':'m','cost':{'amount':None},'total_ms':10}]}
    h.save(run);run['created_at']='2026-01-02';h.save(run)
    assert len(h.list())==1 and h.get('a')['created_at']=='2026-01-02'
    assert variance_groups(h.list())[0]['priced_count']==0
    r.capture({**run,'complete':False});assert r.all()==[]
    r.capture({**run,'recorded':True});assert r.all()==[]
    r.capture(run);assert len(r.all())==1
    r.capture(run);assert len(r.all())==1
    h.close()

async def test_replay_uses_latest_presenter_override(api):
    rid,_=await start(api,models=['alpha'],blind=False)
    await api.post(f'/api/run/{rid}/grade',json={'reel_id':'A','check_id':'claim_id','passed':False})
    replay,_=await start(api,mode='recorded',models=[],recorded_run_id=rid,blind=False)
    stream=await api.get(f'/api/run/{replay}/events')
    packets=[json.loads(line[5:]) for line in stream.text.splitlines() if line.startswith('data:')]
    result=next(p['result'] for p in packets if 'result' in p)
    assert result['grade']['status']=='fail'
    assert next(c for c in result['grade']['checks'] if c['id']=='claim_id')['overridden']

async def test_mismatched_recording_and_exact_workflow(api):
    rid,_=await start(api,models=['alpha'],blind=False)
    r=await api.post('/api/run',json={'task_id':'leakage','mode':'recorded','recorded_run_id':rid})
    assert r.status_code==422
    wf=(await api.get('/api/workflow')).json();config=wf['as_built']
    config['steps']['extract']['bloated_prompt']=False
    response=await api.post('/api/workflow/estimate',json=config)
    assert response.status_code==200
    assert response.json()['steps'][0]['basis'] in {'measured','estimate'}
    assert response.json()['steps'][0]['per_call'] is not None
    config['steps'].pop('analysis')
    assert (await api.post('/api/workflow/estimate',json=config)).status_code==422


def test_recordings_keep_last_thirty_atomic(tmp_path):
    rec=Recordings(tmp_path/'fixtures/recorded.json')
    for i in range(35):
        rec.capture({'id':str(i),'created_at':f'2026-01-{i:02}','task_id':'x','complete':True,'revealed':True,
                     'recorded':False,'reels':[{'model':'m'}],'results':[{'text':'ok'}]})
    assert len(rec.all())==30 and rec.get('0') is None and rec.get('34')
    assert not rec.path.with_suffix('.tmp').exists()

async def test_wall_time_hidden_until_reveal_and_preserved_in_replay(api):
    rid,_=await start(api,models=['alpha'])
    run=module.app.state.runner.runs[rid]
    assert run['wall_ms'] > 0
    stream=await api.get(f'/api/run/{rid}/events')
    assert 'wall_ms' not in stream.text
    history=(await api.get('/api/history')).json()
    assert 'wall_ms' not in history['runs'][0]
    revealed=(await api.post(f'/api/run/{rid}/reveal')).json()
    assert revealed['wall_ms']==run['wall_ms']
    replay,_=await start(api,mode='recorded',models=[],recorded_run_id=rid,blind=False)
    assert module.app.state.runner.runs[replay]['wall_ms']==run['wall_ms']
    groups=(await api.get('/api/history')).json()['groups']
    assert groups[0]['timing']['n']==1

async def test_workflow_timing_without_prices_and_concurrency_validation(api):
    for task_id in ('extraction','leakage'):
        rid,_=await start(api,task_id=task_id,models=['alpha'],prompt=module.get_task(task_id)['prompt'],blind=False)
        run=module.app.state.runner.runs[rid]
        run['results'][0]['cost']={'amount':None,'tokens':None}
        module.app.state.history.save(run)
    wf=(await api.get('/api/workflow')).json()
    model=next(m for m in wf['models'] if m['id']=='alpha')
    assert set(model['timed_steps'])=={'extract','analysis'}
    cfg=wf['as_built']
    for step in cfg['steps'].values():step['model']='alpha'
    cfg['steps']['extract']['concurrency']=3
    r=await api.post('/api/workflow/estimate',json=cfg)
    assert r.status_code==200 and r.json()['timing']['available']
    assert not r.json()['available']
    for value in (0,201):
        cfg['steps']['extract']['concurrency']=value
        assert (await api.post('/api/workflow/estimate',json=cfg)).status_code==422
