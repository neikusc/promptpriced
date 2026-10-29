"""Conservative cost accounting. All rates and amounts are USD."""
import math
from pathlib import Path
import yaml
from .config import ROOT

RATE_ALIASES = {
    'input_cost_per_token': ('input_cost_per_token',),
    'output_cost_per_token': ('output_cost_per_token',),
    'cache_read_input_token_cost': ('cache_read_input_token_cost', 'cache_read_input_cost_per_token'),
    'cache_creation_input_token_cost': ('cache_creation_input_token_cost', 'cache_creation_input_cost_per_token', 'cache_write_input_token_cost'),
    'output_cost_per_reasoning_token': ('output_cost_per_reasoning_token', 'reasoning_cost_per_token'),
}

def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None

def normalize_rates(rates):
    rates = rates if isinstance(rates, dict) else {}
    result = {}
    for key, aliases in RATE_ALIASES.items():
        values = [number(rates[a]) for a in aliases if a in rates]
        result[key] = values[0] if values and None not in values and all(v == values[0] for v in values) else None
    return result

def load_local_rates(path=None):
    data = yaml.safe_load(Path(path or ROOT / 'config/pricing.yaml').read_text())
    if data.get('units') != 'USD_per_token':
        raise ValueError('Pricing units must be USD_per_token.')
    return {m: normalize_rates(r) for m, r in data.get('models', {}).items()}

def _integer(v):
    n = number(v)
    return int(n) if n is not None and n.is_integer() else None

def usage_tokens(usage):
    if not isinstance(usage, dict):
        return None
    inp = _integer(usage.get('prompt_tokens', usage.get('input_tokens')))
    out = _integer(usage.get('completion_tokens', usage.get('output_tokens')))
    pd = usage.get('prompt_tokens_details', usage.get('input_tokens_details', {}))
    od = usage.get('completion_tokens_details', usage.get('output_tokens_details', {}))
    if not isinstance(pd, dict) or not isinstance(od, dict):
        return None
    read = _integer(pd.get('cached_tokens', usage.get('cached_tokens', usage.get('cache_read_input_tokens', 0))))
    candidates = [pd[k] for k in ('cache_write_tokens', 'cache_creation_tokens') if k in pd]
    candidates += [usage[k] for k in ('cache_write_tokens', 'cache_creation_tokens', 'cache_creation_input_tokens') if k in usage]
    writes = [_integer(v) for v in candidates] or [0]
    if None in writes or len({v for v in writes if v > 0}) > 1:
        return None
    write = max(writes)
    reasoning = _integer(od.get('reasoning_tokens', usage.get('reasoning_tokens', 0)))
    if None in (inp, out, read, reasoning):
        return None
    if 'input_tokens' in usage and 'prompt_tokens' not in usage and 'input_tokens_details' not in usage:
        inp += read + write
    if read + write > inp or reasoning > out:
        return None
    return {'input': inp, 'output': out, 'cache_read': read, 'cache_write': write,
            'reasoning': reasoning, 'visible_output': out - reasoning}

def _rated(usage, rates):
    tokens = usage_tokens(usage)
    rates = normalize_rates(rates)
    if tokens is None:
        return None, {}, None
    counts = {'input': tokens['input'] - tokens['cache_read'] - tokens['cache_write'],
              'cache_read': tokens['cache_read'], 'cache_write': tokens['cache_write'],
              'output': tokens['visible_output'], 'reasoning': tokens['reasoning']}
    keys = ['input_cost_per_token', 'cache_read_input_token_cost', 'cache_creation_input_token_cost',
            'output_cost_per_token', 'output_cost_per_reasoning_token']
    r = dict(rates)
    if r[keys[-1]] is None:
        r[keys[-1]] = r['output_cost_per_token']
    components = {k: (0.0 if count == 0 else count * r[key] if r[key] is not None else None)
                  for (k, count), key in zip(counts.items(), keys)}
    valid = rates['input_cost_per_token'] is not None and rates['output_cost_per_token'] is not None
    total = sum(components.values()) if valid and None not in components.values() else None
    if total is not None and not math.isfinite(total):
        total = None
    return total, components, tokens

def resolve_cost(usage, headers, rates=None, local_rates=None):
    headers = {k.lower(): v for k, v in headers.items()}
    result = {'amount': None, 'source': 'unavailable', 'components': {}, 'tokens': usage_tokens(usage)}
    for suffix, key in [('original', 'original_amount'), ('discount-amount', 'discount_amount'),
                        ('margin-amount', 'margin_amount'), ('margin-percent', 'margin_percent'),
                        ('input', 'input_amount'), ('output', 'output_amount'), ('tool-usage', 'tool_usage_amount')]:
        value = number(headers.get('x-litellm-response-cost-' + suffix))
        if value is not None:
            result[key] = value
    estimate, selected_rates = None, None
    for source, r in [('rates', rates), ('local table', local_rates)]:
        amount, parts, tokens = _rated(usage, r)
        if amount is not None:
            estimate = {'amount': amount, 'source': source, 'components': parts,
                        'component_semantics': 'additive; output excludes reasoning',
                        'output_total': tokens['output'], 'reasoning_subset': tokens['reasoning']}
            selected_rates = normalize_rates(r)
            break
    if estimate:
        result['rate_estimate'] = estimate
    for candidate in [usage.get('cost') if isinstance(usage, dict) else None, headers.get('x-litellm-response-cost')]:
        amount = number(candidate)
        explicit_free = estimate and estimate['amount'] == 0 and all(selected_rates[k] == 0 for k in ('input_cost_per_token', 'output_cost_per_token'))
        if amount is None or (amount == 0 and not explicit_free):
            continue
        result.update(amount=amount, source='gateway')
        parts = {key: result[key + '_amount'] for key in ('input', 'output', 'tool_usage') if key + '_amount' in result}
        if parts:
            result.update(components=parts, components_source='gateway',
                          component_semantics='inclusive totals; input includes cache; output includes reasoning',
                          components_complete='input' in parts and 'output' in parts)
        elif estimate:
            result.update(components=estimate['components'], components_source=estimate['source'],
                          component_semantics=estimate['component_semantics'], components_complete=True)
        else:
            result['components_complete'] = False
        if result['components_complete']:
            result['components_total'] = sum(result['components'].values())
            result['components_reconcile'] = math.isclose(amount, result['components_total'], rel_tol=1e-9, abs_tol=1e-12)
        else:
            result['components_reconcile'] = False
        if estimate:
            result['rate_difference'] = amount - estimate['amount']
        return result
    if estimate:
        result.update(amount=estimate['amount'], source=estimate['source'], components=estimate['components'],
                      components_source=estimate['source'], component_semantics=estimate['component_semantics'],
                      components_complete=True, components_reconcile=True, components_total=estimate['amount'])
    return result

def project_cost(amount, runs):
    if type(runs) is not int or runs < 0:
        raise ValueError('Runs must be a non-negative integer.')
    if amount is None:
        return None
    if number(amount) is None:
        raise ValueError('Invalid amount.')
    try:
        value = amount * runs
        if not math.isfinite(value):
            raise OverflowError('Projection overflow.')
        return value
    except OverflowError:
        raise OverflowError('Projection overflow.') from None

project = project_cost
