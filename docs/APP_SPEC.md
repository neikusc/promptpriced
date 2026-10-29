# Same Prompt. Different Price. — Consolidated App-Building Prompt

> **Transcription notice:** Reconstructed from 14 photographed screenshots in original order. Text extraction is best-effort and **not verified verbatim**. Small text, YAML indentation, regex escapes, punctuation, and code symbols may contain transcription errors. Screenshots overlap; some duplicated lines may remain. Review against the originals before executing this as a development specification.

<!-- Source screenshot IMG_9773.jpg -->

ha | tT
| ROLE
You are a senior Python + vanilla-JS engineer. Build, from an empty directory, a complete, tested, local web app called "Same Prompt. Different Price." (package slotmachine , project name medel-stot-machine }. Work
iteratively: scaffold > implement module by module > write tests > run uv run pytest until green > write README. Do not stop at a skeleton; every feature below must work, Do not invent features that are not specified.
WHAT THE APP IS
Asingle-presenter, localhost "slot machine" for live talks about LLM cost. The presenter picks a preset task and up to 3 madels available on a company LiteLLM gateway (OpenAl-compatible AP), "pulls the lever", and the
same prompt streams from every model at once, each Into its own "reel". In blind mode the model names, costs, usage and latency stay hidden until the presenter clicks Reveal. Every answer is graded automatically: exact
JSON checks, or a keyword-pattern rubric that the presenter can override. The app shows a projection of cost at volume, run history with variance, and a ‘replay mode that plays back recorded runs when the gateway isdown. «
A finale panel called "Fix the bill" takes the measured per-call costs and projects them onto a made-up claims-triage application, with design levers the presenter can change.
siaaserrers
Core principle (enforce it everywhere): honest numbers. Missing pricing is "unavailable", never $0. Reasoning tokens are a SUBSET of completion tokens and must never be added twice. Truncated answers are never graded
as content failures. Replays are always labelled RECORDED. Estimates are labelled as estimates.
STACK & HARD CONSTRAINTS
cerzte:
Python >=3.12, managed with uv . Use a sre/ layout with the hatchling build backend ( [tool. hatch. build: target's, wheel] packages=["src/slotmachine”| ).
Runtime dependencies: fastapi>=0.115, uvicorn>=0.34, httpx>=0.28, pydantic-settings>=2.7, pyyaml>=
["tests"] .
0. Dev dependency group: pytest>=8, pytest-asyncio>=0.25. Pytest settings: asyncio_mode="auto" , testpaths=
Frontend: plain web/index.html , web/app.js (an lIFE in strict mode, no framework, no build step) and. wéb/styles.css , served by FastAPI at / and /static .
* Runcommand: uv run uvicorn slotmachine.app:app ——host 127.0.0.1 —port 8000.
* Persistence: SQLite runs.db (history) and fixtures/recorded_runs.json (recordings). Both, plus’ .env and) .vehv,, goin .gitignore . Shipa .env.example .
Security (OWASP): the API key never leaves the server. Never put upstream URLS, keys, response bodies or arbitrary exception strings into API responses, SSE events or logs. Use foltow_redirects=False . Pass through only
an allow-list of response headers. Build all DOM with textContent / createElement and never with innerHTML for data. Never send answer keys or rubrics to the browser.
All rates are USD per token internally. Display them per 1M tokens only.
REPO LAYOUT
Pyproject.toml README.md .env.example .gitignore
config/models.yaml config/pricing.yaml config/workf low. yamt
Config/tasks/extraction.yaml config/tasks/leakage.yaml config/tasks/prompt_bloat. yaml
scripts/probe.py
sr¢/stotmachine/{__init_,app,config,grading, history, litellm_client,archestrator,pricing, recorded, tasks, workflow}. py
tests/{test_app, test_gateway, test_grading, test_pricing, test_workf low}. py
web/{index. html, app. js,styles.css}
CONFIG FILES (create verbatim)
config/models.yaml
defaults: i { i §

<!-- Source screenshot IMG_9774.jpg -->

tas!
it reasons over the packet for
Prompt_bloat
ng claim packet has its documents ex:
wi rkflowyam!

<!-- Source screenshot IMG_9775.jpg -->

max_tokens: 4096
prompt: | i
Extract this synthetic claim into a single JSON object, with exactly these keys:
claim_id (string), policyholder (string), loss_date (YYYY-MM-DD),
Feported_date (YYYY-MM-DD), cause (string), estimated loss_usd {number) ,
deductible_usd (number), injuries (integer), police_report_id (string! or null).
Use null for an explicitly absent police report. Do not invent information.
Return JSON only, without commentary.
Synthetic claim FN-2048: Policyholder Avery Morgan reported the)/claim on
March 16, 2026. A burst pipe damaged the kitchen on March 14, 2026.
The recorded cause is “water damage". The repair estimate! is $18,450.75;
the policy deductible is $1,0@0, No one was injured: (@ injuries).
No police report was filed.
grading:
type: json
exact_keys: true
fields:
Claim_id: {type: string, expected: FN-2048}
policyholder: {type: string, expected: Avery Morgan}
loss_date: {type: date, expected: “2026-03-14"}
reported _date: {type: date, expected: "2026-03-16"}
cause: {type: string, expected: water damage}
estimated loss_usd: {type: number, expected: 18450.75, tolerance: 0.01}
deductible_usd: {type: number, expected: 1000, tolerance: @.01}
injuries: {type: integer, expected: @}
police_report_id: {type: string, expected: null}
config/tasks/leakage.yam!
id: leakage
title: "Round 2 — When is the upgrade worth it?"
description: “Diagnose a synthetic churn experiment. Grading is a transparent keyword heuristic, not an authoritative evaluation; presenter review is encouraged.“
max_tokens: 8192
prompt: |
Review this synthetic churn experiment and recommend what to fix before rollout.
Be concise but explicit about each distinct problem and how to validate again.
At the start of each month, we predict whether an account will cancel during
the next 30 days. Only 1% of account-months churn. We trained on monthly
Snapshots, randomly splitting rows 88/20, so the same account, can appear in
both sets. Features include account tenure, payment history, and cancellation
date, populated after cancellation. Test accuracy is 99%, The team proposes
2 rollout based on that accuracy alone.
=grading:
type: rubric
Findings:
= id: target_leakage
_- label: “Cancellation date leaks post-outcome information"
: any_of: i
= UNbeancel(?:lation|ed|1ed)7(7: [_ ~Idate|\s+date)\b', '\b( leak\wt|post(~ Joutcome| future information|after (isthe )?(?:outcome|event| cancellation) )\b"):
=-f\b(target|label|outcome) leakage\b’, '\b(cancel\we|post[- Joutcome)\b') | Rea es
= UXbpopulated\b', "\bafter\b', ‘\b(7:churn leancellation)\b*} |
exclude patterns: ae
‘b(nofwithout)\s+(?:target\s+)?leakage\b'

<!-- Source screenshot IMG_9776.jpg -->

\b(no|without)\s+(?:target\s+) ?leakage\b* ‘
(2:does not|doesn. t/cannot|can.t)\s+(?:cause\s+)?leak\b' i
“Use a forward-time holdout for SEN
\b(temporal|chronological| forward {- 1¢
‘{'\btrain\b‘, '\b(?:earlier|past)\b', | '\b( later |future)\b',
f*\bhotd[— Jout\b", "\bmonth\b*, "\bpredict\b', ‘\busing data (3
clude_patterns:
‘*\b(?:do notjdon.t{no need to)\s+(?: ieenels a\s4)7(7- temporal |chrotelogital
accuracy baseline wih
; “99% accuracy equals the always—non-churn Majority baseline’
1*\b99\s¥%", ‘\b(baseline|majority|non[— l?ehurnfnol= T?churn{nevel eehurn)\s
-_— {'\baccuracy\b', ‘\o(misleading|uninformative|imbalan\we|not Sufficient|not enou
exclude_patterns:
= "\baccuracy is (?:sufficient|enough|reliable)\b'
2 useful_metrics
label: “Evaluate minority-class performance and decision weit
any_of:
~ [*\bprecision\b', '\brecall\b']
= {"\b(?:pr{- j?auc|auc{- ]?prjaverage precision|precision[— Irec Ly\b! ]
~ = ['\b(?:lift|recail at|precision atjcost[- ]sensitive|expected.
exclude_patterns:
‘\b(?: ignorejavoid{do not use|don,t use)\b*
fig/tasks/prompt_bloat.yaml
a YAML anchor &lean , and the lean variant reuses it via ‘rlean|.
eapest token is the one you never send ||| i
model, same synthetic eat ain exac

<!-- Source screenshot IMG_9777.jpg -->

or @); a list of fields NOT to add; the exact schema line; the same source narrative
as the lean prompt; and a closing "final reminder" that restates everything.>
~ id: lean
label: "Lean instructions"
Prompt: *lean
grading: | t
type: json Hit i
exact_keys: true \
fields:
Claim_id: {type: string, expected: FN-7310}
loss_date: {type: date, expected: “2026-09-08"}
estimated _loss_usd: {type: number, expected: 7258.50, tolerance: @.@1}
police_report_id: {type: string, expected: nuli}
BACKEND MODULES
config.py
| * ROOT = Path{__file__).resolve{).parents[2] .
* pydantic-settings Settings: env_file=ROOT/"-env" , extra="ighore!. Fields: liteltmapi bases! sth! = '1) | utelimapiikey: stri= tt, request _timeout: float = 18@, database_path: Path
/ * Module singleton settings .
Ly
pricing.py (all rates USD per token)
* ‘number(v) : returns a float, or None for bool, None, non-numeric, non-finite or negative values. Accepts numeric strings (from headers).
* RATE_ALTASES maps each canonical key to its accepted alias names:
© input_cost_per_token
© output_cost_per_token
© cache_read_input_token_cost (+ cache_read_input_cost_per_token }
© cache_creation_input_token_cost (+ cache _creation_input_costiper_token,, cache write input! token cost )
© output_cost_per_reasoning token (+ reasoning cost_per_token.)
* ‘normalize rates(r) : returns all 5 canonical keys. A key's value is set only if every alias present agrees; any conflict makes it None.
* load_tocal_rates(path=None) : reads config/pricing.yaml. Raises ValueEtror unless \units = “USD, per ‘token’. Returns {model: normalized}.
* ‘usage_tokens(usage) : normalizes OpenAl- and Anthropic-style usage into {input, output, cache read, ‘cache write, reasoning, Visible output} -
© input = prompt_tokens or input tokens ; output = completion tokens. or output tokens .
© Details come from prompt_tokens_details / input_tokens details) and completion tokens details) / output tokens details), A details value that is not a dict > None.
© Cache_read = details.cached i_tokens , else usage. cached. tokens), else icache.read input tokens , else 0.
© cache _write: take the candidates (details cache write tokens , detalls cache _creation_tokens , Usage |cache!write!'tokens|, cache_creation tokens , cache_creation. _input_tokens ). ee tel max if they are
valld'and at most one distinct positive value exists (LiteLLM can report one value under two names). Otherwise > None,
"© feasoning comes from the completion details or usage, default 0.
Every Value must be a valid integer.
Native Anthropic shape ( input _tokens present, no Prompt tokens , NO Anput tokens details ): add read + write'to input, because that shape excludes cache tokens.
Return None if anythingis invalid, if read + write > input, or if reasoning > output,
visible. Output = output feasoning.
"rated(usage, rat additive components innitinon-eache). cache read cache write. autout(visible). reasoning:

<!-- Source screenshot IMG_9778.jpg -->

* _rated(usage, rates) : additive components input(non-cache), cache_read
© Reasoning uses the reasoning rate if known, else the output rate.
© A component with an unknown rate is 0.0 if its count is 0, otherwise None.
© The total is None if either base rate {inputfoutput) is unknown or any component is None,
Fesolve_cost(Usage, headers, rates=None, local_rates=None) returns dict with amount.
i, Lower-case the headers. Copy these into the result when they parse: original_amount,
response-cost—{original, discount-amount, margin-amount,margin-
, cache_write, output(visible), reasoning.
. + source ("gateway” |“rates'|"Local table" |"unavailabte), components, tokens .
discount_amount, margin_amount, margin_percent, input_amount,
percent, input, output, toal-usage} t
ii. Compute rate estimates in priority order: (“rates", gateway rates), then
excludes reasoning", output_total, reasoning subset} .
output_amount, too1_usage amount from x-litellm
("local table", local). The first usable ane becomes rate_estimate + {amount, source, Components, Component_semantics: "additive; output
iil, Gateway candidates, in order: Usage. cost , then header x-litel lm
Fesponse-cost . Accept a candidate if > 0, or if itis 0 AND the usable estimate is 0 AND both base rates are exactly 0 ("
= When accepted: source="gateway".
Zero is hot proof of free").
= If gateway component headers exist: components. = their {input, output, tool_usage},
reasoning” , components_complete (input & output both Present),
= Otherwise, if there is a usable rate estimate, use its components wit!
Components sources"gateway"', component _semantics="inclusive totals; input includes cache; output includes
components total, and components. reconcile via math.isclose(rel 1e-9, abs 1e-12).
h that source and reconcile them against the gateway amount.
= Set rate_difference = gateway — estimate when an estimate exists,
= Never fill partial gateway components with estimates,
iv. If no gateway amount is accepted, use the first calculated estimate with a non-None amount (components _reconcile=True).
v. Otherwise return “unavailable”.
* project _cost(amount, runs) : runs mustbea non-negative integer. Returns None for an unknown amount and raises on overflow. Alias ‘project = project_cost . k
litelim_client.py
* GatewayError(RuntimeError) : its message is always safe to render (no URL, key or body).
» “ALLOWED HEADERS : x-litelim-response-cost plus the -input, -output, ~original, -tool-usage, -discount~amount,
vmangin-amount, -margin-percent variants; x-litellm-response-duration—ms , x-Liteltm-key=
spend, x-litellm-key-max-budget .
* ‘LiteLLMClient{settings) :
© Uses an httpx.AsyncClient with a Bearer auth header, the timeout, and follow_redirects=False.
© ‘self.budget = {spend, max_budget} is updated from the key-spend headers. A header that is missing keeps the previous value.
° check : raises GatewayError("Gateway request failed (HTTP n).") on an error or redirect status.
° Fa callis wrapped in asyncio.timeout( request_timeout) ; this total deadline also bounds an active stream. Map timeouts, httpx errors and parse errors to generic GatewayErrors with from None .
° discover_madels() :
= GET {base}/models and {base}/model/info ; each must be {"data":[...]}-
= Keep only info entries whose model_name appears in the /models ids. Group deployments by model_name.
= Drop a model unless EVERY deployment has model_info.mode == “chat -
+ Normalize each deployment's rates. A canonical rate counts only if all deployments agree} if they conflict it is None (never pick one arbitrarily),
* Return alist sorted by id of {id, input_per million, output_per.million, pricing known, rates} .
=Peytoad: Model, ‘messages=[{role:user, content:prompt}]), max_tokens, stream. When streaming, add stream options={" include usage''s true} -
© stream(model, prompt, max_tokens) :
= Async generator over POST /chat/completions .
* Parse SSE by hand: collect data: lines and dispatch them on a blank ling; data can be fragmented across lines. Stop at | {DONE} |.
* A packet with an errar) key raises GatewayError. Merge any usage dict.
* Yield {'type":*token'')*text":_..} for each choices (0) delta. content , recording time to first token,
Tile be

<!-- Source screenshot IMG_9779.jpg -->

= Finish with {*typ: result":...} built by result .
i = The stream ended properly if a finish_reason was seen; otherwise mark it truncated.
© complete(...) : the same call without streaming.
© result builds {model, text, usage, headers, finish_reason, ttft_ms, total_ms, gateway_ms (from duration header), overhead_ms=max(@,total-gateway), truncated} . truncated is true if finish_reason is in
{length, max_tokens, max_output_tokens} or the stream did not end properly.
grading.py
* grade(task, text, finish_reason) returns {status, passed, checks, summary} :
© status is “pass” | "fail" | "truncated" | "ungraded"; passed is True/False/None.
© Eachcheckis {id, label, passed, detail}.
© Afinish_reason in {length, max_tokens, max_output_tokens, ™max_completion_tokens, token_limit, model_length} (case-insensitive) > "truncated", with no checks.
JSON grading:
E © Strip a single ** ‘json fence if present.
© json. loads with a duplicate-key-rejecting object_pairs hook anda parse_constant that rejects NaNj/Infinity.
© Malformed JSON or a non-object > fail with a single "json" check.
© Otherwise add a "json" pass check, then a "keys" check (no extra fields) if exact_keys , then one check per field.
* Field matching:
© Anull expected value requires a null value, and the reverse. hk
° date: parse ISO date, ISO datetime (Z>+00:00), %m/xd/xv + %B %d, %Y, OF %b %d, %y , then compare dates.
© number/integer: the type must be exactly int or float (bool is not a number), finite, and integral for integer. Compare with Decimal(str()) and an inclusive tolerance.
© boolean: is comparison. string: exact match.
© Field details are "Required field is missing." / “Value or type does not match.",
* Rubric grading:
© Remove + and backticks. Split into sentences on (2<5[. 171) \s+|\ne .
¢ A finding matches if SOME sentence matches no exclude_pattern AND ALL patterns of SOME | any: of group (case-insensitive).
© Summary: "Heuristic rubric only, not an authoritative evaluation; presenter review may override findings."
* No grading config > "ungraded".
tasks.py
* load_tasks() : reads config/tasks/*.yami sorted. Requires keys {id,title, description, prompt,max_tokens, grading} and rejects duplicate ids. Each call returns fresh copies.
* ‘get_task(id) : raises KeyError if not found.
history.py
= SQLite table runs(id TEXT PK, created at TEXT, payload TEXT JSON) , Upsert on save. get(id) ; list(1imit=10@) ordered by created_at DESC.
* now() returns a UTC ISO timestamp.
* ‘public result(result, hidden) : when hidden, keep only text, grade, truncated, variant, error.
* ‘public_run(run) : drops reels and events, and hides results while the run is blind and not yet revealed,
* variance_groups{runs) :
© Skip recorded runs, unrevealed blind runs, and errored or truncated results,
© Bucket hy task id modell" | "variantl nramnt id or 'ladaew!)
1A eRe

<!-- Source screenshot IMG_9780.jpg -->

Leen ee nnn en ee en ee ene en a ene ee a een ee nn NE re OT OEE | 5 Lad! GSPY Fei Les OCR ree ee
© Bucket by (task_id, model[+" / "+variant], prompt_id or "legacy").
© Return count, priced_count, min/max/mean cost and mean_total_ms per bucket.
recorded.py
* Recordings(path) provides all() , get(id) and summaries() (newestfirst: {id, task_id, created_at, models} ).
* ‘capture(run) stores only genuine completed live runs: not recorded, with a result for every reel, and no errors.
© Replace any entry with the same id.
© Keep the last 30.
© Write atomically: write a .tmp file, then replace.
orchestrator.py — Runner(client, history, recordings)
* runs isan in-memory dict. jobs holds asyncio Tasks.
* ‘start(task, models, prompt, blind, source=None, rates=None) builds the reels:
© Replay: deep-copy the source reels.
© Variant task: one reel per variant on models[0] , {reel_id:"A"/"B", model, variant: label, prompt: variant.prompt} .
© Otherwise one reel per model, shuffled with random.SystemRandom when blind.
Arunis {id:uuid4, created_at, task_id, blind, revealed: not blind, recorded: bool(source), reels, results:[], events:[], complete:False} . Schedule _execute .
* emit appends {event, data, at: monotonic offset} . x
* _execute :
© Replay: sleep through the original at gaps and re-emit the events, skipping run_done. Then copy the results.
© Live: gather one _reel per reel.
© Onan unexpected error, log it and emit a generic "error".
© finally : set complete=True, emit run_done {run_id, recorded} , save to history, and capture when the run was live.
° <-reel:
© Emit reel_start, then a token event per streamed token.
e Onthe result: set prompt_id = sha256(prompt){:12] and resolve the cost with the gateway rates and local rates. Grade it, add the variant if any, append to results, and emit reel_done {reel_id, result}.
© Ifno result arrives, raise.
© On any exception, log only the type name. Append a sanitized error result |{text:"", model, error:'Model request failed. Check gateway availability or server logs.", grade:
{Status:"ungraded”, passed:None, checks: [],summary:"Request failed."}} and emit error {reel_id, message} .
© One failing reel must not affect the others.
* ‘events(run, after=-1) : an async generator that yields (index, name, data) from the event lag, polling every 0.04s until the run is complete. Pass the data of each reel_done event through public result while the runis
blind and not revealed.
* close() cancels and awaits all jobs.
workflow.py — "Fix the bill" estimator
* load workflow() , prompt_id() (sha256[:12]), MAX_RETRY_RATE = 0.9
evidence -runs(history, recordings) : recordings first, then history runs override by id. Skip history runs with recorded=True (playback is not a new measurement).
collect_samples(runs, tasks) returns {task id: {variant_id|None: {model: [sample] }}} .
© Use only runs that are complete AND revealed.
° Use only results that have no error, are not truncated, have cost.tokens , and have a finite amount >= 0.

<!-- Source screenshot IMG_9781.jpg -->

© Theresult's prompt_id must match the preset prompt, or one of the task's variant prompts (which maps to that varia! !). Edited prompts are excluded,
° Asampleis {run_id, cost, passed (only when grade.status is pass/fail, else None), input, visible output, reasoning}.
* profile(samples) : means of cost/input/visible_output/reasoning, plus n, passed and graded counts.
* ‘rated(rates, in, out, reasoning-@) : inxi + {out-reasoning)*o + reasoningx(r or o) . Returns None if either base rate is unknown,
* expected_attempts(r, k) :
© Clamp rto (0, 0.9). r==0> 1.
© Uncapped: i/(1-r) . Capped: (4-ro(k+1))/(1-r) -
© ‘carried turns(turns, context, window) : "full" > turns(turns~1)//2 ; otherwise ¥.{keturns} min(k,) window).
* €stimator(workflow, samples, rates) :
© ‘measured(task, model, variant=None) returns. profile. median profite(task) gives the median input/visible output across models, with reasoning 0,
© ‘call_cost(task, model, input_fn, callse1):
= When measured:
= If calls == 1 and the new input equals the base input, return the measured Cost exactly.
= Otherwise return base.cost * rated(new_in, out»calls, reasoningxcalls) / rated (base), which keeps the gateway's observed markup over list rates. Basis is “measured”
= When not measured: rate-card on the median profile, basis "estimate",
= Unknown pricing > (None, "unavailable").
© quality() returns "x/y passed", or “unverified".
° prompt_bloat_tokens(step) :
= Delta = median over models of bloated.input — lean.input, using the prompt_evidence. task variants. ns
= Also returns the lean pass totals.
© batch_step (when bloated):
= Per-model input = base.input + deltaxbase. input/median’ input’, which adjusts the delta for each model's tokenizer.
= Add the note “Bloated prompt adds ~N input tokens per call (measured in Round 3; tokenizer-adjusted|estimate)."
| = If the prompt is lean and lean evidence exists, add the note "Lean prompt held quality in Round 3: x/y passed.”
= If bloated but no evidence exists > the step is unavailable.
| ° agent_step :
| = Conversation input= turns+in + carried«(in + visible output)|; reasoning is not re-sent.
: = Cost uses calis=turns. per_call = total/turns.
= Add a note for full history or for the trimmed window ("quality impact not measured").
° Each step dictis {id, label, unit,model,basis, per_call,cost_per_workflow, calls, tokens{input, output}, quality, notes}.
= Prepend “No measurement for this model: rate-card estimate, quality unverified." or "Pricing unavailable for this model." when it applies.
© estimate(config) :
Multiply each step by the expected attempts.
* per_month = workflows_per_day * days_per_month.
= Return |{available, per_workflow, monthiy, yearly, workflows permonth, attempts per_call, steps(+monthly)} .
* lf any step is unavailable, the totals are None.
* “build rates(models, tacal) : local rates, overridden by discovered gateway rates. workflow context (history, recordings, models, local) returns an Estimator.
app.Py (FastAPI, lifespan builds client/history/recordings/runner; app. state .models=| ])
Pydantic bodies:
* RunRequest{task_
ist<=3, prompt<=50k chars, blind=True, made: "live" |"recorded", recorded (run id?})

<!-- Source screenshot IMG_9782.jpg -->

[5 saaval [5 Leaning f Finance [9 subdivision (4 gen-ai (4 FditableavM [9 tricks [5 git
kerelated [5 Market
ive""|"recorded", recorded_run_id?}
* RunRequest{task_id, models: list<=3, prompt<=50k chars, blind=True, mode
© GradeRequest{reel_id, check_id, passed}
WorkflowStepConfig{model 1..200 chars, calls 1..2007, bloated prompt, turns 1,.507, context "full"|"window", window turns @,.5@ = 2}
WorkflowConfig{workflows_per_day 1..1e7, retry_rate @..0.9, max_retries 0..10|None, steps}
Endpoints:
* GET / serves web/index.html; /static serves webj.
* GET /api/models :
© Discovery result + defaults from models. yaml. Cache it in app.state.models .
© On failure: 502 "Cannot discover gateway models. Check .env and gateway connectivity; recorded mode is still available."
© GET /api/tasks : the tasks without grading, answer_key or rubric .
* GET /api/budget , GET /api/recordings -
* POST /api/run :
© 404 if the task is unknown.
© Recorded mode: 404 if the recording is missing, 422 if it belongs to another task.
© Live mode: 422 if there are no models, duplicate models, a madel outside the discovered chat list (discover lazily), or an empty prompt on a task without variants.
o Returns {run_id, recorded, reels: [{reel_id, label:"Reel X", model only if not blind, variant?}1} .
* GET /api/run/{id}/events :
© SSE(id:, event: , data: ) with headers no-cache and 'X-Accel-Buffering: no.
© Supports Last-Event-ID ; a non-numeric value > 400. Stops when the client disconnects.
© Looks the run up in memory, then in history.
POST /api/run/{id}/reveal : 409 until complete. Sets revealed and saves. Returns full results.
« POST /api/run/{id}/grade :
© 409 until complete, and also for truncated or ungraded results,
© Keep original passed , set passed and overridden=True , and recompute the overall grade with summary "Presenter-reviewed result (override recorded). Save the run so the override persists.
« GET /api/history: {runs: public_run[], groups: variance_groups} .
* GET /api/workf low :
© Try discovery, but keep working offline with recordings + the local rate table.
e Returns title, description, days_per_month, steps, as_built, and models. The model list is the discovered ids (or rate-table ids) plus any measured models; each entry is {id, pricing _known, measured steps}
© Alsoreturns fix, rates_source ("gateway” | “local table) and the as-built estimate).
* fixed_design:
© Start froma deep copy of as_built and set max_retries=1,
© For each step, pick the cheapest measured model whose graded measurements ALL passed (with at least one graded), excluding fix_excludes’ substrings.
© Agent steps get context="window”; batch steps get bloated_prompt=False.
= POST /api/workflow/estimate : validate that every step is present and has turns (agent) or'calls (batch), then return the estimate (422 otherwise).
scripts/probe.py i
* ACL that prints a redacted JSON capability report and exits 0 or 1,
+ Discovery only by default; this is free,
* model 1D opts into one billable streaming call with the prompt "Reply with the word ready," ( —-max-tokens|, default 1024, must be > 1).
Precise adds anon-streaming call and requires --model .

<!-- Source screenshot IMG_9783.jpg -->

Discovery oni fault; this is free.
* model ID opts into one billable streaming call with the prompt "Reply with the word ready.” (—-max-tokens , default 1024, must be >= 1).
e precise adds anon-streaming call and requires --model .
* Never print prompts, generated text, endpoints, keys or raw header values. Print header names only, plus usage numbers, resolved cost, timings and visible_characters.
FRONTEND (web/)
Dark "casino terminal" look:
« €SS variables: bg #07090f, panel rgba(18,24,40,.82), text #e6ebf5, mint #5eeac4, amber #fbbf24, violet #a78bfa, red #87171, green #4ade80, radius 16px.
« Radial gradient background with a faint grid overlay.
* One accent color per reel A/B/C.
* Respect prefers—reduced-motion . Accessible labels, aria-live regions and a skip link.
Sections:
1. Top bar
© Title "Same Prompt. Different Price.".
© Budget meter (role=meter) from japi/budget: warn at =80%, crit at 295%.
© When unknown, show "Budget unknown — gateway has not reported spend yet".
2. Banners and notices
© A persistent RECORDED banner and a dismissible notices area.
© When a run fails to start and a recording exists for the task, the notice offers a "Switch to recorded teplay" action:
3. Deck
© Selects for task, source (Live gateway / Recorded replay) and recording; task description and meta; 3 model selects (B and'C can be "— none —"; each option shows $in/$out per 1M or “pricing unknown").
© A prompt textarea with a character count and "Reset to preset".
© For variant tasks: disable the prompt, show variant preview cards, use only the Ree! A model, and explain this in a nate.
© Ablind toggle (default on).
° Ananimated lever button “Pull the lever" with the disabled reason shown below it.
© "Reveal models & cost" is enabled only when the run is blind, done and not yet revealed.
4. Reels (cards)
¢ Aspinning symbol strip while waiting. Tokens append in batches via requestAnimationFrame, auto-scrolling only if the reel was already at the bottom.
© Status badge, plus variant, truncated and recorded badges.
° Model label shows "Mode! hidden until reveal" while blind.
© After done:
» Cost with a source badge (gateway / rates / local table) and "Nx lowest" ratio.
= Stats: input, output, reasoning, visible and cache-read tokens; TIFT, total, gateway and overhead times; finish reason,
= Areasoning callout: "Paid for N tokens of thinking and received zero visible words," on\"N reasoning tokens were billed as output but never shown."
= A truncated warning.
=A collapsible cost breakdown: components, Mmargin/discount, semantics text, a\reconcile warning, and a warning when the rate estimate differs from the gateway amount.
™™ Acgtade section: pass/fail badge and a v/x check list. Each check has a "Mark pass/fail! override button that calls POST /grade.
© Use the native EventSource . Ona connection-level error, close it (do NOT auto-reconnect, which would replay tokens) and fail the reels that are still pending,
§. Volume projection
ee Log slider over 1070:.10°6, round:
‘0 2 significant figures, with presets A/KOK/100K/1M,

<!-- Source screenshot IMG_9784.jpg -->

§. Volume projection
° Log slider over 10%0..10%6, rounded to 2 significant figures, with presets 1/1K/10K/100K/1M.
o One row per reel: cost x N, or "Hidden until reveal” / "Pricing unavailable — projection disabled".
© Ratio note covering only complete, non-truncated, priced reels, ending with "Cost ratio says nothing about quality — read the grades."
6. Fix the bill
© Controls:
= Packets/day.
= Extract: model select (sorted measured-first, tagged measured / estimate / no pricing), documents per packet, bloated toggle,
=) Analysis agent: model, turns, context (full / window), N kept (disabled unless window). | Hi
= Retries: failure-rate slider 0-0.6 and retry cap ("Retry until success", 0-3),
© Debounce changes by 150ms and POST them. Ignore stale responses using a sequence number.
© Display:
= "As built - per month" vs "Your design - per month", with an ease-out count-up animation.
= Asavings line: monthly, %, and yearly.
= Per-step dual bars (as built vs current), with badges for model, basis, quality and units, per-call| cast, token counts and notes.
= An assumptions list.
© Buttons: "Reset to as built” and "Apply measured fixes".
7. History & variance
© Variance table: task, model, pulls, min, mean, max, spread (max/min) and mean time.
© Recent pulls (20).
© Recorded replays list with "Select replay".
8. Footer explaining the cost-source badges and that missing pricing is never $0.00.
Money formatting:
* > $1: locale currency. > $0.01: 4 decimals. Smaller amounts: enough significant decimals.
¢ Large monthly totals: no cents.
¢ Unknown values show “—" or “pricing unavailable”.
TESTS (no network, no credentials; use httpx.MockTransport and a tmp SQLite/fixtures path)
Write focused tests covering at least:
* pricing
© A nonzero gateway cost is authoritative.
© A gateway zero Is not proof of free {itis accepted only with explicit 0 rates).
© Cache and reasoning are not double-counted; a distinct reasoning rate is used,
° Acache rate that is missing while cache tokens were used > unknown!
* Falls back to the local table.
6 Inconsistent usage > unrated,
° NaN, negative and boo! costs are rejected,
© Margin and discount metadata are kept; projection works,
Native Anthropic cache input is handled.
Partial nateina ill

<!-- Source screenshot IMG_9785.jpg -->

© Inconsistent usage > unrated.
NaN, negative and bool costs are rejected.
and discount metadata are kept; projection works.
Anthropic eache input is handled. :
Partial gateway components are not filled with estimates; a
The total deadline bounds an active eel
© Probe is discovery-only by default and redacted.
: » Errors are safe to render and do not affect other reels.
grading
Task contract; fenced JSON; normalized dates.
Malformed or non-object JSON fails; types are strict (boolsint, "null"'¢null, THlesibe al
Extra keys are rejected; tolerance boundary is inclusive; overflowed numbers fall ait
Truncated answers are never failed on content; no grading config > ungraded.
Both bloat variants share one grade.
Rubric: case-insensitive, handles negations and unrelated sentences, neces alternati re
* app
Independent reels: blind runs hide data in the stream and history until reveal.
A failure is isolated and sanitized.
A genuine recording replays without network.
prompt_bloat runs two variants on the same model:
Validation errors, including a missing recording,
ison persists; ise persist with sestiiln pas.

<!-- Source screenshot IMG_9786.jpg -->

8 Bom bloat variants sh
Oe Bloat scales by the rate ratio.
-e Context re-sends prompts and visible output but hot rea ni
© Retry attempt formula.
e Unknown pricing > unavailable (not 0).
o An —— model > estimate with unverified aualiy,
- Connection troubleshooting via probe. py. i
A presenter run-book: Rounds 1-3, recorded fallback, and the Fix the bill final
