import asyncio
import copy
import hashlib
import logging
import random
import time
from uuid import uuid4
from .grading import grade
from .history import now, public_result
from .pricing import load_local_rates, resolve_cost

log = logging.getLogger(__name__)

class Runner:
    def __init__(self, client, history, recordings):
        self.client, self.history, self.recordings = client, history, recordings
        self.runs, self.jobs = {}, set()

    def start(self, task, models, prompt, blind, source=None, rates=None):
        if source:
            reels = copy.deepcopy(source['reels'])
        elif task.get('variants'):
            reels = [{'reel_id': chr(65+i), 'model': models[0], 'variant': v['label'], 'prompt': v['prompt']} for i, v in enumerate(task['variants'])]
        else:
            models = list(models)
            if blind:
                random.SystemRandom().shuffle(models)
            reels = [{'reel_id': chr(65+i), 'model': m, 'prompt': prompt} for i, m in enumerate(models)]
        run = {'id': str(uuid4()), 'created_at': now(), 'task_id': task['id'], 'blind': blind, 'revealed': not blind,
               'recorded': bool(source), 'reels': reels, 'results': [], 'events': [], 'complete': False}
        self.runs[run['id']] = run
        job = asyncio.create_task(self._execute(run, task, source, rates or {}))
        self.jobs.add(job)
        job.add_done_callback(self.jobs.discard)
        return run

    def emit(self, run, event, data, start):
        run['events'].append({'event': event, 'data': copy.deepcopy(data), 'at': time.monotonic() - start})

    async def _execute(self, run, task, source, rates):
        start = time.monotonic()
        try:
            if source:
                for event in source['events']:
                    if event['event'] == 'run_done':
                        continue
                    await asyncio.sleep(max(0, event['at'] - (time.monotonic() - start)))
                    data = copy.deepcopy(event['data'])
                    if event['event'] == 'reel_done':
                        latest = next((r for r in source['results'] if r.get('reel_id') == data.get('reel_id')), None)
                        if latest is not None:
                            data['result'] = copy.deepcopy(latest)
                    self.emit(run, event['event'], data, start)
                run['results'] = copy.deepcopy(source['results'])
            else:
                await asyncio.gather(*(self._reel(run, task, reel, rates, start) for reel in run['reels']))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning('Run failed: %s', type(exc).__name__)
            self.emit(run, 'error', {'message': 'Run failed. Check gateway availability.'}, start)
        finally:
            run['complete'] = True
            run['wall_ms'] = source.get('wall_ms') if source else (time.monotonic() - start) * 1000
            self.emit(run, 'run_done', {'run_id': run['id'], 'recorded': run['recorded'], 'wall_ms': run['wall_ms']}, start)
            self.history.save(run)
            self.recordings.capture(run)

    async def _reel(self, run, task, reel, rates, start):
        reel_id, model = reel['reel_id'], reel['model']
        self.emit(run, 'reel_start', {'reel_id': reel_id}, start)
        try:
            found = False
            async for event in self.client.stream(model, reel['prompt'], task['max_tokens']):
                if event['type'] == 'token':
                    self.emit(run, 'token', {'reel_id': reel_id, 'text': event['text']}, start)
                elif event['type'] == 'result':
                    found = True
                    result = event['result']
                    result['reel_id'] = reel_id
                    result['prompt_id'] = hashlib.sha256(reel['prompt'].encode()).hexdigest()[:12]
                    result['cost'] = resolve_cost(result.get('usage', {}), result.get('headers', {}), rates.get(model), load_local_rates().get(model))
                    result['grade'] = grade(task, result['text'], 'length' if result.get('truncated') else result.get('finish_reason'))
                    if reel.get('variant'):
                        result['variant'] = reel['variant']
                    run['results'].append(result)
                    self.emit(run, 'reel_done', {'reel_id': reel_id, 'result': result}, start)
            if not found:
                raise RuntimeError('Missing result')
        except Exception as exc:
            log.warning('Reel failed: %s', type(exc).__name__)
            message = 'Model request failed. Check gateway availability or server logs.'
            run['results'].append({'reel_id': reel_id, 'model': model, 'text': '', 'error': message,
                                   'grade': {'status': 'ungraded', 'passed': None, 'checks': [], 'summary': 'Request failed.'}})
            self.emit(run, 'error', {'reel_id': reel_id, 'message': message}, start)

    async def events(self, run, after=-1):
        index = after + 1
        while True:
            while index < len(run['events']):
                item = run['events'][index]
                data = copy.deepcopy(item['data'])
                if item['event'] == 'reel_done':
                    data['result'] = public_result(data['result'], run['blind'] and not run['revealed'])
                if item['event'] == 'run_done' and run['blind'] and not run['revealed']:
                    data.pop('wall_ms', None)
                yield index, item['event'], data
                index += 1
            if run['complete']:
                return
            await asyncio.sleep(0.04)

    async def close(self):
        jobs = list(self.jobs)
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
