"""Discovery by default. --model explicitly opts into a billable call."""
import argparse
import asyncio
import json
from promptpriced.config import settings
from promptpriced.litellm_client import LiteLLMClient, GatewayError
from promptpriced.pricing import resolve_cost, load_local_rates, usage_tokens

def report_result(result, rates, local):
    return {'header_names': sorted(result['headers']), 'usage': usage_tokens(result['usage']),
            'cost': resolve_cost(result['usage'], result['headers'], rates, local),
            'ttft_ms': result['ttft_ms'], 'total_ms': result['total_ms'], 'gateway_ms': result['gateway_ms'],
            'visible_characters': len(result['text']), 'truncated': result['truncated']}

async def probe(args):
    client = LiteLLMClient(settings)
    try:
        models = await client.discover_models()
        report = {'ok': True, 'chat_models': models, 'calls': []}
        if args.model:
            selected = next((m for m in models if m['id'] == args.model), None)
            if selected is None:
                raise GatewayError('Requested model is not an available chat model.')
            async for event in client.stream(args.model, 'Reply with the word ready.', args.max_tokens):
                if event['type'] == 'result':
                    report['calls'].append({'mode': 'stream', **report_result(event['result'], selected['rates'], load_local_rates().get(args.model))})
            if args.precise:
                result = await client.complete(args.model, 'Reply with the word ready.', args.max_tokens)
                report['calls'].append({'mode': 'non-stream', **report_result(result, selected['rates'], load_local_rates().get(args.model))})
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0
    except GatewayError:
        print(json.dumps({'ok': False, 'error': 'Gateway capability check failed. Verify configuration and connectivity.'}))
        return 1
    finally:
        await client.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', help='Exact model ID; opts into a billable streaming call')
    parser.add_argument('--max-tokens', type=int, default=1024)
    parser.add_argument('--precise', action='store_true', help='Add a billable non-streaming call')
    args = parser.parse_args()
    if args.max_tokens < 1:
        parser.error('--max-tokens must be at least 1')
    if args.precise and not args.model:
        parser.error('--precise requires --model')
    return asyncio.run(probe(args))

if __name__ == '__main__':
    raise SystemExit(main())
