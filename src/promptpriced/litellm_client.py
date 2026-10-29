import asyncio
import json
import time
import httpx
from .pricing import normalize_rates, number

class GatewayError(RuntimeError):
    """Only sanitized messages may cross the API boundary."""

ALLOWED_HEADERS = {'x-litellm-response-cost', 'x-litellm-response-duration-ms', 'x-litellm-key-spend', 'x-litellm-key-max-budget'} | {
    'x-litellm-response-cost-' + suffix for suffix in ('input', 'output', 'original', 'tool-usage', 'discount-amount', 'margin-amount', 'margin-percent')}

class LiteLLMClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.budget = {'spend': None, 'max_budget': None}
        self.http = httpx.AsyncClient(headers={'Authorization': 'Bearer ' + settings.litellm_api_key},
                                      timeout=settings.request_timeout, follow_redirects=False, transport=transport)

    def _url(self, path):
        if not self.settings.litellm_api_base:
            raise GatewayError('Gateway is not configured. Set .env to enable live mode.')
        return self.settings.litellm_api_base.rstrip('/') + path

    def _headers(self, response):
        headers = {k: v for k, v in response.headers.items() if k.lower() in ALLOWED_HEADERS}
        for suffix, key in [('spend', 'spend'), ('max-budget', 'max_budget')]:
            name = 'x-litellm-key-' + suffix
            if name in headers:
                self.budget[key] = number(headers[name])
        return headers

    def _check(self, response):
        self._headers(response)
        if response.status_code >= 300:
            raise GatewayError(f'Gateway request failed (HTTP {response.status_code}).')

    async def discover_models(self):
        try:
            async with asyncio.timeout(self.settings.request_timeout):
                data = []
                for path in ('/models', '/model/info'):
                    response = await self.http.get(self._url(path))
                    self._check(response)
                    packet = response.json()
                    if not isinstance(packet, dict) or not isinstance(packet.get('data'), list):
                        raise ValueError()
                    data.append(packet['data'])
                ids = {m['id'] for m in data[0]}
                groups = {}
                for info in data[1]:
                    name = info.get('model_name')
                    if name in ids:
                        groups.setdefault(name, []).append(info.get('model_info') or {})
                result = []
                for name, deployments in groups.items():
                    if not all(d.get('mode') == 'chat' for d in deployments):
                        continue
                    normalized = [normalize_rates(d) for d in deployments]
                    rates = {key: normalized[0][key] if all(r[key] == normalized[0][key] for r in normalized) else None for key in normalized[0]}
                    i, o = rates['input_cost_per_token'], rates['output_cost_per_token']
                    result.append({'id': name, 'rates': rates, 'input_per_million': i * 1e6 if i is not None else None,
                                   'output_per_million': o * 1e6 if o is not None else None, 'pricing_known': i is not None and o is not None})
                return sorted(result, key=lambda m: m['id'])
        except GatewayError:
            raise
        except (TimeoutError, httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            raise GatewayError('Gateway discovery failed. Check configuration and connectivity.') from None

    def _payload(self, model, prompt, max_tokens, stream):
        payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': max_tokens, 'stream': stream}
        if stream:
            payload['stream_options'] = {'include_usage': True}
        return payload

    def _result(self, model, text, usage, headers, finish_reason, ttft, start, ended):
        total = (time.monotonic() - start) * 1000
        gateway = number(headers.get('x-litellm-response-duration-ms'))
        return {'model': model, 'text': text, 'usage': usage, 'headers': headers, 'finish_reason': finish_reason,
                'ttft_ms': ttft, 'total_ms': total, 'gateway_ms': gateway,
                'overhead_ms': max(0, total - gateway) if gateway is not None else None,
                'truncated': not ended or str(finish_reason).lower() in {'length', 'max_tokens', 'max_output_tokens', 'max_completion_tokens', 'token_limit', 'model_length'}}

    async def stream(self, model, prompt, max_tokens):
        start, ttft = time.monotonic(), None
        text, usage, finish, ended = '', {}, None, False
        try:
            async with asyncio.timeout(self.settings.request_timeout):
                async with self.http.stream('POST', self._url('/chat/completions'), json=self._payload(model, prompt, max_tokens, True)) as response:
                    self._check(response)
                    headers = self._headers(response)
                    lines = []
                    async for line in response.aiter_lines():
                        if line.startswith('data:'):
                            lines.append(line[5:].lstrip(' '))
                            continue
                        if line != '' or not lines:
                            continue
                        raw, lines = '\n'.join(lines), []
                        if raw.strip() == '[DONE]':
                            break
                        try:
                            packet = json.loads(raw)
                        except ValueError:
                            # Some gateways fragment JSON across data lines inside a string.
                            packet = json.loads(raw.replace('\n', ''))
                        if not isinstance(packet, dict) or 'error' in packet:
                            raise ValueError()
                        if isinstance(packet.get('usage'), dict):
                            for key, value in packet['usage'].items():
                                if isinstance(value, dict) and isinstance(usage.get(key), dict):
                                    usage[key].update(value)
                                else:
                                    usage[key] = value
                        for choice in packet.get('choices', [])[:1]:
                            content = choice.get('delta', {}).get('content')
                            if content:
                                if not isinstance(content, str):
                                    raise ValueError()
                                if ttft is None:
                                    ttft = (time.monotonic() - start) * 1000
                                text += content
                                yield {'type': 'token', 'text': content}
                            if choice.get('finish_reason') is not None:
                                finish, ended = choice['finish_reason'], True
                    yield {'type': 'result', 'result': self._result(model, text, usage, headers, finish, ttft, start, ended)}
        except GatewayError:
            raise
        except (TimeoutError, httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            raise GatewayError('Model request failed. Check gateway availability or configuration.') from None

    async def complete(self, model, prompt, max_tokens):
        start = time.monotonic()
        try:
            async with asyncio.timeout(self.settings.request_timeout):
                response = await self.http.post(self._url('/chat/completions'), json=self._payload(model, prompt, max_tokens, False))
                self._check(response)
                packet = response.json()
                if 'error' in packet:
                    raise ValueError()
                choice = packet['choices'][0]
                return self._result(model, choice['message']['content'] or '', packet.get('usage', {}), self._headers(response),
                                    choice.get('finish_reason'), None, start, choice.get('finish_reason') is not None)
        except GatewayError:
            raise
        except (TimeoutError, httpx.HTTPError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            raise GatewayError('Model request failed. Check gateway availability or configuration.') from None

    async def close(self):
        await self.http.aclose()
