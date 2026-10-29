import math
import pytest
from promptpriced.pricing import number, normalize_rates, usage_tokens, resolve_cost, project_cost, load_local_rates

RATES = {'input_cost_per_token': .01, 'output_cost_per_token': .02,
         'cache_read_input_token_cost': .001, 'cache_creation_input_token_cost': .005,
         'output_cost_per_reasoning_token': .03}
USAGE = {'prompt_tokens': 100, 'completion_tokens': 50,
         'prompt_tokens_details': {'cached_tokens': 20, 'cache_write_tokens': 10},
         'completion_tokens_details': {'reasoning_tokens': 30}}

def test_components_no_double_counting():
    cost = resolve_cost(USAGE, {}, RATES)
    assert cost['amount'] == pytest.approx(.7 + .02 + .05 + .4 + .9)
    assert cost['tokens']['visible_output'] == 20
    assert sum(cost['components'].values()) == cost['amount']

def test_gateway_authority_metadata_and_partial_components():
    c = resolve_cost(USAGE, {'X-LiteLLM-Response-Cost': '4', 'x-litellm-response-cost-input': '1',
        'x-litellm-response-cost-margin-amount': '.3', 'x-litellm-response-cost-discount-amount': '.1'}, RATES)
    assert c['amount'] == 4 and c['source'] == 'gateway'
    assert c['margin_amount'] == .3 and c['discount_amount'] == .1
    assert c['components'] == {'input': 1}
    assert not c['components_complete'] and not c['components_reconcile']
    assert c['rate_difference'] == pytest.approx(4 - 2.07)

def test_gateway_usage_cost_first_and_complete_components():
    c = resolve_cost({**USAGE, 'cost': 5}, {'x-litellm-response-cost':'6','x-litellm-response-cost-input':'2','x-litellm-response-cost-output':'3'},RATES)
    assert c['amount'] == 5 and c['components_reconcile']
    assert 'inclusive totals' in c['component_semantics']

def test_zero_requires_explicit_free():
    c = resolve_cost(USAGE, {'x-litellm-response-cost':'0'})
    assert c['amount'] is None and c['source'] == 'unavailable'
    c = resolve_cost(USAGE, {'x-litellm-response-cost':'0'}, RATES)
    assert c['source'] == 'rates' and c['amount'] > 0
    free = {k:0 for k in RATES}
    assert resolve_cost(USAGE, {'x-litellm-response-cost':'0'}, free)['source'] == 'gateway'

@pytest.mark.parametrize('value',[True,False,-1,float('nan'),float('inf'),'NaN','-2',None,'bad'])
def test_invalid_number(value):
    assert number(value) is None

def test_aliases_conflict_and_missing_cache():
    rates = {**RATES, 'cache_read_input_cost_per_token': .5}
    assert normalize_rates(rates)['cache_read_input_token_cost'] is None
    assert resolve_cost(USAGE, {}, rates)['amount'] is None
    assert resolve_cost(USAGE, {}, {}, RATES)['source'] == 'local table'
    assert resolve_cost(USAGE, {}, {'input_cost_per_token':0})['amount'] is None

@pytest.mark.parametrize('patch',[
    {'prompt_tokens':10}, {'completion_tokens':20}, {'prompt_tokens':True},
    {'prompt_tokens':1.5}, {'completion_tokens':-1}, {'prompt_tokens_details':None},
    {'completion_tokens_details':[]}, {'cache_write_tokens':11}])
def test_inconsistent_usage(patch):
    assert usage_tokens({**USAGE, **patch}) is None

def test_anthropic_and_duplicate_write_names():
    t = usage_tokens({'input_tokens':10,'output_tokens':5,'cache_read_input_tokens':20,'cache_creation_input_tokens':30})
    assert t['input'] == 60 and t['cache_write'] == 30
    t = usage_tokens({**USAGE,'cache_creation_input_tokens':10})
    assert t['cache_write'] == 10

def test_projection_and_table(tmp_path):
    assert project_cost(.01,1000)==10
    assert project_cost(None,1000) is None
    for n in (-1, 2.5, True):
        with pytest.raises(ValueError):project_cost(1,n)
    with pytest.raises(OverflowError):project_cost(1e308,10)
    path=tmp_path/'pricing.yaml';path.write_text('units: USD_per_million\nmodels: {}')
    with pytest.raises(ValueError):load_local_rates(path)
