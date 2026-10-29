import json
import pytest
from promptpriced.grading import grade
from promptpriced.tasks import load_tasks, get_task

ANSWER = {'claim_id':'FN-2048','policyholder':'Avery Morgan','loss_date':'2026-03-14',
          'reported_date':'2026-03-16','cause':'water damage','estimated_loss_usd':18450.75,
          'deductible_usd':1000,'injuries':0,'police_report_id':None}

def test_task_contract_fresh_copies():
    assert len(load_tasks())==3
    t=get_task('extraction');t['grading'].clear()
    assert get_task('extraction')['grading']
    with pytest.raises(KeyError):get_task('absent')

@pytest.mark.parametrize('loss_date',['2026-03-14','2026-03-14T12:00:00Z','03/14/2026','March 14, 2026','Mar 14, 2026'])
def test_fenced_json_dates(loss_date):
    text=json.dumps({**ANSWER,'loss_date':loss_date})
    assert grade(get_task('extraction'),'```json\n'+text+'\n```','stop')['passed']

@pytest.mark.parametrize('text',['[]','null','bad','{"x":NaN}','{"x":1,"x":2}'])
def test_bad_json(text):
    g=grade(get_task('extraction'),text,None)
    assert g['status']=='fail' and len(g['checks'])==1

@pytest.mark.parametrize('patch',[{'injuries':False},{'police_report_id':'null'},{'estimated_loss_usd':'18450.75'},
    {'injuries':.5},{'cause':None},{'extra':1},{'estimated_loss_usd':float('inf')}])
def test_strict_types(patch):
    assert not grade(get_task('extraction'),json.dumps({**ANSWER,**patch}),'stop')['passed']

def test_tolerance_and_missing():
    assert grade(get_task('extraction'),json.dumps({**ANSWER,'estimated_loss_usd':18450.76}),'stop')['passed']
    a=ANSWER.copy();del a['claim_id']
    assert grade(get_task('extraction'),json.dumps(a),'stop')['checks'][2]['detail']=='Required field is missing.'

@pytest.mark.parametrize('reason',['length','MAX_TOKENS','model_length','token_limit','max_completion_tokens'])
def test_truncated(reason):
    g=grade(get_task('extraction'),'bad',reason)
    assert g['status']=='truncated' and g['passed'] is None and g['checks']==[]

def test_ungraded_and_bloat_shared_grade():
    assert grade({},'anything',None)['status']=='ungraded'
    t=get_task('prompt_bloat')
    assert len(t['variants'])==2 and all('grading' not in v for v in t['variants'])

def test_rubric_sentences_negations_case():
    t=get_task('leakage')
    text=('CANCELLATION DATE is target leakage. Group split by account to prevent overlap. '
          'Use a temporal holdout. 99% is the non-churn majority baseline. Evaluate precision and recall.')
    assert grade(t,text,'stop')['passed']
    g=grade(t,'There is no target leakage from cancellation date. Ignore precision and recall. Do not use a temporal split.','stop')
    checks={c['id']:c['passed'] for c in g['checks']}
    assert not checks['target_leakage'] and not checks['useful_metrics'] and not checks['temporal_holdout']
    assert not grade(t,'Precision matters. Recall matters.','stop')['checks'][-1]['passed']
