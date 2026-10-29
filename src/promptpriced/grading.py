import json
import math
import re
from datetime import date, datetime
from decimal import Decimal

TRUNCATED = {'length', 'max_tokens', 'max_output_tokens', 'max_completion_tokens', 'token_limit', 'model_length'}

def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate key')
        result[key] = value
    return result

def _invalid(_):
    raise ValueError('Non-finite JSON')

def _date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
    except ValueError:
        pass
    for fmt in ('%m/%d/%Y', '%B %d, %Y', '%b %d, %Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None

def _matches(value, spec):
    expected = spec.get('expected')
    if value is None or expected is None:
        return value is expected
    kind = spec['type']
    if kind == 'date':
        return _date(value) is not None and _date(value) == _date(str(expected))
    if kind in ('number', 'integer'):
        if type(value) not in (int, float):
            return False
        try:
            if not math.isfinite(value) or (kind == 'integer' and value != int(value)):
                return False
            return abs(Decimal(str(value)) - Decimal(str(expected))) <= Decimal(str(spec.get('tolerance', 0)))
        except (ValueError, OverflowError):
            return False
    if kind == 'boolean':
        return value is expected
    return isinstance(value, str) and value == expected

def grade(task, text, finish_reason=None):
    def result(status, checks, summary=''):
        return {'status': status, 'passed': True if status == 'pass' else False if status == 'fail' else None,
                'checks': checks, 'summary': summary}
    if str(finish_reason).lower() in TRUNCATED:
        return result('truncated', [], 'Token limit reached; content was not graded.')
    config = task.get('grading')
    if not config:
        return result('ungraded', [])
    checks = []
    def check(key, label, passed, detail=''):
        checks.append({'id': key, 'label': label, 'passed': bool(passed), 'detail': detail})
    if config['type'] == 'json':
        text = text.strip()
        fence = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.S | re.I)
        if fence:
            text = fence.group(1)
        try:
            data = json.loads(text, object_pairs_hook=_unique, parse_constant=_invalid)
            if not isinstance(data, dict):
                raise ValueError('Not an object')
        except (ValueError, TypeError, RecursionError):
            check('json', 'Valid JSON object', False, 'Expected a valid JSON object with unique keys.')
            return result('fail', checks)
        check('json', 'Valid JSON object', True)
        fields = config['fields']
        if config.get('exact_keys'):
            check('keys', 'No extra fields', not (data.keys() - fields.keys()))
        for key, spec in fields.items():
            passed = key in data and _matches(data[key], spec)
            check(key, key, passed, '' if passed else 'Required field is missing.' if key not in data else 'Value or type does not match.')
        summary = ''
    elif config['type'] == 'rubric':
        sentences = re.split(r'(?<=[.!?])\s+|\n+', text.replace('*', '').replace('`', ''))
        for finding in config['findings']:
            passed = any(not any(re.search(p, s, re.I) for p in finding.get('exclude_patterns', []))
                         and any(all(re.search(p, s, re.I) for p in group) for group in finding['any_of'])
                         for s in sentences)
            check(finding['id'], finding['label'], passed)
        summary = 'Heuristic rubric only, not an authoritative evaluation; presenter review may override findings.'
    else:
        return result('ungraded', [])
    return result('pass' if all(c['passed'] for c in checks) else 'fail', checks, summary)
