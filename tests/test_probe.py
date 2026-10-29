import argparse
import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('probe',Path(__file__).parents[1]/'scripts/probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

async def test_probe_discovery_only(monkeypatch,capsys):
    class Client:
        def __init__(self,*a):pass
        async def discover_models(self):return [{'id':'m','rates':{}}]
        async def stream(self,*a):raise AssertionError('Billable call')
        async def close(self):pass
    monkeypatch.setattr(probe,'LiteLLMClient',Client)
    assert await probe.probe(argparse.Namespace(model=None,precise=False,max_tokens=1024))==0
    assert json.loads(capsys.readouterr().out)['calls']==[]

def test_probe_redacts_content_and_headers():
    report=probe.report_result({'text':'PRIVATE GENERATED TEXT','headers':{'x-litellm-response-cost':'.3'},
        'usage':{'prompt_tokens':10,'completion_tokens':3},'ttft_ms':1,'total_ms':2,'gateway_ms':1,'truncated':False},None,None)
    assert report['visible_characters']==22 and 'PRIVATE' not in json.dumps(report)
    assert report['header_names']==['x-litellm-response-cost']
    assert 'headers' not in report

async def test_probe_safe_failure(monkeypatch,capsys):
    class Client:
        def __init__(self,*a):pass
        async def discover_models(self):raise probe.GatewayError('secret URL')
        async def close(self):pass
    monkeypatch.setattr(probe,'LiteLLMClient',Client)
    assert await probe.probe(argparse.Namespace(model=None))==1
    assert 'secret URL' not in capsys.readouterr().out
