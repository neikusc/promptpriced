import copy
import json
from pathlib import Path

class Recordings:
    def __init__(self, path):
        self.path = Path(path)

    def all(self):
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text())

    def get(self, run_id):
        return next((copy.deepcopy(r) for r in self.all() if r['id'] == run_id), None)

    def summaries(self):
        return [{'id': r['id'], 'task_id': r['task_id'], 'created_at': r['created_at'],
                 'models': [x['model'] for x in r['reels']] if r.get('revealed') else []}
                for r in sorted(self.all(), key=lambda r: r['created_at'], reverse=True)]

    def capture(self, run):
        if run.get('recorded') or not run.get('complete') or len(run['results']) != len(run['reels']) or any(r.get('error') for r in run['results']):
            return
        runs = [r for r in self.all() if r['id'] != run['id']] + [copy.deepcopy(run)]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(runs[-30:], allow_nan=False))
        tmp.replace(self.path)
