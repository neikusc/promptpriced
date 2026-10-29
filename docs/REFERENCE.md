# PromptPriced — Reference

*Same Prompt. Different Price.*

A local presenter app for comparing the same prompt across up to three chat models on an OpenAI-compatible LiteLLM gateway. Python 3.12+, FastAPI, SQLite, and plain JavaScript. No frontend build step.

For Docker + LiteLLM setup and basic usage, see the [quickstart README](../README.md).

## Start

```bash
git clone https://github.com/neikusc/promptpriced.git
cd promptpriced
# Install uv first if needed: https://docs.astral.sh/uv/getting-started/installation/
uv sync
cp .env.example .env
# Edit .env locally with your gateway base URL and API key.
uv run uvicorn promptpriced.app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. If using the environment prepared during development, uv is also available as `.venv/bin/uv`. The app loads `.env` from this project directory; it does not read the parent workspace's `.env`.

Set `LITELLM_API_BASE` to the gateway's API root (usually ending in `/v1`); discovery calls `/models` and `/model/info` under that root. Set `LITELLM_API_KEY` to a key with access to both discovery endpoints and chat completions. `REQUEST_TIMEOUT` is a total deadline in seconds, including active streams. `DATABASE_PATH` and `RECORDINGS_PATH` may override storage locations. Relative paths are relative to the launch directory.

No credentials are included. The initial app works offline for configuration and history, but has no fabricated answers, measurements, models, or recordings. Live pulls make billable requests. Discovery makes no chat-completion calls; gateway-specific discovery policies still apply. For a fresh offline installation, totals remain unavailable until real measurements and prices exist.

## Gateway troubleshooting

```bash
uv run python scripts/probe.py
# Explicitly opt into one billable streaming call:
uv run python scripts/probe.py --model EXACT_GATEWAY_MODEL_ID
# Add a billable non-streaming call to compare precise gateway usage:
uv run python scripts/probe.py --model EXACT_GATEWAY_MODEL_ID --precise --max-tokens 1024
```

The probe prints model capability metadata, numeric usage, cost, header names, timings, and generated character counts. It does not print endpoints, API keys, prompts, generated text, or raw header values. It exits 0 on success, 1 on a gateway failure. `--precise` requires `--model`; maximum tokens must be at least 1.

If discovery fails, check the API root, credentials, and permission for `/model/info`. Only IDs in `/models` whose **every deployment** has `model_info.mode: chat` are selectable. If deployments disagree on a rate, that rate is unavailable. Streaming needs SSE support and `stream_options.include_usage`; the response must contain a finish reason to avoid being marked truncated. A gateway returning HTTP redirects is rejected rather than followed.

Use `config/models.yaml` to set preferred gateway IDs in `defaults: [first, second, third]`. Discovery still validates the selection. Rates normally come from `/model/info`. If needed, edit `config/pricing.yaml` with your contracted rates:

```yaml
units: USD_per_token
models:
  EXACT_GATEWAY_MODEL_ID:
    input_cost_per_token: 0.000001       # example only; replace with your price
    output_cost_per_token: 0.000002      # example only; replace with your price
    cache_read_input_token_cost: 0.0000001
    cache_creation_input_token_cost: 0.00000125
    output_cost_per_reasoning_token: 0.000002
```

Rates are **USD per token**, displayed per million only. Do not copy example rates as actual prices. Missing cache rates make a rate-based total unavailable when cache tokens were used. Missing reasoning rates fall back to the output rate. Cache writes reported under multiple aliases must agree. Native Anthropic input counts are adjusted for separately reported cache tokens.

## Presenter run-book

1. **Round 1 — extraction:** choose two or three models, keep blind mode on, pull the lever. Read the answers and JSON checks first. Reveal identities and costs. Explore the volume presets; the ratio only uses complete, non-truncated, priced answers.
2. **Round 2 — upgrade value:** compare the churn-experiment analyses. Explain that the keyword rubric is a heuristic. Review the findings; use each check's “Mark pass/fail” button where warranted. Overrides retain the original decision and persist in history and recordings.
3. **Round 3 — prompt bloat:** select one model in Reel A. The app runs bloated and lean instructions on that model with a shared schema and grade. Repeat on other models for better tokenizer evidence. Reveal each run so the finale can use it.
4. **Record the rehearsal:** every completed, error-free live run is captured automatically, including timings and token events. Keep a revealed rehearsal for every round. For fallback, choose **Recorded replay**, select a captured run and pull. The RECORDED banner stays visible. Replay makes no model call and does not add variance or workflow evidence. No demo recordings ship with the app.
5. **Fix the bill:** the as-built synthetic workload sends eight documents through extraction, uses a six-turn full-history analysis agent, and retries a 20% failure rate until success. Adjust packets/day, models, documents, prompt bloat, history window, turns and retry policy. “Apply measured fixes” chooses the cheapest eligible model with at least one graded sample and all graded samples passing, trims context, removes bloat, and caps retries at one. Models matching `fix_excludes` are excluded from automatic selection. Review the quality badges and assumptions before presenting savings.

If a run cannot start and a recording exists for its task, the notice offers a replay shortcut. If the SSE connection drops, the client closes it rather than automatically duplicating tokens; check history for the server's completed result and use “Reveal result” or “View result”. One failed reel does not cancel the others.

## Honest accounting

- A positive gateway-reported cost is authoritative. Zero is accepted as proof of free only when explicit zero base rates and a usable zero rate estimate support it.
- Rate fallbacks use gateway rates, then the configured local table. Unavailable pricing is **never** displayed as $0.
- Reasoning is a subset of completion tokens: visible output plus reasoning equals total output. It is never added twice. Reasoning is not re-sent as visible conversation history.
- Gateway component headers are inclusive totals; calculated components are additive. Partial gateway components are never patched with estimates. Reconciliation and rate differences are shown explicitly.
- Truncation and missing finish reasons prevent content-failure grading. Unrevealed blind runs hide model, usage, cost and latency in SSE and history.
- Workflow evidence requires a complete, revealed, error-free, non-truncated, priced preset answer with valid token usage. Edited prompts and recorded playback are excluded. Prompt fingerprints keep different prompts out of the same variance bucket.
- Scaling preserves the measured charge's markup relative to list rates. An unmeasured model uses the median measured token profile with zero assumed reasoning, clearly marked as an estimate with unverified quality. Missing required evidence makes totals unavailable.
- Full agent context carries previous prompts plus visible outputs. Retry factors assume independent failures: unlimited `1/(1-r)`; capped `(1-r^(k+1))/(1-r)` where `k` is maximum retries. Rates are capped at 0.9. These are design estimates, not production forecasts.

## Configuration reconstructed from the source

The supplied [original app specification](APP_SPEC.md) is OCR-damaged and lacks usable model, pricing and workflow YAML. This implementation repairs Python/regex/YAML syntax and uses:

- Empty model defaults and local price tables, avoiding guessed model IDs and rates.
- A documented synthetic two-step workflow with 30 days/month, 10,000 packets/day, eight documents, six agent turns and a 20% retry rate. These defaults are editable in `config/workflow.yaml`.
- Reconstructed Round 2 keyword groups, including separate account-overlap and temporal-split findings.
- Reconstructed Round 3 prose around the stated FN-7310 schema, September 8, 2026 date, $7,258.50 loss, and absent police report. Both variants use the same facts and grading config.

The result is an operational interpretation of the damaged specification, not a verbatim recovery of the photographed originals.

## Execution time: measurement and estimation

Restart the server after updating and refresh the browser. No database migration is needed. Existing run records with valid timings become evidence automatically; older records without timings remain unavailable.

- **Measure a model:** pull the lever, then reveal. Each reel highlights measured end-to-end call time, alongside TTFT, gateway time and overhead. The completed run shows measured elapsed time across the concurrent reels, including orchestration and grading. This is measured directly rather than summing parallel call durations. Blind mode hides all timing metrics until reveal.
- **Review repeated measurements:** History shows mean, median, nearest-rank p95 and the number of timed pulls for each task/model/prompt group. Workflow steps show timing sample counts and mean TTFT. A small sample's p95 is descriptive, not a service guarantee; fewer than five observations produces a caution.
- **Project repeated calls:** the volume section multiplies the current valid call duration by the call count. This is a serial-execution estimate for an unchanged workload. It works even if the call's price is unknown.
- **Estimate the workflow:** “Fix the bill” compares as-built and current **execution time per packet** and shows aggregate model-call hours/day and /month. Run and reveal the extraction and leakage presets for each selected model. The document-concurrency control changes only the time estimate; it does not change the actual comparison run or its cost. Agent turns always execute sequentially.

Timing evidence is independent of pricing and token reports. It requires a successful request (regardless of content grade), a complete revealed run, an exact preset-prompt fingerprint, no truncation, and positive finite `total_ms`. Recorded playback never adds measurements. Genuine captured recordings can supply their original measurements when history is unavailable. Playback shows the original recorded call and run durations, not a new gateway measurement. Legacy recordings without run elapsed time show no run measurement.

Let `t` be a task/model's mean measured call duration, `a` the expected attempts from the retry controls, `n` the document count and `c` the document concurrency (limited to `n`). Estimated document-step elapsed time is `ceil(n/c) * t * a`. Sequential agent time is `turns * t * a`. Workflow elapsed time sums the sequential steps. Aggregate model-call time uses `n * t * a` for documents, so concurrency does not reduce total model-call hours. Daily/monthly totals multiply that aggregate by packet volume; they are not elapsed calendar time, utilization, compute-hours billed by the provider, or a throughput guarantee.

These are baseline-latency estimates, not latency derived from a price/token ratio. Model choice, call count, retry assumptions and concurrency change the projection. Prompt bloat, longer conversation history and trimming can affect real latency, but their effects are not inferred from cost or other tasks' token counts. The estimator holds baseline latency constant and labels this limitation. Parallel waves assume equal mean call durations; contention, retry stragglers, gateway queueing/rate limits, failure-duration differences, backoff, non-LLM processing and network changes are not modeled. Benchmark the actual workflow under target load to validate those effects.

API additions: workflow estimates include a top-level `timing` object and each step's `timing` object (seconds; observed statistics in milliseconds). `/api/workflow` model entries include `timed_steps`. History variance groups include `timing` statistics. Revealed run responses and non-blind completion events include `wall_ms`; unrevealed blind history/events exclude it. Missing timing values are null, never an assumed zero.

## Development & verification

```bash
uv run pytest
node --check web/app.js
```

Tests use `httpx.MockTransport`, temporary SQLite and recording paths; no network or credentials. They cover gateway discovery, streaming/deadlines, safe errors, cost accounting, strict grading, blind streams/history, isolated failures, replay without network, persisted overrides, evidence filters, workflow scaling, retry math, and probe redaction.

The server's HTML/API/static responses and JavaScript syntax were checked during implementation. Visual browser QA could not be performed in the development session because browser automation permissions were unavailable. Live gateway compatibility must be verified with your deployment using the probe.

Source is under `src/promptpriced`, configuration under `config`, frontend under `web`. Run from this source checkout: frontend and configuration are repository assets. The wheel packages the Python module; it is not a standalone bundle of the web/config directories.

`runs.db`, recordings, `.env`, and `.venv` are ignored. Storage can include your prompts and answers; this is a single-presenter localhost app. Keep the supplied loopback binding. The API key stays on the server, redirects are disabled, response headers are allow-listed, exceptions are sanitized, and UI data is created with `textContent`/DOM APIs. No grading answer keys or regex rubrics are sent to the browser.
