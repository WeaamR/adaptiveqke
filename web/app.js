(() => {
  'use strict';
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];
  const state = { meta:null, mode:'replay', device:'High-performance', network:'Low-latency', session:null, comparison:null, compareMetric:'wire_latency_ms', running:false };

  const fmt = (v, unit='', digits=1) => {
    if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '—';
    return `${Number(v).toLocaleString(undefined,{minimumFractionDigits:digits,maximumFractionDigits:digits})}${unit}`;
  };
  const unrestricted = v => v === null || v === undefined ? 'Unrestricted' : v;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const clamp = (x,a,b) => Math.max(a,Math.min(b,x));

  function toast(msg, error=false){
    const t=$('#toast'); t.textContent=msg; t.className=`toast show${error?' error':''}`;
    clearTimeout(toast.timer); toast.timer=setTimeout(()=>t.className='toast',4400);
  }

  async function api(url, opts={}){
    const res=await fetch(url,{headers:{'Content-Type':'application/json'},...opts});
    let body=null; try{body=await res.json();}catch{body={detail:res.statusText};}
    if(!res.ok) throw new Error(body.detail||`Request failed (${res.status})`);
    return body;
  }

  function profileButton(type,p,selected){
    const isDevice=type==='device';
    const specs=isDevice
      ? [`<span>CPU <b>${p.cpu_share_pct==null?'Unlimited':p.cpu_share_pct+'%'}</b></span>`,`<span>RAM <b>${p.memory_mb==null?'Unlimited':p.memory_mb+' MB'}</b></span>`]
      : [`<span>Delay <b>${p.delay_ms} ms</b></span>`,`<span>Rate / Loss <b>${p.rate_mbit}M · ${p.loss_pct}%</b></span>`];
    return `<label class="profile-card ${selected?'selected':''}" data-${type}="${p.name}">
      <input type="radio" name="${type}" value="${p.name}" ${selected?'checked':''}>
      <span class="profile-icon">${p.short}</span><strong>${p.name}</strong><small>${isDevice?p.class_label:p.rtt_region+' modeled region'}</small>
      <span class="profile-spec">${specs.join('')}</span></label>`;
  }

  function renderSelectors(){
    $('#deviceCards').innerHTML=state.meta.device_profiles.map(p=>profileButton('device',p,p.name===state.device)).join('');
    $('#networkCards').innerHTML=state.meta.network_profiles.map(p=>profileButton('network',p,p.name===state.network)).join('');
    $$('[data-device]').forEach(el=>el.addEventListener('click',()=>{if(state.running)return; state.device=el.dataset.device; refreshSelection();}));
    $$('[data-network]').forEach(el=>el.addEventListener('click',()=>{if(state.running)return; state.network=el.dataset.network; refreshSelection();}));
    refreshSelection();
  }

  function getDev(){ return state.meta.device_profiles.find(p=>p.name===state.device); }
  function getNet(){ return state.meta.network_profiles.find(p=>p.name===state.network); }

  function refreshSelection(){
    $$('[data-device]').forEach(el=>{const on=el.dataset.device===state.device;el.classList.toggle('selected',on);$('input',el).checked=on;});
    $$('[data-network]').forEach(el=>{const on=el.dataset.network===state.network;el.classList.toggle('selected',on);$('input',el).checked=on;});
    const d=getDev(),n=getNet();
    $('#selectedSummary').textContent=`${state.device} · ${state.network}`;
    $('#envDevice').textContent=d.name; $('#envCpu').textContent=d.cpu_share_pct==null?'Unrestricted':`${d.cpu_share_pct}%`; $('#envMem').textContent=d.memory_mb==null?'Unrestricted':`${d.memory_mb} MB`;
    $('#envNetwork').textContent=n.name; $('#envDelay').textContent=`${n.delay_ms} ms · ${n.rate_mbit} Mbit`; $('#envLoss').textContent=`${n.loss_pct}%`;
    clearResults(false);
  }

  function renderGroups(selected=''){
    $('#groupCards').innerHTML=state.meta.groups.map(g=>`<article class="crypto-group ${g.openssl_name===selected?'selected':''}">
      <div class="tier">${g.tier}</div><h4>${g.label}</h4><p>${g.role}</p>
      <dl><dt>NIST level</dt><dd>${g.security_level}</dd><dt>Classical</dt><dd>${g.classical}</dd><dt>PQ component</dt><dd>${g.pqc}</dd></dl>
    </article>`).join('');
  }

  function setStage(index,status='active'){
    $$('.step').forEach((el,i)=>{el.classList.toggle('done',i<index);el.classList.toggle('active',i===index);});
    const ids=['environment','context','policy','group','tls','metrics'];
    ids.forEach((id,i)=>{const badge=$(`#${id}State`); if(!badge)return; if(i<index){badge.textContent='DONE';badge.className='stage-state done';} else if(i===index){badge.textContent=status==='running'?'RUNNING':'ACTIVE';badge.className=`stage-state ${status==='running'?'running':''}`;} else {badge.textContent='WAITING';badge.className='stage-state';}});
  }

  function clearResults(resetStepper=true){
    if(state.running) return;
    state.session=null; state.comparison=null;
    if(resetStepper)setStage(0);
    ['ctxRtt','ctxCpu','ctxMem','probeCost','classifiedDevice','candidateGroup','finalGroupMini','policyCost','metricSize','metricCpu','metricHandshake','metricWire','firstCost','costProbeLabel','costWireLabel'].forEach(id=>$('#'+id).textContent='—');
    $('#stage1Rule').textContent='Waiting for measured RTT…'; $('#stage2Rule').textContent='Waiting for device classification…';
    $('#rttMarker').style.left='0%'; $('#rttMarkerLabel').textContent='RTT'; $('#cpuMarker').style.left='0%'; $('#memMarker').style.left='0%';
    $('#tlsClientGroup').textContent='selected group'; $('#secureChannel').classList.remove('success'); $('#secureStatus').textContent='Awaiting session';
    $('#tinyPolicyCost').textContent='Policy: —'; $('#costProbeBar').style.width='50%'; $('#costWireBar').style.width='50%';
    $('#comparisonChart').innerHTML='<p class="empty-state">Run a session to load the matching recorded baselines.</p>';
    renderGroups('');
  }

  function renderMode(){
    $$('.mode-btn').forEach(b=>b.classList.toggle('active',b.dataset.mode===state.mode));
    const n=$('#liveNotice'); const pf=state.meta.live;
    if(state.mode==='live'){
      n.classList.remove('hidden');
      if(pf.ready){n.classList.add('good');n.innerHTML='<b>Live Lab ready.</b> The server will call the project implementation and perform one actual TLS 1.3 handshake.';}
      else{n.classList.remove('good');n.innerHTML='<b>Live Lab is not ready on this machine.</b> '+pf.reasons.join(' ');}
    } else {n.classList.add('hidden');}
  }

  function updateRttScale(rtt){
    const max=150, pos=clamp(rtt/max*100,1,99); $('#rttMarker').style.left=`${pos}%`; $('#rttMarkerLabel').textContent=fmt(rtt,' ms',1);
  }
  function updateResources(cpu,mem){
    $('#policyCpu').textContent=cpu==null?'Unrestricted':fmt(cpu,'%',0); $('#policyMem').textContent=mem==null?'Unrestricted':fmt(mem,' MB',0);
    $('#cpuMarker').style.left=cpu==null?'96%':`${clamp(cpu,0,100)}%`;
    $('#memMarker').style.left=mem==null?'96%':`${clamp(mem/512*100,0,100)}%`;
  }

  function renderSession(s){
    state.session=s;
    const c=s.context,p=s.policy,m=s.metrics;
    $('#sourceBadge').textContent=s.source_label; $('#sourceBadge').className=`source-badge ${s.mode}`;
    $('#ctxRtt').textContent=fmt(c.probed_rtt_ms,' ms',1); $('#ctxCpu').textContent=c.cpu_share_pct==null?'∞':fmt(c.cpu_share_pct,'%',0); $('#ctxMem').textContent=c.mem_limit_mb==null?'∞':fmt(c.mem_limit_mb,' MB',0);
    $('#probeCost').textContent=fmt(c.probe_cost_ms,' ms',3); $('#classifiedDevice').textContent=c.classified_device;
    updateRttScale(Number(c.probed_rtt_ms)); updateResources(c.cpu_share_pct,c.mem_limit_mb);
    $('#stage1Rule').textContent=p.stage1_rule; $('#candidateGroup').textContent=`Candidate · ${p.candidate_meta.tier}`;
    $('#stage2Rule').textContent=p.stage2_rule; $('#finalGroupMini').textContent=`Final · ${p.final_meta.tier}`;
    $('#policyCost').textContent=fmt(c.policy_cost_ms,' ms',3); renderGroups(s.selected_group);
    $('#tlsClientGroup').textContent=s.selected_group; $('#secureChannel').classList.toggle('success',m.success); $('#secureStatus').textContent=m.success?(s.mode==='replay'?'Recorded success flag':'Client reported success'):'Client reported failure';
    $('#metricSize').textContent=fmt(m.handshake_size_bytes,' B',0); $('#metricCpu').textContent=fmt(m.cpu_time_ms,' ms',1); $('#metricHandshake').textContent=fmt(m.handshake_latency_ms,' ms',1); $('#metricWire').textContent=fmt(m.wire_latency_ms,' ms',1); $('#firstCost').textContent=fmt(m.first_connection_cost_ms,' ms',1);
    const probe=Number(c.probe_cost_ms)||0, wire=Number(m.wire_latency_ms)||0,total=probe+wire||1; $('#costProbeBar').style.width=`${Math.max(8,probe/total*100)}%`; $('#costWireBar').style.width=`${Math.max(8,wire/total*100)}%`;
    $('#costProbeLabel').textContent=fmt(probe,' ms',1); $('#costWireLabel').textContent=fmt(wire,' ms',1); $('#tinyPolicyCost').textContent=`Policy: ${fmt(c.policy_cost_ms,' ms',3)}`;
  }

  async function loadComparison(){
    state.comparison=await api(`/api/compare?device=${encodeURIComponent(state.device)}&network=${encodeURIComponent(state.network)}`); renderComparison();
  }
  function metricUnit(metric){return metric==='handshake_size_bytes'?' B':' ms';}
  function metricDigits(metric){return metric==='handshake_size_bytes'?0:1;}
  function renderComparison(){
    if(!state.comparison)return; const rows=state.comparison.rows, metric=state.compareMetric;
    const vals=rows.map(r=>Number(r[metric])||0),max=Math.max(...vals,1);
    $('#comparisonChart').innerHTML=rows.map(r=>{const v=Number(r[metric])||0,g=r.group_meta||{};return `<div class="comparison-row ${r.config==='Adaptive'?'adaptive':''}">
      <div class="comparison-label"><b>${r.config}</b><small>${g.tier?`Group ${g.tier}`:'—'}</small></div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2,v/max*100)}%"></div></div>
      <div class="comparison-value">${fmt(v,metricUnit(metric),metricDigits(metric))}</div>
      <div class="comparison-level">NIST L${g.security_level??'—'}</div></div>`;}).join('');
  }

  async function runSession(){
    if(state.running)return; clearResults(true); state.running=true; $('#startBtn').disabled=true; $('#startBtn span').textContent='SESSION RUNNING…'; setStage(0,'running');
    const payload={mode:state.mode,device:state.device,network:state.network}; let pending;
    try{
      pending=api('/api/session',{method:'POST',body:JSON.stringify(payload)});
      await sleep(330);setStage(1,'running');await sleep(430);setStage(2,'running');
      const result=await pending;
      renderSession(result);setStage(3,'running');await sleep(360);setStage(4,'running');$('#tlsStage').classList.add('running');await sleep(720);$('#tlsStage').classList.remove('running');setStage(5,'running');await loadComparison();await sleep(320);setStage(5);$$('.step').forEach((e,i)=>{if(i<5)e.classList.add('done')});$('#metricsState').textContent='DONE';$('#metricsState').className='stage-state done';toast(result.mode==='live'?'Live attempt returned; see recorded status.':'Recorded dataset replay loaded.');
      $('#metricsStage').scrollIntoView({behavior:'smooth',block:'center'});
    }catch(err){setStage(0);toast(err.message,true); if(state.mode==='live'&&!state.meta.live.ready) state.mode='replay';}
    finally{state.running=false;$('#startBtn').disabled=false;$('#startBtn span').textContent='START ADAPTIVE SESSION';}
  }

  function sandboxOutputs(){
    $('#sandboxRttOut').textContent=`${$('#sandboxRtt').value} ms`; $('#sandboxCpuOut').textContent=$('#sandboxCpuUnlimited').checked?'Unrestricted':`${$('#sandboxCpu').value}%`; $('#sandboxMemOut').textContent=$('#sandboxMemUnlimited').checked?'Unrestricted':`${$('#sandboxMem').value} MB`;
    $('#sandboxCpu').disabled=$('#sandboxCpuUnlimited').checked; $('#sandboxMem').disabled=$('#sandboxMemUnlimited').checked;
  }

  async function runSandbox(ev){
    ev.preventDefault(); const body={rtt_ms:Number($('#sandboxRtt').value),cpu_share_pct:$('#sandboxCpuUnlimited').checked?null:Number($('#sandboxCpu').value),mem_limit_mb:$('#sandboxMemUnlimited').checked?null:Number($('#sandboxMem').value)};
    try{const r=await api('/api/policy',{method:'POST',body:JSON.stringify(body)}),p=r.policy; $('#sandboxResult').innerHTML=`<div class="trace"><div><span>Stage 1 · ${p.stage1_rule}</span><b>Candidate ${p.candidate_meta.tier}</b></div><i>→</i><div><span>Stage 2 · ${p.stage2_rule}</span><b>Final <strong>${p.final_meta.tier}</strong></b></div></div>`;}catch(e){$('#sandboxResult').textContent=e.message;}
  }

  function bind(){
    $$('.mode-btn').forEach(b=>b.addEventListener('click',()=>{if(b.disabled)return;state.mode=b.dataset.mode;renderMode();}));
    $('#startBtn').addEventListener('click',runSession);
    $$('.metric-tab').forEach(b=>b.addEventListener('click',()=>{$$('.metric-tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.compareMetric=b.dataset.metric;renderComparison();}));
    $('#sandboxOpen').addEventListener('click',()=>$('#sandboxDialog').showModal()); $('#sandboxClose').addEventListener('click',()=>$('#sandboxDialog').close());
    ['sandboxRtt','sandboxCpu','sandboxMem','sandboxCpuUnlimited','sandboxMemUnlimited'].forEach(id=>$('#'+id).addEventListener('input',sandboxOutputs)); $('#sandboxForm').addEventListener('submit',runSandbox); sandboxOutputs();
  }

  async function init(){
    try{state.meta=await api('/api/meta');$('#statRows').textContent=Number(state.meta.dataset.rows).toLocaleString();renderSelectors();renderGroups();
      const liveBtn=$('#liveModeBtn'); if(!state.meta.live.ready){liveBtn.title=state.meta.live.reasons.join(' ');} renderMode();bind(); clearResults(true);
    }catch(e){toast(`Could not initialize: ${e.message}`,true);}
  }
  init();
})();
