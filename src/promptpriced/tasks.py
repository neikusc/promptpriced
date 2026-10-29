import copy
import yaml
from .config import ROOT

def load_tasks():
    tasks, seen = [], set()
    for path in sorted((ROOT / 'config/tasks').glob('*.yaml')):
        task = yaml.safe_load(path.read_text())
        if not {'id', 'title', 'description', 'prompt', 'max_tokens', 'grading'} <= task.keys():
            raise ValueError('Invalid task contract.')
        if task['id'] in seen:
            raise ValueError('Duplicate task ID.')
        seen.add(task['id'])
        tasks.append(task)
    return copy.deepcopy(tasks)

def get_task(task_id):
    for task in load_tasks():
        if task['id'] == task_id:
            return task
    raise KeyError(task_id)
