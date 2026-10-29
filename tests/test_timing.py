import copy
import math
import pytest
from promptpriced.timing import timing_profile
from promptpriced.tasks import get_task, load_tasks
from promptpriced.workflow import Estimator, collect_timings, load_workflow, prompt_id
from promptpriced.history import public_run, variance_groups


def timing_run(**patch):
    task = get_task('extraction')
    result = {'model': 'timed-only', 'prompt_id': prompt_id(task['prompt']), 'total_ms': 2000,
              'ttft_ms': 500, 'cost': {'amount': None}, 'grade': {'status': 'pass', 'passed': True}}
    result.update(patch)
    return {'id': 'original', 'task_id': task['id'], 'complete': True, 'revealed': True,
            'blind': False, 'recorded': False, 'wall_ms': 2100, 'results': [result]}


def test_timing_statistics_and_invalid_values():
    p = timing_profile([{'total_ms': n, 'ttft_ms': n/2} for n in range(100, 2100, 100)])
    assert p['n'] == 20 and p['mean_ms'] == 1050 and p['median_ms'] == 1050
    assert p['p95_ms'] == 1900 and p['min_ms'] == 100 and p['max_ms'] == 2000
    assert p['mean_ttft_ms'] == 525 and p['ttft_n'] == 20
    assert timing_profile([{'total_ms': x} for x in (None, True, 0, -1, math.nan, math.inf)]) is None
    p = timing_profile([{'total_ms': 100, 'ttft_ms': 101}, {'total_ms': 200, 'ttft_ms': 0}])
    assert p['n'] == 2 and p['ttft_n'] == 1 and p['mean_ttft_ms'] == 0


def test_timing_evidence_needs_no_price_or_usage():
    run = timing_run()
    data = collect_timings([run], load_tasks())
    assert data['extraction'][None]['timed-only'][0]['total_ms'] == 2000
    for patch in ({'truncated': True}, {'error': 'failure'}, {'prompt_id': 'edited'},
                  {'total_ms': None}, {'total_ms': 0}, {'total_ms': True}, {'total_ms': math.inf}):
        assert not collect_timings([timing_run(**patch)], load_tasks())
    for patch in ({'complete': False}, {'revealed': False}, {'recorded': True}):
        assert not collect_timings([{**run, **patch}], load_tasks())
    variant = get_task('prompt_bloat')['variants'][0]
    run['task_id'] = 'prompt_bloat'
    run['results'][0]['prompt_id'] = prompt_id(variant['prompt'])
    assert collect_timings([run], load_tasks())['prompt_bloat']['bloated']


def make_estimator():
    timing = {'extraction': {None: {'m': [{'total_ms': 2000, 'ttft_ms': 500}]}},
              'leakage': {None: {'m': [{'total_ms': 4000, 'ttft_ms': 1000}]}}}
    return Estimator(load_workflow(), {}, {}, timing)


def config():
    c = copy.deepcopy(load_workflow()['as_built'])
    c['workflows_per_day'] = 100
    c['retry_rate'] = .2
    c['max_retries'] = 1
    c['steps']['extract'].update(model='m', calls=5, concurrency=2)
    c['steps']['analysis'].update(model='m', turns=3)
    return c


def test_time_independent_from_cost_and_concurrency_work_hours():
    e, c = make_estimator(), config()
    out = e.estimate(c)
    assert not out['available'] and out['monthly'] is None
    assert out['timing']['available']
    extract, agent = [s['timing'] for s in out['steps']]
    assert extract['waves'] == 3 and extract['concurrency'] == 2
    assert extract['per_call_seconds'] == 2
    assert extract['per_workflow_seconds'] == pytest.approx(3 * 2 * 1.2)
    assert agent['waves'] == 3 and agent['concurrency'] == 1
    expected = (3 * 2 + 3 * 4) * 1.2
    assert out['timing']['per_workflow_seconds'] == pytest.approx(expected)
    assert out['timing']['daily_model_call_hours'] == pytest.approx((5 * 2 + 3 * 4) * 1.2 * 100 / 3600)
    assert out['timing']['monthly_model_call_hours'] == pytest.approx(out['timing']['daily_model_call_hours'] * 30)
    c['steps']['extract']['concurrency'] = 200
    parallel = e.estimate(c)
    assert parallel['steps'][0]['timing']['waves'] == 1
    assert parallel['timing']['per_workflow_seconds'] < out['timing']['per_workflow_seconds']
    assert parallel['timing']['monthly_model_call_hours'] == out['timing']['monthly_model_call_hours']


def test_no_latency_price_scaling_or_unknown_model_fallback():
    e, c = make_estimator(), config()
    original = e.estimate(c)['timing']['per_workflow_seconds']
    c['steps']['extract']['bloated_prompt'] = False
    c['steps']['analysis'].update(context='window', window_turns=0)
    assert e.estimate(c)['timing']['per_workflow_seconds'] == original
    c['steps']['analysis']['model'] = 'unmeasured'
    out = e.estimate(c)
    assert not out['timing']['available'] and out['timing']['per_workflow_seconds'] is None
    assert out['steps'][0]['timing']['available']
    assert out['steps'][1]['timing']['per_call_seconds'] is None
    assert e.measured_timing('extraction', 'm')['n'] == 1


def test_blind_history_hides_wall_and_latency_variance():
    run = timing_run()
    assert public_run(run)['wall_ms'] == 2100
    group = variance_groups([run])[0]
    assert group['priced_count'] == 0 and group['timing']['n'] == 1
    assert group['timing']['median_ms'] == 2000
    run.update(blind=True, revealed=False)
    assert 'wall_ms' not in public_run(run)
    assert 'total_ms' not in public_run(run)['results'][0]
    assert not variance_groups([run])
