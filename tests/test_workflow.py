import copy
import pytest
from promptpriced.tasks import load_tasks,get_task
from promptpriced.workflow import (Estimator,collect_samples,profile,prompt_id,expected_attempts,carried_turns,load_workflow,evidence_runs,build_rates)

RATES={'input_cost_per_token':.001,'output_cost_per_token':.002,'output_cost_per_reasoning_token':.003}

def sample(cost=.2,inp=100,visible=30,reasoning=20,passed=True):
    return {'run_id':'a','cost':cost,'input':inp,'visible_output':visible,'reasoning':reasoning,'passed':passed}

def estimator():
    return Estimator(load_workflow(),{'extraction':{None:{'cheap':[sample()],'expensive':[sample(cost=.8)]}},
        'leakage':{None:{'cheap':[sample()]}},
        'prompt_bloat':{'bloated':{'cheap':[sample(inp=200)]},'lean':{'cheap':[sample(inp=100)]}}},
        {'cheap':RATES,'expensive':RATES,'unmeasured':RATES})

def test_measured_preserved_and_scaled():
    e=estimator()
    assert e.call_cost('extraction','cheap',lambda p:p['input'])==(.2,'measured')
    new,basis=e.call_cost('extraction','cheap',lambda p:p['input']*2)
    # base list: .1+.06+.06=.22; new: .2+.06+.06=.32
    assert new==pytest.approx(.2*.32/.22) and basis=='measured'
    new,basis=e.call_cost('extraction','unmeasured',lambda p:p['input'])
    assert new==pytest.approx(.1+.06) and basis=='estimate'
    assert e.quality('extraction','unmeasured')=='unverified'

def test_context_carries_visible_not_reasoning():
    e=estimator();step=e.workflow['steps'][1]
    full=e._step(step,{'model':'cheap','turns':3,'context':'full'})
    assert full['tokens']['input']==3*100+3*(100+30)
    window=e._step(step,{'model':'cheap','turns':3,'context':'window','window_turns':1})
    assert window['tokens']['input']==3*100+2*(100+30)
    assert window['cost_per_workflow']<full['cost_per_workflow']
    assert carried_turns(4,'full')==6 and carried_turns(4,'window',1)==3

def test_retry_formula():
    assert expected_attempts(0)==1
    assert expected_attempts(.2)==pytest.approx(1.25)
    assert expected_attempts(.2,0)==1
    assert expected_attempts(.2,1)==pytest.approx(1.2)
    assert expected_attempts(5)==pytest.approx(10)

def test_bloat_and_unknowns():
    e=estimator();step=e.workflow['steps'][0]
    bloated=e._step(step,{'model':'cheap','calls':2,'bloated_prompt':True})
    assert bloated['per_call']==pytest.approx(.2*.32/.22)
    assert bloated['cost_per_workflow']==pytest.approx(2*bloated['per_call'])
    assert '100 input tokens' in bloated['notes'][0]
    lean=e._step(step,{'model':'cheap','calls':2,'bloated_prompt':False})
    assert lean['per_call']==.2 and '1/1 passed' in lean['notes'][0]
    cfg=copy.deepcopy(e.workflow['as_built']);cfg['steps']['extract']['model']='missing';cfg['steps']['analysis']['model']='cheap'
    assert not e.estimate(cfg)['available'] and e.estimate(cfg)['monthly'] is None
    e.samples.pop('prompt_bloat')
    assert e._step(step,{'model':'cheap','calls':1,'bloated_prompt':True})['per_call'] is None

def test_fixed_design_quality_and_exclusions():
    e=estimator()
    e.samples['extraction'][None]['bad']=[sample(cost=.01,passed=False)]
    e.samples['extraction'][None]['reasoning-model']=[sample(cost=.001)]
    fix=e.fixed_design(e.workflow['as_built'])
    assert fix['steps']['extract']['model']=='cheap' and not fix['steps']['extract']['bloated_prompt']
    assert fix['steps']['analysis']['context']=='window' and fix['max_retries']==1

def test_sample_evidence_filters_variants_and_prompts():
    t=get_task('extraction')
    result={'model':'m','prompt_id':prompt_id(t['prompt']), 'cost':{'amount':.1,'tokens':{'input':100,'visible_output':20,'reasoning':0}},'grade':{'status':'pass','passed':True}}
    run={'id':'a','task_id':t['id'],'complete':True,'revealed':True,'results':[result]}
    assert collect_samples([run],load_tasks())['extraction'][None]['m'][0]['passed']
    for patch in ({'error':'oops'},{'truncated':True},{'prompt_id':'edited'},{'cost':{'amount':None}}):
        bad={**run,'results':[{**result,**patch}]};assert collect_samples([bad],load_tasks())=={}
    assert collect_samples([{**run,'revealed':False}],load_tasks())=={}
    assert collect_samples([{**run,'complete':False}],load_tasks())=={}
    b=get_task('prompt_bloat');r={**run,'task_id':b['id'],'results':[{**result,'prompt_id':prompt_id(b['variants'][0]['prompt'])}]}
    assert 'bloated' in collect_samples([r],load_tasks())['prompt_bloat']
    assert profile([sample(passed=None)])['graded']==0

def test_history_overrides_recordings_but_playbacks_ignored():
    class H:
        def list(self,*a):return [{'id':'a','recorded':False,'v':2},{'id':'b','recorded':True}]
    class R:
        def all(self):return [{'id':'a','v':1}]
    assert evidence_runs(H(),R())==[{'id':'a','recorded':False,'v':2}]
    rates=build_rates([{'id':'m','rates':{'input_cost_per_token':None}}],{'m':RATES})
    assert rates['m']['input_cost_per_token'] is None
