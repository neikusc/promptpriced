(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
  const state = { tasks: [], models: [], recordings: [], run: null, reels: new Map(), source: null, busy: false, workflow: null, config: null, seq: 0 };
  const money = (n, large = false) => {
    if (n === null || n === undefined || !Number.isFinite(n)) return '—';
    if (n < 0) return '−' + money(-n, large);
    if (large || n >= 1) return n.toLocaleString('en-US', {style:'currency', currency:'USD', maximumFractionDigits:large ? 0 : 2});
    return '$' + n.toFixed(n >= .01 ? 4 : n === 0 ? 2 : Math.min(12, Math.max(5, 3-Math.floor(Math.log10(n)))));
  };
  const duration = seconds => {
    if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return 'Unavailable';
    if (seconds < 1) return (seconds * 1000).toFixed(0) + ' ms';
    if (seconds < 60) return seconds.toFixed(2) + ' s';
    if (seconds < 3600) return (seconds / 60).toFixed(1) + ' min';
    return (seconds / 3600).toLocaleString('en-US', {maximumFractionDigits: 1}) + ' h';
  };
  function runStatus(wallMs) {
    $('run-state').textContent = 'Run complete' + (state.run?.recorded ? ' · RECORDED' : '') +
      (wallMs === null || wallMs === undefined ? '' : ' · ' + duration(wallMs / 1000) + ' measured elapsed');
  }
  const num = n => n === null || n === undefined ? '—' : Math.round(n).toLocaleString();
  const task = () => state.tasks.find(t => t.id === $('task').value);
  async function api(path, body) {
    const r = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    let data;
    try { data = await r.json(); } catch (_) { throw new Error('The server returned an unreadable response.'); }
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Check your selections.');
    return data;
  }
  function notice(text, action) {
    const box = el('div', undefined, 'notice'); box.append(el('span', text));
    if (action) { const b = el('button', action.label); b.addEventListener('click', () => { action.run(); box.remove(); }); box.append(b); }
    const close = el('button', '×'); close.setAttribute('aria-label','Dismiss notice'); close.addEventListener('click', () => box.remove()); box.append(close); $('notices').append(box);
  }
  function option(select, value, text) { const o = el('option', text); o.value = value; select.append(o); }
  function fillModels() {
    ['a','b','c'].forEach((id, i) => {
      const s = $('model-'+id); s.replaceChildren();
      if (i) option(s, '', '— none —');
      state.models.forEach(m => option(s, m.id, m.id + (m.pricing_known ? ` · ${money(m.input_per_million)} / ${money(m.output_per_million)} per 1M` : ' · pricing unknown')));
      if (!state.models.length && !i) option(s,'','No gateway models available');
      const selected = (state.defaults || [])[i] || (state.models[i] || {}).id;
      if (selected && [...s.options].some(o => o.value === selected)) s.value = selected;
    });
  }
  function fillRecordings() {
    const s = $('recording'), old = s.value; s.replaceChildren();
    const matching = state.recordings.filter(r => r.task_id === $('task').value);
    if (!matching.length) option(s, '', 'No recordings for this task');
    matching.forEach(r => option(s, r.id, new Date(r.created_at).toLocaleString() + ' · ' + (r.models.join(', ') || 'blind capture')));
    if (matching.some(r => r.id === old)) s.value = old;
  }
  function selectTask() {
    const t = task(); if (!t) return;
    $('task-description').textContent = t.description;
    $('task-meta').textContent = `${num(t.max_tokens)} maximum output tokens · ${t.variants ? '2 prompt variants, 1 model' : 'Up to 3 models in parallel'}`;
    $('prompt').value = t.prompt; $('variants').replaceChildren();
    (t.variants || []).forEach(v => { const box = el('details'); box.append(el('summary', v.label), el('pre', v.prompt)); $('variants').append(box); });
    $('variant-note').hidden = !t.variants;
    fillRecordings(); updateControls();
  }
  function updateControls() {
    const recorded = $('source').value === 'recorded', variant = !!task()?.variants;
    $('recording-label').hidden = !recorded;
    $('prompt').disabled = recorded || variant || state.busy;
    $('reset-prompt').disabled = recorded || variant || state.busy;
    ['a','b','c'].forEach((id,i) => { $('model-'+id).disabled = recorded || (variant && i > 0) || state.busy; });
    ['task','source','recording','blind'].forEach(id => { $(id).disabled = state.busy; });
    $('char-count').textContent = `${$('prompt').value.length.toLocaleString()} / 50,000 characters`;
    let reason = '';
    if (state.busy) reason = 'Run in progress…';
    else if (recorded && !$('recording').value) reason = 'Capture a successful live run first.';
    else if (!recorded && !$('model-a').value) reason = 'Configure your gateway to discover models.';
    else if (!recorded && !variant && !$('prompt').value.trim()) reason = 'Enter a prompt.';
    else if (!recorded && !variant) { const models = ['a','b','c'].map(id => $('model-'+id).value).filter(Boolean); if (new Set(models).size !== models.length) reason = 'Choose distinct models for each reel.'; }
    $('pull').disabled = !!reason; $('disabled-reason').textContent = reason;
    $('reveal').disabled = !state.run || !state.run.blind || !state.run.done || state.run.revealed;
  }
  function createReel(info, recorded) {
    const card = el('article', undefined, 'panel reel'), top = el('div', undefined, 'reel-heading');
    top.append(el('h3', info.label || 'Reel '+info.reel_id));
    const status = el('span','WAITING','badge'); top.append(status); card.append(top);
    if (info.variant) card.append(el('span', info.variant, 'badge'));
    if (recorded) card.append(el('span','RECORDED','badge accent-b'));
    const model = el('div', info.model || 'Model hidden until reveal', 'reel-model'); card.append(model);
    const spinner = el('div','✦ ◇ ✦','spinner'); spinner.setAttribute('aria-hidden','true'); card.append(spinner);
    const answer = el('pre','','answer'); answer.setAttribute('aria-label','Answer for '+info.reel_id); card.append(answer);
    const details = el('div'); card.append(details); $('reels').append(card);
    const reel = {id:info.reel_id,card,status,model,spinner,answer,details,result:null,pending:'',frame:null,done:false}; state.reels.set(info.reel_id,reel); return reel;
  }
  function appendToken(reel, text) {
    reel.pending += text;
    if (reel.frame) return;
    reel.frame = requestAnimationFrame(() => {
      const bottom = reel.answer.scrollTop + reel.answer.clientHeight >= reel.answer.scrollHeight - 35;
      reel.answer.append(document.createTextNode(reel.pending)); reel.pending = ''; reel.frame = null;
      if (bottom) reel.answer.scrollTop = reel.answer.scrollHeight;
    });
  }
  function renderResult(reel, result) {
    reel.result = result; reel.done = true; reel.spinner.hidden = true;
    if (reel.frame) cancelAnimationFrame(reel.frame); reel.frame = null; reel.pending = '';
    reel.answer.textContent = result.text || '';
    const grade = result.grade || {status:'ungraded',checks:[]};
    reel.status.textContent = result.error ? 'ERROR' : grade.status.toUpperCase(); reel.status.className = 'badge '+grade.status;
    reel.model.textContent = result.model || 'Model hidden until reveal'; reel.details.replaceChildren();
    if (result.error) reel.details.append(el('p',result.error,'callout'));
    if (result.truncated) reel.details.append(el('p','TRUNCATED — token limit or incomplete stream. Content was not graded.','callout'));
    if (!result.model && !result.error) reel.details.append(el('p','Cost, usage and latency hidden until reveal.','muted small'));
    if (result.model && Number.isFinite(result.total_ms)) {
      reel.details.append(el('p', duration(result.total_ms / 1000) + ' measured call time' + (state.run?.recorded ? ' · original recording' : ''), 'measured-time'));
    }
    if (result.cost) {
      const cost = result.cost, line = el('div',undefined,'cost-line');
      line.append(el('strong',cost.amount === null ? 'Pricing unavailable' : money(cost.amount),'cost-value'), el('span',cost.source,'badge'));
      const ratio = el('span','','badge ratio'); line.append(ratio); reel.details.append(line);
      const tokens = cost.tokens || {}, stats = el('div',undefined,'stats');
      [['Input',num(tokens.input)],['Output',num(tokens.output)],['Reasoning',num(tokens.reasoning)],['Visible output',num(tokens.visible_output)],['Cache read',num(tokens.cache_read)],['Cache write',num(tokens.cache_write)],['TTFT',num(result.ttft_ms)+' ms'],['Total',num(result.total_ms)+' ms'],['Gateway',num(result.gateway_ms)+' ms'],['Overhead',num(result.overhead_ms)+' ms'],['Finish',result.finish_reason || 'unknown']].forEach(([k,v]) => {const row=el('div');row.append(el('span',k),el('strong',v));stats.append(row);}); reel.details.append(stats);
      if (tokens.reasoning > 0) reel.details.append(el('p',tokens.visible_output === 0 ? `Paid for ${num(tokens.reasoning)} tokens of thinking and received zero visible words.` : `${num(tokens.reasoning)} reasoning tokens were billed as output but never shown.`,'callout'));
      const breakdown = el('details'); breakdown.append(el('summary','Cost breakdown'));
      Object.entries(cost.components || {}).forEach(([key,value])=>breakdown.append(el('p',key.replaceAll('_',' ')+': '+money(value),'small')));
      ['original_amount','discount_amount','margin_amount','margin_percent'].forEach(k => {if (cost[k] !== undefined) breakdown.append(el('p',k.replaceAll('_',' ')+': '+(k === 'margin_percent' ? cost[k]+'%' : money(cost[k])),'small'));});
      breakdown.append(el('p',cost.component_semantics || 'No component breakdown reported.','muted small'));
      if (cost.components_reconcile === false) breakdown.append(el('p','Component breakdown is incomplete or does not reconcile with the reported charge.','callout'));
      if (cost.rate_difference && Math.abs(cost.rate_difference)>1e-12) breakdown.append(el('p',`Gateway charge differs from rate estimate by ${money(cost.rate_difference)}. Gateway charge remains authoritative.`,'callout'));
      reel.details.append(breakdown);
    }
    const grades = el('details'); grades.open = true; grades.append(el('summary','Grade · '+grade.status));
    (grade.checks || []).forEach(check => {
      const row=el('div',undefined,'check'); row.append(el('span',check.passed?'✓':'×',check.passed?'pass':'fail'));
      const label=el('span',check.label+(check.overridden?' · reviewed':'')); if(check.detail) label.title=check.detail; row.append(label);
      const override=el('button',check.passed?'Mark fail':'Mark pass'); override.disabled=!!state.busy || grade.status==='truncated';
      override.addEventListener('click',async()=>{override.disabled=true;try{const r=await api(`/api/run/${state.run.id}/grade`,{reel_id:reel.id,check_id:check.id,passed:!check.passed});renderResult(reel,r);await refreshHistory();await loadWorkflow();}catch(e){notice(e.message);}finally{override.disabled=false;}});
      row.append(override); grades.append(row);
    });
    if (grade.summary) grades.append(el('p',grade.summary,'muted small')); reel.details.append(grades); updateProjections();
  }
  async function pull() {
    if (state.busy) return;
    state.busy=true; updateControls();
    try {
      const body={task_id:task().id,models:(task().variants?['a']:['a','b','c']).map(id=>$('model-'+id).value).filter(Boolean),prompt:$('prompt').value,blind:$('blind').checked,mode:$('source').value,recorded_run_id:$('recording').value || null};
      const run=await api('/api/run',body); state.run={id:run.run_id,blind:body.blind,revealed:!body.blind,done:false,recorded:run.recorded};
      state.reels.clear();$('reels').replaceChildren();run.reels.forEach(info=>createReel(info,run.recorded));
      $('recorded-banner').hidden=!run.recorded; $('run-state').textContent=run.recorded?'Playing recorded run…':'Streaming live…';
      if(state.source)state.source.close(); const source=new EventSource(`/api/run/${run.run_id}/events`);state.source=source;
      source.addEventListener('reel_start',event=>{const r=state.reels.get(JSON.parse(event.data).reel_id);if(r)r.status.textContent='STREAMING';});
      source.addEventListener('token',event=>{const d=JSON.parse(event.data),r=state.reels.get(d.reel_id);if(r)appendToken(r,d.text);});
      source.addEventListener('reel_done',event=>{const d=JSON.parse(event.data),r=state.reels.get(d.reel_id);if(r)renderResult(r,d.result);});
      source.addEventListener('error',event=>{
        if(event.data){const d=JSON.parse(event.data),r=state.reels.get(d.reel_id);if(r)renderResult(r,{text:r.answer.textContent+r.pending,error:d.message,grade:{status:'ungraded',checks:[]}});else notice(d.message);}
        else {source.close();state.busy=false;$('run-state').textContent='Connection lost';state.reels.forEach(r=>{if(!r.done)renderResult(r,{text:r.answer.textContent+r.pending,error:'Connection lost. Check history for the server result.',grade:{status:'ungraded',checks:[]}});});updateControls();refreshHistory();}
      });
      source.addEventListener('run_done',async event=>{source.close();state.busy=false;state.run.done=true;runStatus(JSON.parse(event.data).wall_ms);state.reels.forEach(r=>{if(r.result)renderResult(r,r.result);});updateControls();await refreshHistory();await loadWorkflow();await refreshBudget();});
    } catch(e) { state.busy=false; const matching=state.recordings.some(r=>r.task_id===task().id);notice(e.message,matching?{label:'Switch to recorded replay',run:()=>{$('source').value='recorded';updateControls();}}:null);updateControls(); }
  }
  async function reveal() {
    try {const data=await api(`/api/run/${state.run.id}/reveal`,{});state.run.revealed=true;runStatus(data.wall_ms);data.results.forEach(r=>{const reel=state.reels.get(r.reel_id);if(reel)renderResult(reel,r);});updateControls();await refreshHistory();await loadWorkflow();}catch(e){notice(e.message);}
  }
  function updateProjections() {
    const volume=Number(Number(10**Number($('volume').value)).toPrecision(2));$('volume-label').textContent=num(volume)+' calls';$('projections').replaceChildren();
    const priced=[...state.reels.values()].filter(r=>r.done&&!r.result?.error&&!r.result?.truncated&&r.result?.cost?.amount!==null&&r.result?.cost?.amount!==undefined);
    const lowest=priced.length?Math.min(...priced.map(r=>r.result.cost.amount)):null;
    state.reels.forEach(r=>{const row=el('div',undefined,'projection-row');row.append(el('span',`Reel ${r.id}`));const c=r.result?.cost?.amount;row.append(el('strong',r.result?.error?'Pricing unavailable — projection disabled':!r.result?.model?'Hidden until reveal':c===null||c===undefined?'Pricing unavailable — projection disabled':money(c*volume)));$('projections').append(row);
      if (r.result?.model && !r.result?.error && !r.result?.truncated && Number.isFinite(r.result?.total_ms)) {
        const timeRow = el('div', undefined, 'projection-row timing-projection');
        timeRow.append(el('span', `Reel ${r.id} · serial execution estimate`), el('strong', duration(r.result.total_ms / 1000 * volume)));
        $('projections').append(timeRow);
      }
      const ratio=r.details.querySelector('.ratio');if(ratio)ratio.textContent=priced.includes(r)&&lowest>0?(c/lowest).toFixed(1)+'× lowest':'';});
    const max=priced.length?Math.max(...priced.map(r=>r.result.cost.amount)):null;
    $('ratio-note').textContent=(priced.length>1&&lowest>0?`Complete, non-truncated priced reels: ${(max/lowest).toFixed(1)}× cost spread. `:'')+'Cost ratio says nothing about quality — read the grades.';
  }
  async function refreshBudget(){try{const b=await api('/api/budget');const known=b.spend!==null&&b.max_budget!==null&&b.max_budget>0;$('budget').hidden=!known;$('budget-text').textContent=known?`${money(b.spend)} / ${money(b.max_budget)} · ${Math.round(b.spend/b.max_budget*100)}% used`:'Budget unknown — gateway has not reported spend yet';if(known){const ratio=b.spend/b.max_budget;$('budget').value=Math.min(1,ratio);$('budget-text').className=ratio>=.95?'crit':ratio>=.8?'warn':'';}}catch(_) {}}
  async function refreshHistory(){
    const results=await Promise.allSettled([api('/api/history'),api('/api/recordings')]);
    if(results[1].status==='fulfilled'){state.recordings=results[1].value;fillRecordings();$('recordings-list').replaceChildren();state.recordings.forEach(r=>{const row=el('div',undefined,'history-item'),label=el('span',r.task_id+' · RECORDED');label.append(el('small',new Date(r.created_at).toLocaleString()));const b=el('button','Select replay');b.disabled=state.busy;b.addEventListener('click',()=>{$('task').value=r.task_id;selectTask();$('source').value='recorded';$('recording').value=r.id;updateControls();$('deck').scrollIntoView({behavior:'smooth'});});row.append(label,b);$('recordings-list').append(row);});if(!state.recordings.length)$('recordings-list').append(el('p','No recordings yet. Complete a live run to capture one.','muted small'));}
    if(results[0].status==='fulfilled'){const data=results[0].value;$('variance').replaceChildren();data.groups.forEach(g=>{const row=el('tr');[g.task_id+' / '+g.prompt_id,g.model,`${g.count} / ${g.priced_count}`,money(g.min),money(g.mean),money(g.max),g.min>0?(g.max/g.min).toFixed(2)+'×':'—',duration(g.mean_total_ms === null ? null : g.mean_total_ms / 1000), duration(g.timing ? g.timing.median_ms / 1000 : null), duration(g.timing ? g.timing.p95_ms / 1000 : null), g.timing ? String(g.timing.n) : '0'].forEach(v=>row.append(el('td',v)));$('variance').append(row);});if(!data.groups.length){const row=el('tr'),cell=el('td','No revealed live measurements yet.');cell.colSpan=11;row.append(cell);$('variance').append(row);}$('recent').replaceChildren();data.runs.slice(0,20).forEach(run=>{const row=el('div',undefined,'history-item'),label=el('span',run.task_id+(run.recorded?' · RECORDED':'')+(run.blind&&!run.revealed?' · BLIND':''));label.append(el('small',new Date(run.created_at).toLocaleString()));row.append(label);if(run.complete){const b=el('button',run.revealed?'View result':'Reveal result');b.disabled=state.busy;b.addEventListener('click',async()=>{if(state.source)state.source.close();state.run={id:run.id,blind:run.blind,revealed:run.revealed,done:true,recorded:run.recorded};state.reels.clear();$('reels').replaceChildren();$('recorded-banner').hidden=!run.recorded;try{const data=await api(`/api/run/${run.id}/reveal`,{});data.results.forEach(r=>{const reel=createReel({reel_id:r.reel_id,model:r.model,variant:r.variant},run.recorded);renderResult(reel,r);});state.run.revealed=true;runStatus(data.wall_ms);updateControls();await refreshHistory();await loadWorkflow();}catch(e){notice(e.message);}});row.append(b);}$('recent').append(row);});if(!data.runs.length)$('recent').append(el('p','Your first pull starts the story.','muted small'));}updateControls();
  }
  function control(parent,label,type,value,change,attrs={}){const wrapper=el('label',label),input=el('input');input.type=type;input.value=value;Object.entries(attrs).forEach(([k,v])=>input.setAttribute(k,v));input.addEventListener('input',()=>{change(type==='checkbox'?input.checked:Number(input.value));scheduleEstimate();});wrapper.append(input);parent.append(wrapper);return input;}
  function wfSelect(parent,label,value,options,change){const wrapper=el('label',label),s=el('select');options.forEach(([v,t])=>option(s,v,t));s.value=value;s.addEventListener('change',()=>{change(s.value);scheduleEstimate();});wrapper.append(s);parent.append(wrapper);return s;}
  let timer=null;
  function scheduleEstimate(){clearTimeout(timer);const seq=++state.seq;timer=setTimeout(()=>estimateDesign(seq),150);}
  async function loadWorkflow(){try{const data=await api('/api/workflow');state.workflow=data;if(!state.config)state.config=structuredClone(data.as_built);$('workflow-empty').hidden=true;$('workflow-content').hidden=false;renderWorkflowControls();await estimateDesign(++state.seq);}catch(e){$('workflow-empty').textContent='Workflow unavailable. '+e.message;}}
  function renderWorkflowControls(){
    const root=$('workflow-controls');root.replaceChildren();const c=state.config,w=state.workflow;
    control(root,'Packets per day','number',c.workflows_per_day,v=>c.workflows_per_day=v,{min:1,max:10000000});
    w.steps.forEach(step=>{const group=el('fieldset');group.append(el('legend',step.label));root.append(group);const sc=c.steps[step.id];
      const models=[...w.models].sort((a,b)=>Number(b.measured_steps.includes(step.id))-Number(a.measured_steps.includes(step.id))||a.id.localeCompare(b.id));
      wfSelect(group,'Model',sc.model,models.length?models.map(m=>[m.id,m.id+' · '+(m.measured_steps.includes(step.id)?'measured':m.pricing_known?'estimate':'no pricing') + (m.timed_steps?.includes(step.id) ? ' · timing measured' : ' · no timing')]):[['','No models available']],v=>sc.model=v);
      if(step.kind==='batch'){control(group,'Documents per packet','number',sc.calls,v=>sc.calls=v,{min:1,max:200});control(group,'Concurrent documents (time estimate)','number',sc.concurrency ?? 1,v=>sc.concurrency=v,{min:1,max:200});const check=control(group,'Bloated prompt','checkbox','',v=>sc.bloated_prompt=v);check.checked=sc.bloated_prompt;check.parentElement.className='toggle';}
      else{control(group,'Agent turns','number',sc.turns,v=>sc.turns=v,{min:1,max:50});const ctx=wfSelect(group,'Conversation context',sc.context,[['full','Full history'],['window','Trimmed window']],v=>{sc.context=v;windowInput.disabled=v!=='window';});const windowInput=control(group,'Previous turns kept','number',sc.window_turns,v=>sc.window_turns=v,{min:0,max:50});windowInput.disabled=ctx.value!=='window';}
    });
    const retry=el('fieldset');retry.append(el('legend','Retries'));root.append(retry);const rateLabel='Failure rate: '+Math.round(c.retry_rate*100)+'%';const r=control(retry,rateLabel,'range',c.retry_rate,v=>{c.retry_rate=v;r.parentElement.firstChild.textContent='Failure rate: '+Math.round(v*100)+'%';},{min:0,max:.6,step:.01});
    wfSelect(retry,'Maximum retries',c.max_retries===null?'unlimited':String(c.max_retries),[['unlimited','Retry until success'],['0','0'],['1','1'],['2','2'],['3','3']],v=>c.max_retries=v==='unlimited'?null:Number(v));
  }
  function animateMoney(node,value){const previous=Number(node.dataset.value || 0);node.dataset.value=value===null?'':String(value);if(value===null){node.textContent='Unavailable';return;}if(matchMedia('(prefers-reduced-motion: reduce)').matches){node.textContent=money(value,true);return;}const start=performance.now();const version=String(value);function frame(now){if(node.dataset.value!==version)return;const p=Math.min(1,(now-start)/450);node.textContent=money(previous+(value-previous)*(1-(1-p)**3),true);if(p<1)requestAnimationFrame(frame);}requestAnimationFrame(frame);}
  async function estimateDesign(seq){if(!state.workflow)return;try{const current=await api('/api/workflow/estimate',state.config);if(seq!==state.seq)return;renderEstimate(current);}catch(e){if(seq===state.seq){$('design-total').textContent='Unavailable';['baseline-time','design-time','execution-work','time-savings'].forEach(id=>$(id).textContent='Unavailable');$('savings').textContent='Choose models and valid values for all steps. '+e.message;}}}
  function renderEstimate(current){
    const baseline=state.workflow.estimate;animateMoney($('baseline-total'),baseline.monthly);animateMoney($('design-total'),current.monthly);
    if(current.available&&baseline.available){const diff=baseline.monthly-current.monthly;$('savings').textContent=`${diff>=0?'Save':'Increase by'} ${money(Math.abs(diff),true)} / month${baseline.monthly>0?' · '+Math.abs(diff/baseline.monthly*100).toFixed(1)+'%':''} · ${money(Math.abs(diff)*12,true)} / year`;}else $('savings').textContent='Complete and reveal Rounds 1–3 to ground this estimate. Unknown pricing or missing evidence keeps totals unavailable.';
    const bt = baseline.timing, ct = current.timing;
    $('baseline-time').textContent = duration(bt.per_workflow_seconds);
    $('design-time').textContent = duration(ct.per_workflow_seconds);
    $('execution-work').textContent = ct.available ?
      `Aggregate model-call time: ${duration(ct.daily_model_call_hours * 3600)} / day · ${duration(ct.monthly_model_call_hours * 3600)} / month. Concurrent calls overlap; these hours are not elapsed calendar time.` :
      'Timing unavailable: run and reveal the preset for each selected model. Timing does not require known prices.';
    if (bt.available && ct.available) {
      const delta = bt.per_workflow_seconds - ct.per_workflow_seconds;
      $('time-savings').textContent = `${delta >= 0 ? 'Estimated time saved' : 'Estimated time added'}: ${duration(Math.abs(delta))} / packet. Baseline call latency is held constant; model and concurrency choices drive this estimate.`;
    } else $('time-savings').textContent = 'Execution estimates use measured mean latency. Missing measurements remain unavailable.';
    $('step-bars').replaceChildren();current.steps.forEach(s=>{const b=baseline.steps.find(x=>x.id===s.id),box=el('div',undefined,'step-comparison');box.append(el('h3',s.label));const max=Math.max(b.monthly||0,s.monthly||0,1);[[b,'As built',false],[s,'Your design',true]].forEach(([v,label,isCurrent])=>{const row=el('div',undefined,'step-label');row.append(el('span',label),el('span',money(v.monthly,true)+' / month'));const track=el('div',undefined,'bar-track'),bar=el('div',undefined,'bar'+(isCurrent?' current':''));bar.style.width=(v.monthly===null?0:v.monthly/max*100)+'%';track.append(bar);box.append(row,track);});const badges=el('div',undefined,'step-badges');[s.model||'No model',s.basis,s.quality,`${s.calls} ${s.unit}s / packet`].forEach(t=>badges.append(el('span',t,'badge')));box.append(badges,el('p',`${money(s.per_call)} / ${s.unit} · ${num(s.tokens.input)} input / ${num(s.tokens.output)} output tokens per packet`,'small muted'));const timing = s.timing, observed = timing.observed;
      box.append(el('p', `Execution estimate: ${duration(timing.per_workflow_seconds)} / packet · ${duration(timing.per_call_seconds)} / call · ${timing.waves} sequential waves · concurrency ${timing.concurrency}`, 'small timing-summary'));
      if (observed) box.append(el('p', `Observed: n=${observed.n} · median ${duration(observed.median_ms / 1000)} · p95 ${duration(observed.p95_ms / 1000)} · mean TTFT ${duration(observed.mean_ttft_ms === null ? null : observed.mean_ttft_ms / 1000)} (n=${observed.ttft_n}). These are sample statistics, not an SLA.`, 'small muted'));
      const notes=el('ul');[...s.notes, ...timing.notes].forEach(n=>notes.append(el('li',n)));box.append(notes);$('step-bars').append(box);});
    $('assumptions').replaceChildren();[state.workflow.description,`${state.workflow.days_per_month} days/month; ${num(current.workflows_per_month)} packets/month.`,`${current.attempts_per_call.toFixed(3)} expected attempts per call, assuming independent failures at the chosen rate.`,`Rate source: ${state.workflow.rates_source}. Estimates preserve measured markup when scaling with known rates.`,`Cost evidence requires complete, revealed, priced preset runs. Edited prompts and playback do not add measurements.`,`Prompt bloat requires paired Round 3 evidence. Context trimming and retry policy quality impacts are not measured.`,`Timing uses successful, complete, revealed preset runs even when pricing is unknown. No latency is inferred from a price card.`, `Workflow steps and agent turns run sequentially; document calls use the selected concurrency in equal-duration waves. Parallel estimates omit stragglers, contention, queueing, rate limits and retry backoff.`, `Prompt/context changes do not reduce estimated call latency without workload-specific evidence. Monthly model-call hours count overlapping calls separately.`, `Cost projections exclude infrastructure, taxes, human review and production workload variation.`].forEach(t=>$('assumptions').append(el('li',t)));
  }
  async function init(){
    $('pull').addEventListener('click',pull);$('reveal').addEventListener('click',reveal);$('task').addEventListener('change',selectTask);$('source').addEventListener('change',updateControls);$('recording').addEventListener('change',updateControls);$('prompt').addEventListener('input',updateControls);['a','b','c'].forEach(id=>$('model-'+id).addEventListener('change',updateControls));$('reset-prompt').addEventListener('click',()=>{$('prompt').value=task().prompt;updateControls();});$('volume').addEventListener('input',updateProjections);$('volume-presets').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{$('volume').value=Math.log10(Number(b.dataset.volume));updateProjections();}));$('refresh-history').addEventListener('click',async()=>{await refreshHistory();await loadWorkflow();});$('workflow-reset').addEventListener('click',()=>{state.config=structuredClone(state.workflow.as_built);renderWorkflowControls();scheduleEstimate();});$('workflow-fix').addEventListener('click',()=>{state.config=structuredClone(state.workflow.fix);renderWorkflowControls();scheduleEstimate();});
    try{state.tasks=await api('/api/tasks');state.tasks.forEach(t=>option($('task'),t.id,t.title));selectTask();}catch(e){notice(e.message);return;}
    try{const data=await api('/api/models');state.models=data.models;state.defaults=data.defaults;}catch(e){notice(e.message);}
    fillModels();updateControls();await refreshHistory();await refreshBudget();await loadWorkflow();
  }
  init().catch(()=>notice('The app could not initialize. Check server availability.'));
}());
