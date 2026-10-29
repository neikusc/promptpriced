"""Evidence-based synthetic workload estimates; never extrapolate hidden runs."""
import copy
import hashlib
import math
from statistics import mean, median
import yaml
from .config import ROOT
from .pricing import normalize_rates, number
from .tasks import load_tasks
from .timing import timing_profile

MAX_RETRY_RATE = 0.9

def load_workflow():
    return yaml.safe_load((ROOT / 'config/workflow.yaml').read_text())

def prompt_id(prompt):
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]

def evidence_runs(history, recordings):
    runs = {r['id']: r for r in recordings.all()}
    runs.update({r['id']: r for r in history.list(10000) if not r.get('recorded')})
    return list(runs.values())

def collect_samples(runs, tasks):
    samples = {}
    task_map = {t['id']: t for t in tasks}
    for run in runs:
        task = task_map.get(run['task_id'])
        if not task or not run.get('complete') or not run.get('revealed'):
            continue
        prompts = {prompt_id(v['prompt']): v['id'] for v in task.get('variants', [])}
        if not prompts:
            prompts = {prompt_id(task['prompt']): None}
        for result in run['results']:
            cost, grade = result.get('cost', {}), result.get('grade', {})
            tokens = cost.get('tokens')
            if result.get('error') or result.get('truncated') or not tokens or number(cost.get('amount')) is None or result.get('prompt_id') not in prompts:
                continue
            variant = prompts[result['prompt_id']]
            sample = {'run_id': run['id'], 'cost': cost['amount'],
                      'passed': grade.get('passed') if grade.get('status') in ('pass', 'fail') else None,
                      **{k: tokens[k] for k in ('input', 'visible_output', 'reasoning')}}
            samples.setdefault(task['id'], {}).setdefault(variant, {}).setdefault(result['model'], []).append(sample)
    return samples

def profile(samples):
    if not samples:
        return None
    return {**{key: mean(s[key] for s in samples) for key in ('cost', 'input', 'visible_output', 'reasoning')},
            'n': len(samples), 'passed': sum(s['passed'] is True for s in samples),
            'graded': sum(s['passed'] is not None for s in samples)}

def collect_timings(runs, tasks):
    """Preset timing evidence does not require a price or token-usage report."""
    samples = {}
    task_map = {t['id']: t for t in tasks}
    for run in runs:
        task = task_map.get(run['task_id'])
        if not task or not run.get('complete') or not run.get('revealed') or run.get('recorded'):
            continue
        prompts = {prompt_id(v['prompt']): v['id'] for v in task.get('variants', [])}
        if not prompts:
            prompts = {prompt_id(task['prompt']): None}
        for result in run.get('results', []):
            total = number(result.get('total_ms'))
            if result.get('error') or result.get('truncated') or total is None or total <= 0 or result.get('prompt_id') not in prompts:
                continue
            sample = {'run_id': run['id'], 'total_ms': total, 'ttft_ms': result.get('ttft_ms')}
            samples.setdefault(task['id'], {}).setdefault(prompts[result['prompt_id']], {}).setdefault(result['model'], []).append(sample)
    return samples

def rated(rates, inp, out, reasoning=0):
    r = normalize_rates(rates)
    i, o, think = r['input_cost_per_token'], r['output_cost_per_token'], r['output_cost_per_reasoning_token']
    if i is None or o is None:
        return None
    result = inp*i + (out-reasoning)*o + reasoning*(think if think is not None else o)
    return result if math.isfinite(result) else None

def expected_attempts(r, k=None):
    r = max(0, min(MAX_RETRY_RATE, r))
    return 1 if r == 0 else (1-r**(k+1))/(1-r) if k is not None else 1/(1-r)

def carried_turns(turns, context, window=2):
    return turns*(turns-1)//2 if context == 'full' else sum(min(k, window) for k in range(turns))

class Estimator:
    def __init__(self, workflow, samples, rates, timings=None):
        self.workflow, self.samples, self.rates = workflow, samples, rates
        self.timings = timings or {}

    def measured_timing(self, task, model, variant=None):
        return timing_profile(self.timings.get(task, {}).get(variant, {}).get(model, []))

    def step_timing(self, step, config, attempts):
        model, task = config['model'], step['task_id']
        observed = self.measured_timing(task, model)
        calls = config['turns'] if step['kind'] == 'agent' else config['calls']
        concurrency = min(calls, config.get('concurrency', 1)) if step['kind'] == 'batch' else 1
        waves = math.ceil(calls / concurrency)
        notes = ['Estimate uses mean observed end-to-end call latency for this task and model.']
        # Price and token-count ratios do not establish prefill/decode throughput.
        if step['kind'] == 'batch' and config.get('bloated_prompt'):
            notes.append('Prompt bloat latency impact is not measured for this task; baseline call time is held constant.')
        if step['kind'] == 'agent':
            notes.append('Agent turns execute sequentially. Growing context, trimming and changing output lengths may change latency; their effect is not modeled.')
        elif concurrency > 1:
            notes.append('Parallel waves assume unchanged call latency and no gateway queueing or rate limits; retry stragglers are not modeled.')
        notes.append('Retries scale expected time by expected attempts; backoff and failed-attempt durations are not measured.')
        if observed is None:
            notes.insert(0, 'No valid timing measurements for this task and model. Run and reveal the preset; pricing is not required.')
        elif observed['n'] < 5:
            notes.append('Fewer than five observations: collect more live runs before relying on this estimate.')
        seconds = observed['mean_ms'] / 1000 if observed else None
        return {'available': observed is not None, 'basis': 'estimate from measurements' if observed else 'unavailable',
                'observed': observed, 'per_call_seconds': seconds,
                'per_workflow_seconds': seconds * waves * attempts if observed else None,
                'model_call_seconds': seconds * calls * attempts if observed else None,
                'concurrency': concurrency, 'waves': waves, 'notes': notes}

    def measured(self, task, model, variant=None):
        return profile(self.samples.get(task, {}).get(variant, {}).get(model, []))

    def median_profile(self, task):
        profiles = [profile(v) for v in self.samples.get(task, {}).get(None, {}).values() if v]
        if not profiles:
            return None
        return {'input': median(p['input'] for p in profiles), 'visible_output': median(p['visible_output'] for p in profiles), 'reasoning': 0}

    def call_cost(self, task, model, input_fn, calls=1):
        measured = self.measured(task, model)
        base = measured or self.median_profile(task)
        if base is None:
            return None, 'unavailable'
        inp = input_fn(base)
        if measured and calls == 1 and inp == base['input']:
            return base['cost'], 'measured'
        new = rated(self.rates.get(model), inp, (base['visible_output']+base['reasoning'])*calls, base['reasoning']*calls)
        if new is None:
            return None, 'unavailable'
        if measured:
            old = rated(self.rates.get(model), base['input'], base['visible_output']+base['reasoning'], base['reasoning'])
            if old is None or old == 0:
                return (0.0, 'measured') if old == 0 and base['cost'] == 0 and new == 0 else (None, 'unavailable')
            new = base['cost'] * new/old
        return new, 'measured' if measured else 'estimate'

    def quality(self, task, model, variant=None):
        p = self.measured(task, model, variant)
        return f"{p['passed']}/{p['graded']} passed" if p and p['graded'] else 'unverified'

    def prompt_bloat_tokens(self, step):
        evidence = self.samples.get(step.get('prompt_evidence'), {})
        bloated, lean = evidence.get('bloated', {}), evidence.get('lean', {})
        deltas = [profile(bloated[m])['input'] - profile(lean[m])['input'] for m in bloated.keys() & lean.keys()]
        lean_samples = [s for values in lean.values() for s in values]
        return (median(deltas) if deltas else None), profile(lean_samples)

    def _step(self, step, config):
        model, task = config['model'], step['task_id']
        base = self.measured(task, model) or self.median_profile(task)
        notes = []
        kind = step['kind']
        calls = config['turns'] if kind == 'agent' else config['calls']
        inp = None
        if kind == 'batch':
            delta, lean = self.prompt_bloat_tokens(step)
            med = self.median_profile(task)
            if config.get('bloated_prompt'):
                if delta is None or not med or med['input'] == 0:
                    notes.append('Bloated prompt requires paired measurements from Round 3.')
                    cost, basis = None, 'unavailable'
                else:
                    fn = lambda p: p['input'] + delta*p['input']/med['input']
                    cost, basis = self.call_cost(task, model, fn)
                    inp = fn(base) if base else None
                    notes.append(f'Bloated prompt adds ~{delta:.0f} input tokens per call (measured in Round 3; tokenizer-adjusted estimate).')
            else:
                cost, basis = self.call_cost(task, model, lambda p: p['input'])
                inp = base['input'] if base else None
                if lean and lean['graded']:
                    notes.append(f"Lean prompt held quality in Round 3: {lean['passed']}/{lean['graded']} passed.")
            total = cost*calls if cost is not None else None
            total_input = inp*calls if inp is not None else None
        else:
            carried = carried_turns(calls, config['context'], config.get('window_turns', 2))
            fn = lambda p: calls*p['input'] + carried*(p['input']+p['visible_output'])
            total, basis = self.call_cost(task, model, fn, calls)
            cost = total/calls if total is not None else None
            total_input = fn(base) if base else None
            notes.append('Full conversation history is re-sent each turn.' if config['context'] == 'full' else f"Trimmed to {config.get('window_turns', 2)} previous turns; quality impact not measured.")
            notes.append('Reasoning tokens are billed once and are not re-sent as visible context.')
        if basis == 'estimate':
            notes.insert(0, 'No measurement for this model: rate-card estimate, quality unverified.')
        if basis == 'unavailable':
            notes.insert(0, 'Pricing or required measurement unavailable for this model.')
        return {'id': step['id'], 'label': step['label'], 'unit': step['unit'], 'model': model, 'basis': basis,
                'per_call': cost, 'cost_per_workflow': total, 'calls': calls,
                'tokens': {'input': total_input, 'output': (base['visible_output']+base['reasoning'])*calls if base else None},
                'quality': self.quality(task, model), 'notes': notes}

    def estimate(self, config):
        attempts = expected_attempts(config['retry_rate'], config.get('max_retries'))
        per_month = config['workflows_per_day'] * self.workflow['days_per_month']
        steps = [self._step(step, config['steps'][step['id']]) for step in self.workflow['steps']]
        for step in steps:
            step['cost_per_workflow'] = step['cost_per_workflow']*attempts if step['cost_per_workflow'] is not None else None
            step['monthly'] = step['cost_per_workflow']*per_month if step['cost_per_workflow'] is not None else None
            definition = next(s for s in self.workflow['steps'] if s['id'] == step['id'])
            step['timing'] = self.step_timing(definition, config['steps'][step['id']], attempts)
        available = all(s['cost_per_workflow'] is not None for s in steps)
        total = sum(s['cost_per_workflow'] for s in steps) if available else None
        time_available = all(s['timing']['available'] for s in steps)
        elapsed = sum(s['timing']['per_workflow_seconds'] for s in steps) if time_available else None
        work = sum(s['timing']['model_call_seconds'] for s in steps) if time_available else None
        return {'available': available, 'per_workflow': total, 'monthly': total*per_month if available else None,
                'yearly': total*per_month*12 if available else None, 'workflows_per_month': per_month,
                'attempts_per_call': attempts, 'steps': steps,
                'timing': {'available': time_available, 'basis': 'estimate from measurements' if time_available else 'unavailable',
                           'per_workflow_seconds': elapsed,
                           'daily_model_call_hours': work * config['workflows_per_day'] / 3600 if time_available else None,
                           'monthly_model_call_hours': work * per_month / 3600 if time_available else None}}

    def fixed_design(self, as_built):
        config = copy.deepcopy(as_built)
        config['max_retries'] = 1
        for step in self.workflow['steps']:
            good = []
            for model, samples in self.samples.get(step['task_id'], {}).get(None, {}).items():
                p = profile(samples)
                if p['graded'] and p['passed'] == p['graded'] and not any(x.lower() in model.lower() for x in self.workflow.get('fix_excludes', [])):
                    good.append((p['cost'], model))
            sc = config['steps'][step['id']]
            if good:
                sc['model'] = min(good)[1]
            if step['kind'] == 'agent':
                sc['context'] = 'window'
            else:
                sc['bloated_prompt'] = False
        return config

def build_rates(models, local):
    rates = copy.deepcopy(local)
    for model in models:
        rates[model['id']] = model['rates']
    return rates

def workflow_context(history, recordings, models, local):
    runs, tasks = evidence_runs(history, recordings), load_tasks()
    return Estimator(load_workflow(), collect_samples(runs, tasks), build_rates(models, local), collect_timings(runs, tasks))
