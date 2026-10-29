import asyncio
import json
import httpx
import pytest
from promptpriced.config import Settings
from promptpriced.litellm_client import LiteLLMClient, GatewayError

CFG=Settings(litellm_api_base='https://secret.example/v1',litellm_api_key='private-key',request_timeout=.15)

def client(handler):return LiteLLMClient(CFG,httpx.MockTransport(handler))

async def test_discovery_agreement_modes_budget():
    def handle(req):
        assert req.headers['authorization']=='Bearer private-key'
        if req.url.path.endswith('/models'):
            return httpx.Response(200,json={'data':[{'id':m} for m in ('chat','mixed','embedding','orphan')]},headers={'x-litellm-key-spend':'8','x-litellm-key-max-budget':'10'})
        return httpx.Response(200,json={'data':[
            {'model_name':'chat','model_info':{'mode':'chat','input_cost_per_token':.1,'output_cost_per_token':.2}},
            {'model_name':'chat','model_info':{'mode':'chat','input_cost_per_token':.3,'output_cost_per_token':.2}},
            {'model_name':'mixed','model_info':{'mode':'chat'}},{'model_name':'mixed','model_info':{'mode':'embedding'}},
            {'model_name':'embedding','model_info':{'mode':'embedding'}},{'model_name':'not-listed','model_info':{'mode':'chat'}}]})
    c=client(handle)
    models=await c.discover_models()
    assert [m['id'] for m in models]==['chat']
    assert models[0]['input_per_million'] is None and models[0]['output_per_million']==200000
    assert c.budget=={'spend':8,'max_budget':10}
    await c.close()

async def test_stream_fragmented_usage_headers_and_finish():
    def handle(req):
        body=json.loads(req.content)
        assert body['stream_options']=={'include_usage':True}
        content='data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: {"choices":[{"delta":{},\ndata: "finish_reason":"stop"}]}\n\ndata: {"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":2}}\n\ndata: [DONE]\n\n'
        return httpx.Response(200,text=content,headers={'x-litellm-response-cost':'.5','x-litellm-response-duration-ms':'2','x-secret':'never'})
    c=client(handle);events=[e async for e in c.stream('chat','test',8)]
    assert events[0]=={'type':'token','text':'hello'}
    r=events[-1]['result'];assert not r['truncated'] and r['text']=='hello' and r['usage']['prompt_tokens']==4
    assert 'x-secret' not in r['headers'] and r['ttft_ms'] is not None
    await c.close()

@pytest.mark.parametrize('response',[httpx.Response(302,headers={'location':'https://secret.example'}),httpx.Response(500,text='private-key'),httpx.Response(200,text='data: {bad}\n\n'),httpx.Response(200,text='data: {"error":{"message":"private-key"}}\n\n')])
async def test_safe_errors(response):
    c=client(lambda _:response)
    with pytest.raises(GatewayError) as e:
        [x async for x in c.stream('x','p',2)]
    assert 'private-key' not in str(e.value) and 'secret.example' not in str(e.value)
    await c.close()

async def test_incomplete_and_non_streaming():
    c=client(lambda _:httpx.Response(200,text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\ndata: [DONE]\n\n'))
    assert [x async for x in c.stream('x','p',2)][-1]['result']['truncated']
    await c.close()
    c=client(lambda _:httpx.Response(200,json={'choices':[{'message':{'content':'done'},'finish_reason':'stop'}],'usage':{}}))
    assert (await c.complete('x','p',2))['text']=='done'
    await c.close()

class SlowStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        while True:
            await asyncio.sleep(.025)
            yield b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n'

async def test_active_stream_total_deadline():
    c=client(lambda _:httpx.Response(200,stream=SlowStream()))
    with pytest.raises(GatewayError):
        async with asyncio.timeout(.6):
            [e async for e in c.stream('x','p',2)]
    await c.close()
