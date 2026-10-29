import copy
import json
import sqlite3
from datetime import datetime, timezone
from statistics import mean
from .timing import timing_profile

def now():
    return datetime.now(timezone.utc).isoformat()

class History:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT, payload TEXT)')
        self.db.commit()

    def save(self, run):
        self.db.execute('INSERT INTO runs VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET created_at=excluded.created_at, payload=excluded.payload',
                        (run['id'], run['created_at'], json.dumps(run, allow_nan=False)))
        self.db.commit()

    def get(self, run_id):
        row = self.db.execute('SELECT payload FROM runs WHERE id=?', (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit=100):
        return [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM runs ORDER BY created_at DESC LIMIT ?', (limit,))]

    def close(self):
        self.db.close()

def public_result(result, hidden):
    if hidden:
        return {k: copy.deepcopy(v) for k, v in result.items() if k in {'text', 'grade', 'truncated', 'variant', 'error'}}
    # Raw headers remain server-side, even when revealed.
    return {k: copy.deepcopy(v) for k, v in result.items() if k not in {'headers'}}

def public_run(run):
    value = {k: copy.deepcopy(v) for k, v in run.items() if k not in {'reels', 'events', 'results'}}
    value['results'] = [public_result(r, run['blind'] and not run['revealed']) for r in run['results']]
    if run['blind'] and not run['revealed']:
        value.pop('wall_ms', None)
    return value

def variance_groups(runs):
    buckets = {}
    for run in runs:
        if run.get('recorded') or (run.get('blind') and not run.get('revealed')):
            continue
        for r in run.get('results', []):
            if r.get('error') or r.get('truncated'):
                continue
            key = (run['task_id'], r['model'] + (' / ' + r['variant'] if r.get('variant') else ''), r.get('prompt_id', 'legacy'))
            buckets.setdefault(key, []).append(r)
    output = []
    for (task, model, prompt), items in buckets.items():
        costs = [r['cost']['amount'] for r in items if r.get('cost', {}).get('amount') is not None]
        timing = timing_profile(items)
        output.append({'task_id': task, 'model': model, 'prompt_id': prompt, 'count': len(items), 'priced_count': len(costs),
                       'min': min(costs) if costs else None, 'max': max(costs) if costs else None,
                       'mean': mean(costs) if costs else None, 'mean_total_ms': timing['mean_ms'] if timing else None,
                       'timing': timing})
    return output
