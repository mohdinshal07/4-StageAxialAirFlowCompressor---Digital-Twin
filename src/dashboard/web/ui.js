'use strict';
/* =====================================================================================================
   ui.js: views, controls, KPI tiles, deviation panel, charts, records (db), uploads and exports.
   ===================================================================================================== */
const $ = s => document.querySelector(s), $$ = s => Array.from(document.querySelectorAll(s));
const fmt = (v, d = 2) => v == null || !isFinite(v) ? '–' : (+v).toLocaleString(undefined, {minimumFractionDigits: d, maximumFractionDigits: d});
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
function toast(msg){ const t = $('#toast'); t.textContent = msg; t.classList.add('on'); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('on'), 2600); }
readTokens();
try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', readTokens); } catch (e) {}
new MutationObserver(readTokens).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});

/* ------------------------------------------------------------------ capabilities (db, user, downloads, assets) */
const CAP = {db: null, user: null, dl: null, assets: null, canWrite: true, ready: false};
const REC = {experiments: [], checklist: [], datasets: [], design: null, memDatasets: []};
(async () => {
  if (!window.claude || !window.claude.use){ setStorageNote(); return; }
  const [db, user, dl, assets] = await Promise.all(['db', 'user', 'downloads', 'assets'].map(n => window.claude.use(n).catch(() => null)));
  Object.assign(CAP, {db, user, dl, assets, ready: true});
  if (user && user.can){ try { const w = await user.can('data.write'); if (w === false) CAP.canWrite = false; } catch (e) {} }
  setStorageNote();
  if (db) subscribeAll();
})();
function setStorageNote(){
  const msg = !CAP.db ? 'Saving is not available in this view: entries stay until the page reloads.' : !CAP.canWrite ? 'You can view the records; your sharing level does not allow changes.' : '';
  ['#lg-status', '#design-status'].forEach(s => { const el = $(s); if (el && msg) el.textContent = msg; });
  if (!CAP.canWrite) $$('#log-form button[type=submit], #ck-form button, #design-save, #ds-delete').forEach(b => b.disabled = true);
}
function subscribeAll(){
  const db = CAP.db, timer = setTimeout(() => { $('#lg-status').textContent = 'The record store is not answering yet; entries may be out of date.'; }, 10000);
  db.collection('experiments').orderBy('created_at', 'desc').limit(500).onSnapshot(s => { clearTimeout(timer); REC.experiments = s.docs.map(d => Object.assign({id: d.id}, d.data())); renderLog(); }, err => console.warn(err));
  db.collection('checklist').orderBy('order').onSnapshot(s => { REC.checklist = s.docs.map(d => Object.assign({id: d.id}, d.data())); renderChecklist(); }, err => console.warn(err));
  db.doc('design/reference').onSnapshot(s => { REC.design = s.exists ? s.data() : null; renderDesignForm(); }, err => console.warn(err));
  db.collection('datasets').orderBy('uploaded_at', 'desc').limit(40).onSnapshot(s => { REC.datasets = s.docs.map(d => Object.assign({id: d.id}, d.data())); renderDatasetSelect(); }, err => console.warn(err));
}
async function save(filename, data, label){
  if (CAP.dl){ try { await CAP.dl.save({filename, data}); toast(`Saved ${filename}`); return; } catch (e){ if (e && e.code === 'declined') return; } }
  if (typeof data === 'string') showText(label || filename, data); else showImage(label || filename, data);
}
function showText(title, text){
  const m = document.createElement('div'); m.className = 'modal';
  m.innerHTML = `<div class="box"><div class="card-h"><h2>${esc(title)}</h2><button class="btn sm" type="button">Close</button></div><p class="small muted" style="margin-bottom:8px">Downloads are not available in this view. Select the text and copy it.</p><textarea readonly></textarea></div>`;
  m.querySelector('textarea').value = text; m.querySelector('button').onclick = () => m.remove(); m.onclick = e => { if (e.target === m) m.remove(); };
  document.body.appendChild(m); m.querySelector('textarea').select();
}
function showImage(title, blob){
  const m = document.createElement('div'); m.className = 'modal'; const url = URL.createObjectURL(blob);
  m.innerHTML = `<div class="box"><div class="card-h"><h2>${esc(title)}</h2><button class="btn sm" type="button">Close</button></div><img alt="${esc(title)}" src="${url}" style="width:100%;border:1px solid var(--line);border-radius:6px"></div>`;
  m.querySelector('button').onclick = () => m.remove(); document.body.appendChild(m);
}
async function copyText(text, what){
  try { await navigator.clipboard.writeText(text); toast(`${what} copied`); } catch (e){ showText(what, text); }
}

/* ------------------------------------------------------------------ routing */
function route(){
  const v = (location.hash || '#twin').slice(1), ok = ['twin', 'compare', 'log', 'checklist', 'rom', 'report'].includes(v) ? v : 'twin';
  $$('.view').forEach(s => s.classList.toggle('on', s.id === 'view-' + ok));
  $$('.tabs a').forEach(a => a.setAttribute('aria-current', a.dataset.view === ok ? 'page' : 'false'));
  VIEW = ok; if (ok === 'rom') renderRomPage(); if (ok === 'report') renderReport(); if (ok === 'compare'){ renderDesignForm(); renderDatasetSelect(); }
  setTimeout(() => renderCharts(true), 30);
}
let VIEW = 'twin';
window.addEventListener('hashchange', route);

/* ------------------------------------------------------------------ controls */
function bindRange(id, out, f, setter){ const el = $(id); const upd = () => { const v = +el.value; $(out).textContent = f(v); setter(v); }; el.addEventListener('input', upd); upd(); }
bindRange('#in-n', '#v-n', v => `${v.toLocaleString()} rpm`, v => S.Nman = v);
bindRange('#in-pr', '#v-pr', v => v.toFixed(3), v => S.PRset = v);
bindRange('#in-ta', '#v-ta', v => `${v.toFixed(1)} °C`, v => S.TaC = v);
bindRange('#in-pa', '#v-pa', v => `${v.toFixed(2)} kPa`, v => S.PaK = v);
bindRange('#in-phi', '#v-phi', v => `${Math.round(v*100)} %`, v => S.phi = v);
bindRange('#in-sev', '#v-sev', v => `${Math.round(v*100)} %`, v => S.sev = v);
$('#fault').addEventListener('change', e => { S.fault = e.target.value; Object.keys(S.cus).forEach(k => S.cus[k] = {hi: 0, lo: 0}); });
$('#bellmouth').addEventListener('change', e => { S.bellmouth = e.target.checked; });
function segBind(sel, key, fn){ $$(sel + ' button').forEach(b => b.addEventListener('click', () => { $$(sel + ' button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); fn(b.dataset[key]); })); }
segBind('#field-seg', 'f', v => ANIM.field = v);
segBind('#speed-seg', 's', v => S.speed = +v);
segBind('#mode-seg', 'm', v => { S.mode = v; $('#ctl-manual').hidden = v !== 'manual'; $('#ctl-auto').hidden = v !== 'auto'; $('#mode-chip').textContent = v === 'auto' ? 'Holding pressure ratio' : 'Manual speed'; S.I = 0; });
$('#run-btn').addEventListener('click', () => { S.running = !S.running; $('#run-btn').textContent = S.running ? 'Pause' : 'Run'; });
$('#btn-reset').addEventListener('click', () => { resetRig(); toast('Rig reset'); });
$('#btn-baseline').addEventListener('click', () => {
  S.base = {p: S.kf.x[0], t: S.kf.x[1], m: S.bellmouth ? S.kf.x[2] : 1}; Object.keys(S.cus).forEach(k => S.cus[k] = {hi: 0, lo: 0});
  toast(`Baseline set: h_p ${S.base.p.toFixed(4)}, h_T ${S.base.t.toFixed(4)}`);
});
$('#src').addEventListener('change', e => {
  if (e.target.value === 'replay'){
    const ds = currentDataset();
    if (!ds){ e.target.value = 'rig'; toast('Upload or generate a dataset first (Design & data)'); return; }
    startReplay(ds);
  } else stopReplay();
});
function startReplay(ds){
  S.source = 'replay'; S.replay = {rows: ds.rows, kind: ds.kind, name: ds.name, start: S.t, k: 0}; $('#src').value = 'replay';
  Object.keys(S.cus).forEach(k => S.cus[k] = {hi: 0, lo: 0});
  $('#src-chip').textContent = ds.kind === 'measured' ? 'Replay: measured log' : 'Replay: simulated log'; $('#src-chip').className = 'chip ' + (ds.kind === 'measured' ? 'ok' : 'info');
  $('#dev-src-h').innerHTML = ds.kind === 'measured' ? '<span class="tag meas">MEAS</span>' : '<span class="tag sim">SIM</span>';
  $$('#ctl-manual input, #ctl-auto input, #mode-seg button, #fault, #in-sev').forEach(x => x.disabled = true);
  location.hash = '#twin'; toast(`Replaying “${ds.name}”`);
}
function stopReplay(){
  S.source = 'rig'; S.replay = null; $('#src').value = 'rig'; $('#src-chip').textContent = 'Virtual rig'; $('#src-chip').className = 'chip info';
  $('#dev-src-h').innerHTML = '<span class="tag sim">SIM</span>';
  $$('#ctl-manual input, #ctl-auto input, #mode-seg button, #fault, #in-sev').forEach(x => x.disabled = false);
}

/* ------------------------------------------------------------------ KPI tiles and deviation panel */
const srcTag = () => S.meas && S.meas.kind === 'meas' ? '<span class="tag meas">MEAS</span>' : '<span class="tag sim">SIM</span>';
function kpi(label, tag, v, unit, sub, st){ return `<div class="kpi ${st || ''}"><div class="k"><span>${label}</span>${tag}</div><div class="v">${v}<small>${unit}</small></div><div class="s">${sub || '&nbsp;'}</div></div>`; }
function renderKPIs(){
  const m = S.meas, e = S.est, me = S.mest; if (!m || !e) return;
  const T = '<span class="tag est">EST</span>', M = srcTag(), st = k => status(k);
  const PRm = m.Pout != null ? m.Pout/m.Pa : null, ToutC = m.Tout != null ? m.Tout - 273.15 : null;
  const Pe = m.Ib != null && m.Vb != null ? m.Ib*m.Vb : null;
  let etaM = PRm && m.Tout && m.N > 4000 && Math.abs(m.N - S.Ncmd) < 0.01*S.Ncmd + 50 && Math.abs(m.Tout - S.sens.ToutEstLag - (S.est.Toutb - S.sens.ToutEstLag)) < 0.4 ? (Math.pow(PRm, 1/EXP) - 1)/(m.Tout/(m.TaC + 273.15) - 1) : null;
  if (etaM != null && (etaM < 0.2 || etaM > 1)) etaM = null;
  const [u1, u2] = thermalInputs(e), cas = casingTimeToLimit(S.thA, u1, u2, m.TaC), mot = motorTimeToLimit(S.motEst, me.Ploss, m.TaC);
  const ttl = Math.min(cas.t, mot.t), casMax = m.TaC + Math.max(...casingField(S.thA));
  const html = [
    kpi('Rotational speed', M, fmt(m.N, 0), ' rpm', `command ${fmt(S.Ncmd, 0)} · EST ${fmt(S.Nexp, 0)} rpm`, st('N')),
    kpi('Pressure ratio', M, fmt(PRm, 4), '', `EST ${fmt(e.PRb, 4)} · Δ ${PRm != null ? (PRm - e.PRb >= 0 ? '+' : '') + (PRm - e.PRb).toFixed(4) : '–'}`, st('PR')),
    kpi('Outlet total pressure', M, fmt(m.Pout != null ? m.Pout/1e3 : null, 2), ' kPa', `EST ${fmt(e.PRb*m.Pa/1e3, 2)} kPa`, st('Pout')),
    kpi('Outlet total temperature', M, fmt(ToutC, 2), ' °C', `EST ${fmt(S.sens.ToutEstLag - 273.15, 2)} °C (probe lag 3 s)`, st('Tout')),
    kpi('Ambient (inlet) state', M, fmt(m.TaC, 1), ' °C', `${fmt(m.Pa/1e3, 2)} kPa`, ''),
    kpi('Mass flow', m.m != null ? M : T, fmt(m.m != null ? m.m : e.mb, 4), ' kg/s', m.m != null ? `EST ${fmt(e.mb, 4)} kg/s` : 'not measured: from the ROM', S.bellmouth ? st('m') : ''),
    kpi('Isentropic efficiency', T, fmt(e.eta*100, 1), ' %', `from sensors ${etaM != null && isFinite(etaM) ? fmt(etaM*100, 1) + ' %' : '– (needs steady state)'}`, ''),
    kpi('Shaft power', T, fmt(e.Pshb/1e3, 3), ' kW', `torque ${fmt(me.tq, 2)} N·m`, ''),
    kpi('Electrical power', Pe != null ? M : T, fmt((Pe != null ? Pe : me.Pe)/1e3, 3), ' kW', `EST ${fmt(me.Pe/1e3, 3)} kW · η_motor ${fmt(me.eta_m*100, 0)} %`, st('Pe')),
    kpi('Battery current', m.Ib != null ? M : T, fmt(m.Ib != null ? m.Ib : me.Ib, 1), ' A', `EST ${fmt(me.Ib, 1)} A · phase ${fmt(me.Iq, 0)} A`, st('I')),
    kpi('Surge margin', T, fmt(e.SM*100, 1), ' %', S.surge > 0 ? 'SURGE' : e.SM < 0.03 ? 'close to surge' : 'stable', S.surge > 0 ? 'alarm' : e.SM < 0.03 ? 'warn' : 'ok'),
    kpi('Motor winding', T, fmt(S.motEst.Tw, 0), ' °C', `steady ${fmt(mot.steady, 0)} °C (limit ${MOTOR.Tlim})`, S.motEst.Tw > MOTOR.Tlim ? 'alarm' : mot.steady > MOTOR.Tlim ? 'warn' : 'ok'),
    kpi('PLA casing max', T, fmt(casMax, 1), ' °C', `steady ${fmt(cas.steady, 1)} °C (limit ${PLA_LIMIT})`, casMax > PLA_LIMIT ? 'alarm' : cas.steady > PLA_LIMIT ? 'warn' : 'ok'),
    kpi('Time to a thermal limit', T, isFinite(ttl) ? fmt(ttl/60, 1) : 'none', isFinite(ttl) ? ' min' : '', isFinite(ttl) ? (cas.t < mot.t ? 'PLA casing reaches 55 °C' : 'motor winding reaches limit') : 'steady state stays below the limits', isFinite(ttl) ? (ttl < 300 ? 'alarm' : 'warn') : 'ok'),
  ].join('');
  $('#kpis').innerHTML = html;
  // deviation table
  $('#dev-table tbody').innerHTML = S.devRows.map(([name, ev, mv, d, key, z]) => {
    const c = S.cus[key] || {hi: 0, lo: 0}, cu = Math.min(Math.max(c.hi, c.lo)/CUSUM_H, 1), s = status(key);
    const dlt = mv - ev;
    return `<tr><td>${name}</td><td>${fmt(ev, d)}</td><td>${fmt(mv, d)}</td><td>${(dlt >= 0 ? '+' : '') + fmt(dlt, d)}</td><td style="color:var(--${s === 'ok' ? 'ink-2' : s})">${fmt(z, 1)}</td><td><span class="cus" title="CUSUM ${fmt(Math.max(c.hi, c.lo), 1)}"><i style="width:${(cu*100).toFixed(0)}%;background:var(--${cu >= 1 ? 'alarm' : 'warn'})"></i></span></td></tr>`;
  }).join('');
  const kf = S.kf, h2 = i => 2*Math.sqrt(kf.P[i]);
  $('#health').innerHTML = `<div><span>h<sub>p</sub> (pressure)</span><b>${fmt(kf.x[0], 4)}</b><span>± ${fmt(h2(0), 4)} (2σ) · base ${fmt(S.base.p, 3)}</span></div>
    <div><span>h<sub>T</sub> (temperature)</span><b>${fmt(kf.x[1], 4)}</b><span>± ${fmt(h2(1), 4)} (2σ) · base ${fmt(S.base.t, 3)}</span></div>
    <div><span>efficiency factor</span><b>${fmt(kf.x[0]/kf.x[1], 4)}</b><span>≈ h<sub>p</sub>/h<sub>T</sub>${S.bellmouth ? ` · h<sub>m</sub> ${fmt(kf.x[2], 3)}` : ''}</span></div>`;
  const al = S.alarms;
  $('#alarms').innerHTML = al.length ? al.map(([lvl, t]) => `<div class="alarm-item ${lvl}">${esc(t)}</div>`).join('') : '<div class="alarm-item ok">All channels agree with the healthy twin within their uncertainty.</div>';
  const worst = al.some(a => a[0] === 'alarm') ? 'alarm' : al.some(a => a[0] === 'warn') ? 'warn' : 'ok';
  const chip = $('#anom-chip'); chip.className = 'chip ' + worst; chip.textContent = worst === 'alarm' ? 'Anomaly' : worst === 'warn' ? 'Watch' : 'Nominal';
  const b = [];
  if (S.surge > 0) b.push('<span class="chip alarm">SURGE</span>');
  if (e.extrap && m.N > 1000) b.push('<span class="chip warn">Extrapolating</span>');
  if (S.source === 'rig' && S.fault !== 'none' && S.sev > 0) b.push(`<span class="chip warn">Fault injected: ${esc(FAULTS[S.fault].label)}</span>`);
  if (S.source === 'replay') b.push(`<span class="chip info">Replay: ${esc(S.replay.name)}</span>`);
  $('#sim-banner').innerHTML = b.join('');
}

/* ------------------------------------------------------------------ charts registry */
const H_ = k => HIST.d[k];
const CHARTS = {
  'c-pr': () => ({xlabel: 'time (s)', ylabel: 'total pressure ratio', series: [
    {x: H_('t'), y: H_('PRe'), color: 'est', label: 'EST (ROM)', width: 2},
    {x: H_('t'), y: H_('PRm'), color: S.meas && S.meas.kind === 'meas' ? 'meas' : 'sim', label: S.meas && S.meas.kind === 'meas' ? 'MEAS' : 'SIM', width: 1.2},
    {x: H_('t'), y: H_('PRset'), color: 'ink', dash: [5, 4], label: 'set point', width: 1}]}),
  'c-n': () => ({xlabel: 'time (s)', ylabel: 'speed (rpm)', y0zero: true, series: [
    {x: H_('t'), y: H_('Ncmd'), color: 'warn', dash: [6, 4], label: 'motor command', width: 1.5},
    {x: H_('t'), y: H_('N'), color: S.meas && S.meas.kind === 'meas' ? 'meas' : 'sim', label: 'measured speed', width: 1.6}]}),
  'c-t': () => ({xlabel: 'time (s)', ylabel: 'temperature (°C)', series: [
    {x: H_('t'), y: H_('Tm'), color: S.meas && S.meas.kind === 'meas' ? 'meas' : 'sim', label: 'outlet T₀ sensor', width: 1.4},
    {x: H_('t'), y: H_('Te'), color: 'est', label: 'outlet T₀ EST', width: 2, dash: [4, 3]},
    {x: H_('t'), y: H_('Tcas'), color: 'warn', label: 'PLA casing max EST', width: 1.6},
    {x: H_('t'), y: H_('Tw'), color: 'alarm', label: 'motor winding EST', width: 1.6}]}),
  'c-p': () => ({xlabel: 'time (s)', ylabel: 'power (W)', y0zero: true, y2: {label: 'battery current (A)'}, series: [
    {x: H_('t'), y: H_('Pe_e'), color: 'est', label: 'P_el EST', width: 2},
    {x: H_('t'), y: H_('Pe_m'), color: S.meas && S.meas.kind === 'meas' ? 'meas' : 'sim', label: 'P_el measured', width: 1.2},
    {x: H_('t'), y: H_('Psh'), color: 'des', label: 'shaft EST', width: 1.4, dash: [5, 3]},
    {x: H_('t'), y: H_('Ib_m'), color: 'ink-3', label: 'I_batt', width: 1, axis2: true}]}),
  'c-map': () => mapSpec(),
  'c-ax': () => axialSpec(),
  'c-kf': () => ({xlabel: 'time (s)', ylabel: 'health factor (–)', hlines: [{y: 1, color: 'des', label: 'design'}], series: [
    {x: H_('t'), y: H_('hp'), color: 'est', label: 'h_p ±2σ', width: 1.8, band: {lo: H_('hp').map((v, i) => v - H_('hpS')[i]), hi: H_('hp').map((v, i) => v + H_('hpS')[i])}},
    {x: H_('t'), y: H_('ht'), color: 'alarm', label: 'h_T ±2σ', width: 1.8, band: {lo: H_('ht').map((v, i) => v - H_('htS')[i]), hi: H_('ht').map((v, i) => v + H_('htS')[i])}}]}),
};
function mapSpec(){
  const ser = [];
  MAP.lines.forEach((l, i) => {
    const st = l.s.map((s, j) => s ? l.PR[j] : null), un = l.s.map((s, j) => !s || (j + 1 < l.s.length && !l.s[j + 1]) || (j > 0 && !l.s[j - 1] && s) ? l.PR[j] : null);
    ser.push({x: l.m, y: st, color: 'ink-3', width: 1.1}); ser.push({x: l.m, y: l.s.map((s, j) => !s ? l.PR[j] : null), color: 'ink-3', width: 1, dash: [3, 3]});
    const k = l.s.lastIndexOf(1); ser.push({x: [l.m[l.m.length - 1]], y: [l.PR[l.PR.length - 1]], color: 'ink-3', line: false, marker: null, labels: [`${l.N/1000}k`]});
  });
  ser.push({x: MAP.surge.m, y: MAP.surge.PR, color: 'alarm', width: 2, label: 'surge line'});
  const e = S.est;
  if (e){
    const th = Math.sqrt(e.TaK/REF.T), dl = e.PaPa/REF.P, ol = {x: [], y: []};
    for (let N = 6000; N <= 23000; N += 500){ const r = romPredict(N, e.phi); ol.x.push(r.m); ol.y.push(r.PR); }
    ser.push({x: ol.x, y: ol.y, color: 'est', dash: [2, 3], width: 1.4, label: `operating line, valve ${(e.phi*100).toFixed(0)} %`});
    ser.push({x: [e.m*th/dl], y: [1 + S.base.p*(e.PR - 1)], color: 'est', line: false, marker: 'o', msize: 5, label: 'EST point'});
    const m = S.meas; if (m && m.Pout != null){ const mm = (m.m != null ? m.m : e.mb)*th/dl; ser.push({x: [mm], y: [m.Pout/m.Pa], color: m.kind === 'meas' ? 'meas' : 'sim', line: false, marker: 'd', msize: 4.5, label: m.m != null ? 'measured' : 'measured PR at EST flow'}); }
  }
  ser.push({x: [ROM.design.m], y: [ROM.design.PR], color: 'des', line: false, marker: 's', msize: 4, label: 'design'});
  return {xlabel: 'corrected mass flow (kg/s)', ylabel: 'total pressure ratio', x: [0.06, 0.25], y: [1.0, 1.17], series: ser};
}
const DES_EST = romPredict(20000, 1.0);
function axialSpec(){
  const e = S.est, xs = [...Array(NS).keys()], names = ROM.stations;
  const ser = [];
  if (e){ ser.push({x: xs, y: e.P0.map(v => (v - e.PaPa)/1e3), color: 'est', marker: 'o', width: 2, label: 'ΔP₀ (kPa) EST'});
          ser.push({x: xs, y: e.T0.map(v => v - e.TaK), color: 'alarm', marker: 's', width: 2, label: 'ΔT₀ (K) EST'});
          ser.push({x: xs, y: e.p.map(v => (v - e.PaPa)/1e3), color: 'sim', marker: 'd', width: 1.2, dash: [4, 3], label: 'Δp static (kPa)'}); }
  ser.push({x: xs, y: DES_EST.P0.map(v => (v - DES_EST.PaPa)/1e3), color: 'des', dash: [5, 4], width: 1.2, label: 'design ΔP₀'});
  return {xlabel: 'station', ylabel: 'rise above inlet', x: [-0.2, 8.2], xticks: 8, xfmt: v => (names[Math.round(v)] || '').replace(' exit', ''), series: ser};
}
function fitCanvas(cv){
  const r = cv.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (r.width < 10) return null;
  const w = Math.round(r.width*dpr), h = Math.round(r.height*dpr);
  if (cv.width !== w || cv.height !== h){ cv.width = w; cv.height = h; }
  const ctx = cv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); return [ctx, r.width, r.height];
}
function renderCharts(force){
  if (VIEW === 'twin'){
    Object.keys(CHARTS).forEach(id => { const f = fitCanvas($('#' + id)); if (f) plot(f[0], f[1], f[2], TOK, CHARTS[id]()); });
    const f = fitCanvas($('#c-tri')); if (f) drawTriangles(f[0], f[1], f[2], TOK, +$('#tri-stage').value);
  }
  if (VIEW === 'compare' && force){ renderDatasetCharts(); renderOpTable(); }
  if (VIEW === 'compare' && !force) renderOpTable();
  if (VIEW === 'rom' && force) Object.keys(ROMCHARTS).forEach(id => { const f = fitCanvas($('#' + id)); if (f) plot(f[0], f[1], f[2], TOK, ROMCHARTS[id]()); });
}
$('#tri-stage').addEventListener('change', () => renderCharts());

/* ------------------------------------------------------------------ main loop */
let lastT = performance.now(), acc = 0, lastUI = 0;
const simCv = $('#sim');
function frame(now){
  const dtR = Math.min((now - lastT)/1000, 0.1); lastT = now;
  if (S.running){ acc += dtR*S.speed; let n = 0; while (acc >= DT && n < 700){ step(); acc -= DT; n++; } if (n >= 700) acc = 0; }
  if (VIEW === 'twin'){ const f = fitCanvas(simCv); if (f) drawSim(f[0], f[1], f[2], TOK, S.running ? dtR : 0); }
  if (now - lastUI > 250){ lastUI = now; $('#clock').textContent = `t = ${S.t.toFixed(1)} s`; if (VIEW === 'twin') renderKPIs(); renderCharts(false); }
  requestAnimationFrame(frame);
}

/* ------------------------------------------------------------------ design reference */
const DESIGN_FIELDS = [['stages', 'Number of stages', ''], ['N_rpm', 'Design speed', 'rpm'], ['PR', 'Total pressure ratio', ''], ['mdot_kg_s', 'Mass flow', 'kg/s'],
  ['T_in_C', 'Inlet temperature', '°C'], ['P_in_kPa', 'Inlet pressure', 'kPa'], ['T_out_C', 'Outlet total temperature', '°C'], ['P_out_kPa', 'Outlet total pressure', 'kPa'],
  ['dT0_K', 'Total temperature rise', 'K'], ['eta_stage', 'Stage efficiency', ''], ['eta_overall', 'Overall isentropic efficiency', ''], ['P_air_kW', 'Power to air', 'kW'],
  ['P_shaft_kW', 'Shaft power', 'kW'], ['torque_Nm', 'Shaft torque', 'N·m'], ['Ca_m_s', 'Axial velocity', 'm/s'], ['hub_in_mm', 'Inlet hub diameter', 'mm'],
  ['tip_mm', 'Tip diameter', 'mm'], ['hub_out_mm', 'Outlet hub diameter', 'mm'], ['rotor_blades', 'Rotor blades', ''], ['stator_vanes', 'Stator vanes', ''], ['surge_margin', 'Design surge margin', '']];
const designValues = () => Object.assign({}, DESIGN_DEFAULT, REC.design || {});
let designDirty = false;
function renderDesignForm(){
  if (designDirty) return;
  const d = designValues();
  $('#design-form').innerHTML = DESIGN_FIELDS.map(([k, l, u]) => `<div><label for="dz-${k}">${l}${u ? ` (${u})` : ''}</label><input type="text" id="dz-${k}" data-k="${k}" value="${esc(d[k])}"></div>`).join('');
  $$('#design-form input').forEach(i => i.addEventListener('input', () => { designDirty = true; $('#design-status').textContent = 'Unsaved changes'; }));
  if (!$('#design-status').textContent) $('#design-status').textContent = REC.design ? `Saved design reference${REC.design.saved_at ? ' · ' + new Date(REC.design.saved_at).toLocaleString() : ''}` : 'Showing the design calculation values.';
}
function readDesignForm(){ const o = {}; $$('#design-form input').forEach(i => { const v = i.value.trim(), n = Number(v); o[i.dataset.k] = v !== '' && isFinite(n) ? n : v; }); return o; }
$('#design-save').addEventListener('click', async () => {
  const o = readDesignForm(); o.saved_at = new Date().toISOString();
  if (!CAP.db){ REC.design = o; designDirty = false; $('#design-status').textContent = 'Kept for this session (saving is not available in this view).'; return; }
  try { await CAP.db.doc('design/reference').set(o); designDirty = false; $('#design-status').textContent = 'Saved.'; toast('Design reference saved'); }
  catch (e){ $('#design-status').textContent = 'Could not save: ' + (e.message || e.code); }
});
$('#design-upload-btn').addEventListener('click', () => $('#design-file').click());
$('#design-file').addEventListener('change', async e => {
  const f = e.target.files[0]; if (!f) return; const txt = await f.text(); let o = {};
  try { if (/^\s*[{[]/.test(txt)) o = JSON.parse(txt); else txt.split(/\r?\n/).forEach(l => { const [k, v] = l.split(/[,;\t]/); if (k && v !== undefined) o[k.trim()] = v.trim(); }); }
  catch (err){ toast('Could not read the file: use JSON or two-column CSV (key,value)'); return; }
  let n = 0; $$('#design-form input').forEach(i => { if (o[i.dataset.k] !== undefined){ i.value = o[i.dataset.k]; n++; } });
  designDirty = true; $('#design-status').textContent = `${n} fields filled from ${f.name}. Review, then Save.`; e.target.value = '';
});

/* ------------------------------------------------------------------ operating-point table */
function opRows(){
  const d = designValues(), m = S.meas, e = S.est, me = S.mest; if (!m || !e) return {head: [], rows: []};
  const PRm = m.Pout != null ? m.Pout/m.Pa : null, kind = m.kind === 'meas' ? 'MEAS' : 'SIM', Pe = m.Ib != null && m.Vb != null ? m.Ib*m.Vb : null;
  const r = (q, u, des, est, meas, dd) => [q, u, des == null ? '–' : fmt(des, dd), fmt(est, dd), meas == null ? '–' : fmt(meas, dd), meas == null ? '–' : ((meas - est >= 0 ? '+' : '') + fmt(meas - est, dd))];
  return {head: ['Quantity', 'Unit', 'Design [DES]', 'Expected now [EST]', `Measured [${kind}]`, 'Measured − expected'], rows: [
    r('Rotational speed', 'rpm', d.N_rpm, m.N, m.N, 0),
    r('Inlet temperature', '°C', d.T_in_C, m.TaC, m.TaC, 2),
    r('Inlet pressure', 'kPa', d.P_in_kPa, m.Pa/1e3, m.Pa/1e3, 3),
    r('Valve opening', '%', 100, m.phi*100, m.phi*100, 0),
    r('Total pressure ratio', '–', d.PR, e.PRb, PRm, 4),
    r('Outlet total pressure', 'kPa', d.P_out_kPa, e.PRb*m.Pa/1e3, m.Pout != null ? m.Pout/1e3 : null, 2),
    r('Outlet total temperature', '°C', d.T_out_C, e.Toutb - 273.15, m.Tout != null ? m.Tout - 273.15 : null, 2),
    r('Mass flow', 'kg/s', d.mdot_kg_s, e.mb, m.m, 4),
    r('Isentropic efficiency', '–', d.eta_overall, e.eta, null, 4),
    r('Power to air', 'kW', d.P_air_kW, e.Pshb*ETA_MECH/1e3, null, 3),
    r('Shaft power', 'kW', d.P_shaft_kW, e.Pshb/1e3, null, 3),
    r('Electrical power', 'kW', null, me.Pe/1e3, Pe != null ? Pe/1e3 : null, 3),
    r('Battery current', 'A', null, me.Ib, m.Ib, 1),
    r('Shaft torque', 'N·m', d.torque_Nm, me.tq, null, 3),
    r('Surge margin', '–', d.surge_margin, e.SM, null, 3)]};
}
function tableHTML(t){ return `<thead><tr>${t.head.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${t.rows.map(r => `<tr>${r.map((c, i) => `<td class="${i > 1 || typeof c === 'number' ? 'n' : ''}">${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody>`; }
function renderOpTable(){ $('#op-table').innerHTML = tableHTML(opRows()); }

/* ------------------------------------------------------------------ datasets: parse, store, compare */
const ALIAS = {t: ['time', 'times', 't', 'ts', 'timestamp', 'elapsed', 'elapseds', 'timesec'], N: ['rpm', 'n', 'speed', 'speedrpm', 'nrpm', 'motorrpm', 'shaftrpm'],
  TaC: ['tamb', 'tambc', 'ambientt', 'tinc', 'tinlet', 'tinletc', 't01', 'tin', 'tambk', 'ambienttc'], Pa: ['pamb', 'pambkpa', 'pambpa', 'pambhpa', 'ambientp', 'pin', 'pinkpa', 'p01', 'pinlet'],
  Tout: ['tout', 'toutc', 't0out', 'toutlet', 'toutletc', 't03', 'toutk'], Pout: ['pout', 'poutkpa', 'p0out', 'p0outkpa', 'poutlet', 'poutpa', 'pouthpa', 'poutletkpa', 'p0outletkpa'],
  ps: ['poutstatic', 'poutstatickpa', 'pstatic', 'pouts', 'pstatickpa', 'poutstaticpa'], Ib: ['ibatt', 'ibatta', 'ibat', 'current', 'ia', 'iin', 'battcurrent'],
  Vb: ['vbatt', 'vbattv', 'vbat', 'voltage', 'vin', 'battvoltage'], m: ['mdot', 'mdotkgs', 'massflow', 'massflowkgs'], phi: ['valve', 'valvepct', 'valveopening', 'throttle', 'phi', 'valve%']};
const normH = h => h.toLowerCase().replace(/[^a-z0-9%]/g, '');
const A_OUT = Math.PI*(0.0505*0.0505 - 0.03844*0.03844);
function parseCSV(text, name, kind){
  const lines = text.split(/\r?\n/).filter(l => l.trim() && !l.trim().startsWith('#'));
  if (lines.length < 2) throw new Error('The file has no data rows.');
  const delim = [',', ';', '\t'].map(d => [d, lines[0].split(d).length]).sort((a, b) => b[1] - a[1])[0][0];
  const head = lines[0].split(delim).map(h => h.trim().replace(/^"|"$/g, '')), nh = head.map(normH), map = {};
  Object.entries(ALIAS).forEach(([k, al]) => { const i = nh.findIndex(h => al.includes(h)); if (i >= 0) map[k] = i; });
  if (map.N == null) throw new Error('No speed column found (expected rpm).');
  if (map.Pout == null && map.ps == null && map.Tout == null && map.Ib == null) throw new Error('No outlet pressure, outlet temperature or current column found.');
  const unitP = k => { const h = nh[map[k]]; return h.includes('kpa') ? 1e3 : h.includes('hpa') ? 100 : h.endsWith('pa') ? 1 : null; };
  const rows = []; let t0 = null;
  for (let li = 1; li < lines.length; li++){
    const c = lines[li].split(delim).map(v => v.trim().replace(/^"|"$/g, ''));
    const num = k => map[k] == null ? null : (c[map[k]] === '' ? null : Number(c[map[k]]));
    let t = num('t'); if (map.t != null && !isFinite(t)){ const d = Date.parse(c[map.t]); t = isFinite(d) ? d/1000 : null; }
    if (t == null || !isFinite(t)) t = li - 1; if (t0 == null) t0 = t;
    const P = k => { let v = num(k); if (v == null || !isFinite(v)) return null; const u = unitP(k); return u ? v*u : v < 300 ? v*1e3 : v < 3000 ? v*100 : v; };
    const T = k => { const v = num(k); return v == null || !isFinite(v) ? null : v > 200 ? v - 273.15 : v; };
    let phi = num('phi'); if (phi != null && phi > 3) phi /= 100;
    const row = {t: t - t0, N: num('N'), TaC: T('TaC'), Pa: P('Pa'), Pout: P('Pout'), Tout: T('Tout'), Ib: num('Ib'), Vb: num('Vb'), m: num('m'), phi};
    const ps = P('ps');
    if (row.Pout == null && ps != null && row.N != null){ // static to total: P0 = p + rho C^2 / 2 with the ROM mass flow
      const est = romPredict(row.N, phi || 1, (row.TaC ?? 15) + 273.15, row.Pa ?? 101325), rho = ps/(287*((row.Tout ?? 20) + 273.15)), C = est.m/(rho*A_OUT);
      row.Pout = ps + 0.5*rho*C*C;
    }
    if (row.N != null && isFinite(row.N)) rows.push(row);
  }
  let kept = rows; if (rows.length > 1500){ const st = rows.length/1500; kept = Array.from({length: 1500}, (_, i) => rows[Math.floor(i*st)]); }
  return {name, kind, uploaded_at: new Date().toISOString(), n_rows: rows.length, n_kept: kept.length, columns: Object.keys(map), rows: kept};
}
function currentDataset(){ const id = $('#ds-select').value; return allDatasets().find(d => d.id === id) || null; }
function allDatasets(){ return REC.datasets.concat(REC.memDatasets); }
function renderDatasetSelect(){
  const sel = $('#ds-select'), cur = sel.value, all = allDatasets();
  sel.innerHTML = all.length ? all.map(d => `<option value="${esc(d.id)}">${esc(d.name)} · ${d.kind === 'measured' ? 'MEAS' : 'SIM'} · ${d.n_rows} rows${d._mem ? ' (not saved)' : ''}</option>`).join('') : '<option value="">No datasets yet</option>';
  if (all.some(d => d.id === cur)) sel.value = cur;
  renderDatasetCharts();
}
$('#ds-select').addEventListener('change', () => renderDatasetCharts());
async function storeDataset(ds, rawFile){
  if (CAP.db && CAP.canWrite){
    try {
      if (rawFile && CAP.assets){ try { const a = await CAP.assets.upload(rawFile); ds.raw_asset_id = a.id; } catch (e) {} }
      const ref = await CAP.db.collection('datasets').add(ds); toast(`Saved dataset “${ds.name}”`); setTimeout(() => { $('#ds-select').value = ref.id; renderDatasetCharts(); }, 400); return;
    } catch (e){ toast('Could not save the dataset: ' + (e.code === 'quota_exceeded' ? 'storage is full, delete an old dataset' : (e.message || e.code))); }
  }
  ds.id = 'mem-' + Date.now(); ds._mem = true; REC.memDatasets.unshift(ds); renderDatasetSelect(); $('#ds-select').value = ds.id; renderDatasetCharts();
}
async function handleFile(f){
  if (!f) return;
  const kind = document.querySelector('input[name=kind]:checked').value;
  try { const ds = parseCSV(await f.text(), f.name.replace(/\.[^.]+$/, ''), kind); await storeDataset(ds, f); $('#ds-info').textContent = `${ds.n_rows} rows read; columns: ${ds.columns.join(', ')}${ds.n_rows > ds.n_kept ? `; ${ds.n_kept} kept (evenly spaced)` : ''}`; }
  catch (e){ toast(e.message); $('#ds-info').textContent = e.message; }
}
$('#pick-btn').addEventListener('click', () => $('#csv-file').click());
$('#csv-file').addEventListener('change', e => { handleFile(e.target.files[0]); e.target.value = ''; });
const drop = $('#drop');
['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', e => handleFile(e.dataTransfer.files[0]));
$('#ds-replay').addEventListener('click', () => { const ds = currentDataset(); if (ds) startReplay(ds); else toast('Choose a dataset first'); });
$('#ds-delete').addEventListener('click', async () => {
  const ds = currentDataset(); if (!ds) return;
  const btn = $('#ds-delete');
  if (btn.dataset.arm !== ds.id){ btn.dataset.arm = ds.id; btn.textContent = 'Click again to delete'; setTimeout(() => { btn.dataset.arm = ''; btn.textContent = 'Delete dataset'; }, 3500); return; }
  btn.dataset.arm = ''; btn.textContent = 'Delete dataset';
  if (ds._mem){ REC.memDatasets = REC.memDatasets.filter(d => d !== ds); renderDatasetSelect(); return; }
  try { await CAP.db.doc('datasets/' + ds.id).delete(); toast('Dataset deleted'); } catch (e){ toast('Could not delete: ' + (e.message || e.code)); }
});
$('#tpl-btn').addEventListener('click', () => save('compressor_log_template.csv',
  'time_s,rpm,T_amb_C,P_amb_kPa,T_out_C,P_out_kPa,I_batt_A,V_batt_V,mdot_kg_s,valve_pct\n# example of the format only; replace with your logged values\n0.0,0,25.0,100.90,25.0,100.90,0.0,30.8,,100\n0.1,1200,25.0,100.90,25.0,100.95,1.2,30.8,,100\n'));
$('#example-btn').addEventListener('click', () => { const ds = generateExample(); storeDataset(ds, null); });
function generateExample(){
  const keep = JSON.parse(JSON.stringify({Nman: S.Nman, phi: S.phi, TaC: S.TaC, PaK: S.PaK, fault: S.fault, sev: S.sev, mode: S.mode, base: S.base, bellmouth: S.bellmouth}));
  const save_ = {t: S.t, N: S.N, Ncmd: S.Ncmd, mot: {...S.mot}, motEst: {...S.motEst}, thA: S.thA.slice(), sens: {...S.sens}, kf: JSON.parse(JSON.stringify(S.kf)), cus: JSON.parse(JSON.stringify(S.cus)), hist: JSON.parse(JSON.stringify(HIST.d)), next: HIST.next, source: S.source, replay: S.replay, truth: S.truth, meas: S.meas, est: S.est, mest: S.mest, I: S.I};
  Object.assign(S, {source: 'rig', mode: 'manual', TaC: 25, PaK: 100.9, fault: 'none', sev: 0, phi: 1.0, base: {p: 1, t: 1, m: 1}, bellmouth: true}); resetRig();
  const plan = [[0, 12000, 1.0, 'none', 0], [30, 16000, 1.0, 'none', 0], [70, 20000, 1.0, 'none', 0], [110, 20000, 1.25, 'none', 0], [150, 18000, 0.97, 'none', 0], [190, 18000, 1.0, 'erosion', 0.6]];
  const rows = [];
  for (let k = 0; k < 2400; k++){
    const t = k*DT; const p = plan.filter(q => q[0] <= t).pop(); S.Nman = p[1]; S.phi = p[2]; S.fault = p[3]; S.sev = p[4];
    step(); const m = S.meas;
    if (k % 5 === 0) rows.push({t: +t.toFixed(2), N: +m.N.toFixed(1), TaC: +m.TaC.toFixed(3), Pa: +m.Pa.toFixed(1), Pout: +m.Pout.toFixed(1), Tout: +(m.Tout - 273.15).toFixed(3), Ib: +m.Ib.toFixed(2), Vb: +m.Vb.toFixed(3), m: +m.m.toFixed(5), phi: m.phi});
  }
  Object.assign(S, keep, save_); HIST.d = save_.hist; HIST.next = save_.next;
  return {name: 'Example log (virtual rig, 25 °C, blade erosion from 190 s)', kind: 'simulated', uploaded_at: new Date().toISOString(), n_rows: rows.length, n_kept: rows.length, columns: ['t', 'N', 'TaC', 'Pa', 'Pout', 'Tout', 'Ib', 'Vb', 'm', 'phi'], rows};
}
let DSCMP = null;
function compareDataset(ds){
  if (!ds) return null;
  const out = ds.rows.map(r => {
    const TaK = (r.TaC ?? S.TaC) + 273.15, Pa = r.Pa ?? S.PaK*1e3, phi = r.phi ?? 1.0, e = romPredict(r.N, phi, TaK, Pa), me = motorModel(r.N, e.Pshaft);
    return {t: r.t, N: r.N, PRm: r.Pout != null ? r.Pout/Pa : null, PRe: e.PR, Tm: r.Tout, Te: e.Tout - 273.15, Ib: r.Ib, Ie: me.Ib, Pe: r.Ib != null && r.Vb != null ? r.Ib*r.Vb : null, Pee: me.Pe, m: r.m, me: e.m, Pout: r.Pout != null ? r.Pout/1e3 : null, Poute: e.PR*Pa/1e3};
  });
  const met = (k, ke, sel = r => r.N > 4000) => {
    const p = out.filter(r => sel(r) && r[k] != null && isFinite(r[k])); if (p.length < 2) return null;
    const e = p.map(r => r[k] - r[ke]), y = p.map(r => r[k]), ym = y.reduce((a, b) => a + b, 0)/y.length;
    const sse = e.reduce((a, b) => a + b*b, 0), sst = y.reduce((a, b) => a + (b - ym)*(b - ym), 0);
    return {n: p.length, rmse: Math.sqrt(sse/p.length), mae: e.reduce((a, b) => a + Math.abs(b), 0)/p.length, bias: e.reduce((a, b) => a + b, 0)/p.length, max: Math.max(...e.map(Math.abs)), r2: sst > 0 ? 1 - sse/sst : null};
  };
  return {rows: out, metrics: [['Pressure ratio', '–', met('PRm', 'PRe'), 5], ['Outlet total pressure', 'kPa', met('Pout', 'Poute'), 3], ['Outlet total temperature', '°C', met('Tm', 'Te'), 3],
    ['Battery current', 'A', met('Ib', 'Ie', r => r.N > 1000), 2], ['Electrical power', 'W', met('Pe', 'Pee', r => r.N > 1000), 1], ['Mass flow', 'kg/s', met('m', 'me'), 5]].filter(m => m[2])};
}
function dsmTable(){
  if (!DSCMP) return {head: [], rows: []};
  const ds = currentDataset(), tag = ds && ds.kind === 'measured' ? 'MEAS' : 'SIM';
  return {head: ['Channel', 'Unit', 'n', 'RMSE', 'MAE', `Bias (${tag} − EST)`, 'Max |error|', 'R²'], rows: DSCMP.metrics.map(([n, u, m, d]) => [n, u, m.n, fmt(m.rmse, d), fmt(m.mae, d), fmt(m.bias, d), fmt(m.max, d), m.r2 == null ? '–' : fmt(m.r2, 4)])};
}
const DSCHARTS = {
  'd-pr': () => { const r = DSCMP ? DSCMP.rows : []; const k = dsKindColor(); return {xlabel: 'time (s)', ylabel: 'total pressure ratio', empty: 'Upload or generate a dataset', series: [
    {x: r.map(q => q.t), y: r.map(q => q.PRe), color: 'est', width: 2, label: 'expected EST'}, {x: r.map(q => q.t), y: r.map(q => q.PRm), color: k, width: 1.1, label: k === 'meas' ? 'MEAS' : 'SIM'}]}; },
  'd-t': () => { const r = DSCMP ? DSCMP.rows : []; const k = dsKindColor(); return {xlabel: 'time (s)', ylabel: 'outlet T₀ (°C)', empty: 'Upload or generate a dataset', series: [
    {x: r.map(q => q.t), y: r.map(q => q.Te), color: 'est', width: 2, label: 'expected EST (steady)'}, {x: r.map(q => q.t), y: r.map(q => q.Tm), color: k, width: 1.1, label: k === 'meas' ? 'MEAS' : 'SIM'}]}; },
  'd-par': () => { const r = DSCMP ? DSCMP.rows.filter(q => q.N > 4000 && q.PRm != null) : []; const k = dsKindColor(); const lo = 1.0, hi = Math.max(1.02, ...r.map(q => Math.max(q.PRm, q.PRe))) + 0.005;
    return {xlabel: 'expected PR (EST)', ylabel: 'measured PR', x: [lo, hi], y: [lo, hi], empty: 'Upload or generate a dataset', series: [{x: [lo, hi], y: [lo, hi], color: 'des', dash: [5, 4], width: 1, label: 'y = x'}, {x: r.map(q => q.PRe), y: r.map(q => q.PRm), color: k, line: false, marker: 'o', msize: 2.2, label: k === 'meas' ? 'MEAS' : 'SIM'}]}; },
  'd-i': () => { const r = DSCMP ? DSCMP.rows : []; const k = dsKindColor(); return {xlabel: 'time (s)', ylabel: 'battery current (A)', y0zero: true, empty: 'Upload or generate a dataset', series: [
    {x: r.map(q => q.t), y: r.map(q => q.Ie), color: 'est', width: 2, label: 'expected EST'}, {x: r.map(q => q.t), y: r.map(q => q.Ib), color: k, width: 1.1, label: k === 'meas' ? 'MEAS' : 'SIM'}]}; },
};
function dsKindColor(){ const ds = currentDataset(); return ds && ds.kind === 'measured' ? 'meas' : 'sim'; }
function renderDatasetCharts(){
  const ds = currentDataset(); DSCMP = compareDataset(ds);
  if (ds) $('#ds-info').textContent = `${ds.kind === 'measured' ? 'Measured' : 'Simulated'} · ${ds.n_rows} rows · uploaded ${new Date(ds.uploaded_at).toLocaleString()}${ds.raw_asset_id ? ' · raw file stored' : ''}`;
  if (VIEW === 'compare') Object.keys(DSCHARTS).forEach(id => { const f = fitCanvas($('#' + id)); if (f) plot(f[0], f[1], f[2], TOK, DSCHARTS[id]()); });
  const t = dsmTable(); $('#dsm-table').innerHTML = t.rows.length ? tableHTML(t) : '<tbody><tr><td class="empty">No dataset selected. Upload a CSV log or generate the simulated example.</td></tr></tbody>';
}

/* ------------------------------------------------------------------ experiment log */
function entryFromLive(){
  const m = S.meas, e = S.est, me = S.mest; if (!m || !e) return null;
  return {test_id: $('#lg-test').value.trim() || `T-${String(REC.experiments.length + 1).padStart(3, '0')}`, operator: $('#lg-op').value.trim(),
    source: m.kind === 'meas' ? 'measured' : 'simulated', origin: S.source === 'rig' ? 'virtual rig' : 'replay: ' + S.replay.name,
    rpm: +m.N.toFixed(0), valve_pct: +(m.phi*100).toFixed(1), T_amb_C: +m.TaC.toFixed(2), P_amb_kPa: +(m.Pa/1e3).toFixed(3),
    PR_meas: m.Pout != null ? +(m.Pout/m.Pa).toFixed(5) : null, PR_est: +e.PRb.toFixed(5), T_out_meas_C: m.Tout != null ? +(m.Tout - 273.15).toFixed(3) : null, T_out_est_C: +(e.Toutb - 273.15).toFixed(3),
    I_batt_meas_A: m.Ib != null ? +m.Ib.toFixed(2) : null, I_batt_est_A: +me.Ib.toFixed(2), mdot_est_kg_s: +e.mb.toFixed(5), eta_est: +e.eta.toFixed(4), SM_est: +e.SM.toFixed(4),
    h_p: +S.kf.x[0].toFixed(4), h_T: +S.kf.x[1].toFixed(4), fault: S.source === 'rig' && S.fault !== 'none' ? `${FAULTS[S.fault].label} ${Math.round(S.sev*100)} %` : '',
    notes: $('#lg-notes').value.trim(), created_at: new Date().toISOString(), sim_time_s: +S.t.toFixed(1)};
}
async function addEntry(o){
  if (CAP.db && CAP.canWrite){ try { await CAP.db.collection('experiments').add(o); toast('Entry logged'); return; } catch (e){ toast('Could not save: ' + (e.message || e.code)); return; } }
  o.id = 'mem-' + Date.now(); REC.experiments.unshift(o); renderLog(); toast('Entry kept for this session');
}
$('#btn-logpt').addEventListener('click', () => { const o = entryFromLive(); if (o) addEntry(o); });
$('#lg-fill').addEventListener('click', () => {
  const o = entryFromLive(); if (!o) return;
  $('#lg-n').value = o.rpm; $('#lg-phi').value = o.valve_pct; $('#lg-ta').value = o.T_amb_C; $('#lg-pa').value = o.P_amb_kPa;
  $('#lg-pr').value = o.PR_meas ?? ''; $('#lg-to').value = o.T_out_meas_C ?? ''; $('#lg-i').value = o.I_batt_meas_A ?? ''; $('#lg-src').value = o.source;
});
$('#log-form').addEventListener('submit', ev => {
  ev.preventDefault();
  const n = +$('#lg-n').value, phi = (+$('#lg-phi').value || 100)/100, ta = $('#lg-ta').value === '' ? 15 : +$('#lg-ta').value, pa = $('#lg-pa').value === '' ? 101.325 : +$('#lg-pa').value;
  if (!n){ $('#lg-status').textContent = 'Enter the speed.'; return; }
  const e = romPredict(n, phi, ta + 273.15, pa*1e3), me = motorModel(n, e.Pshaft), num = id => $(id).value === '' ? null : +$(id).value;
  addEntry({test_id: $('#lg-test').value.trim() || `T-${String(REC.experiments.length + 1).padStart(3, '0')}`, operator: $('#lg-op').value.trim(), source: $('#lg-src').value, origin: 'manual entry',
    rpm: n, valve_pct: phi*100, T_amb_C: ta, P_amb_kPa: pa, PR_meas: num('#lg-pr'), PR_est: +e.PR.toFixed(5), T_out_meas_C: num('#lg-to'), T_out_est_C: +(e.Tout - 273.15).toFixed(3),
    I_batt_meas_A: num('#lg-i'), I_batt_est_A: +me.Ib.toFixed(2), mdot_est_kg_s: +e.m.toFixed(5), eta_est: +e.eta.toFixed(4), SM_est: +e.SM.toFixed(4), h_p: null, h_T: null, fault: '',
    notes: $('#lg-notes').value.trim(), created_at: new Date().toISOString()});
  $('#lg-notes').value = '';
});
function logTable(){
  return {head: ['Logged', 'Test', 'Operator', 'Source', 'Speed (rpm)', 'Valve (%)', 'T_amb (°C)', 'P_amb (kPa)', 'PR meas', 'PR EST', 'T_out meas (°C)', 'T_out EST (°C)', 'I_batt meas (A)', 'I_batt EST (A)', 'ṁ EST (kg/s)', 'η EST', 'SM EST', 'h_p', 'h_T', 'Fault injected', 'Notes'],
    rows: REC.experiments.map(x => [new Date(x.created_at).toLocaleString(), x.test_id, x.operator || '', x.source === 'measured' ? 'MEAS' : 'SIM', x.rpm, x.valve_pct, x.T_amb_C, x.P_amb_kPa, x.PR_meas ?? '–', x.PR_est, x.T_out_meas_C ?? '–', x.T_out_est_C,
      x.I_batt_meas_A ?? '–', x.I_batt_est_A, x.mdot_est_kg_s, x.eta_est, x.SM_est, x.h_p ?? '–', x.h_T ?? '–', x.fault || '', x.notes || ''])};
}
function renderLog(){
  const t = logTable();
  if (!t.rows.length){ $('#log-table').innerHTML = '<tbody><tr><td class="empty">No entries yet. Use “Log this point” on the live twin or fill the form above.</td></tr></tbody>'; return; }
  $('#log-table').innerHTML = `<thead><tr>${t.head.map(h => `<th>${esc(h)}</th>`).join('')}<th></th></tr></thead><tbody>${REC.experiments.map((x, i) => `<tr>${t.rows[i].map((c, j) => `<td class="${j >= 4 && j <= 18 ? 'n' : ''}">${j === 3 ? `<span class="tag ${c === 'MEAS' ? 'meas' : 'sim'}">${c}</span>` : esc(typeof c === 'number' ? (Number.isInteger(c) ? c.toLocaleString() : c) : c)}</td>`).join('')}<td>${CAP.canWrite ? `<button class="btn sm danger" type="button" data-del="${esc(x.id)}">Delete</button>` : ''}</td></tr>`).join('')}</tbody>`;
  $$('#log-table [data-del]').forEach(b => b.addEventListener('click', async () => {
    if (b.dataset.arm !== '1'){ b.dataset.arm = '1'; b.textContent = 'Confirm'; setTimeout(() => { b.dataset.arm = ''; b.textContent = 'Delete'; }, 3000); return; }
    const id = b.dataset.del;
    if (id.startsWith('mem-')){ REC.experiments = REC.experiments.filter(x => x.id !== id); renderLog(); return; }
    try { await CAP.db.doc('experiments/' + id).delete(); } catch (e){ toast('Could not delete: ' + (e.message || e.code)); }
  }));
}

/* ------------------------------------------------------------------ checklist */
const CK_STATES = ['needed', 'ordered', 'received', 'installed', 'calibrated'];
function ckTable(){
  return {head: ['Status', 'Component', 'Specification', 'Qty', 'Unit cost (USD)', 'Line cost (USD)', 'Category', 'Link'],
    rows: REC.checklist.map(c => [c.status || 'needed', c.item, c.spec || '', c.qty ?? 1, c.unit_cost_usd != null ? fmt(c.unit_cost_usd, 2) : '–', c.unit_cost_usd != null ? fmt(c.unit_cost_usd*(c.qty || 1), 2) : '–', c.category || '', c.link || ''])};
}
function renderChecklist(){
  const items = REC.checklist;
  if (!items.length){ $('#ck-table').innerHTML = '<tbody><tr><td class="empty">No components yet. Add the first one below.</td></tr></tbody>'; $('#ck-sum').textContent = ''; $('#ck-bar').style.width = '0%'; return; }
  const done = items.filter(c => ['installed', 'calibrated'].includes(c.status)).length, cost = items.reduce((a, c) => a + (c.unit_cost_usd || 0)*(c.qty || 1), 0), priced = items.filter(c => c.unit_cost_usd != null).length;
  $('#ck-sum').textContent = `${done}/${items.length} installed or calibrated · known cost ${fmt(cost, 2)} USD (${priced} of ${items.length} priced)`;
  $('#ck-bar').style.width = (100*done/items.length).toFixed(0) + '%';
  $('#ck-table').innerHTML = `<thead><tr><th>Status</th><th>Component</th><th>Specification</th><th>Qty</th><th>Unit cost (USD)</th><th>Category</th><th>Link</th><th></th></tr></thead><tbody>${items.map(c => `<tr>
    <td><select data-id="${esc(c.id)}" data-f="status" aria-label="Status of ${esc(c.item)}" style="width:auto" ${CAP.canWrite ? '' : 'disabled'}>${CK_STATES.map(s => `<option ${s === (c.status || 'needed') ? 'selected' : ''}>${s}</option>`).join('')}</select></td>
    <td><b>${esc(c.item)}</b>${c.notes ? `<div class="small faint">${esc(c.notes)}</div>` : ''}</td><td>${esc(c.spec || '')}</td><td class="n">${esc(c.qty ?? 1)}</td>
    <td class="n"><input type="number" step="0.01" data-id="${esc(c.id)}" data-f="unit_cost_usd" value="${c.unit_cost_usd ?? ''}" aria-label="Unit cost of ${esc(c.item)}" style="width:90px" ${CAP.canWrite ? '' : 'disabled'}></td>
    <td>${esc(c.category || '')}</td><td>${c.link ? `<a href="${esc(c.link)}" target="_blank" rel="noopener">open</a>` : ''}</td>
    <td>${CAP.canWrite ? `<button class="btn sm danger" type="button" data-ckdel="${esc(c.id)}">Remove</button>` : ''}</td></tr>`).join('')}</tbody>`;
  $$('#ck-table [data-f]').forEach(el => el.addEventListener('change', async () => {
    const id = el.dataset.id, f = el.dataset.f, v = f === 'status' ? el.value : (el.value === '' ? null : +el.value);
    const it = REC.checklist.find(c => c.id === id); if (it) it[f] = v;
    if (CAP.db && !id.startsWith('mem-')){ try { await CAP.db.doc('checklist/' + id).update({[f]: v}); } catch (e){ toast('Could not save: ' + (e.message || e.code)); } } else renderChecklist();
  }));
  $$('#ck-table [data-ckdel]').forEach(b => b.addEventListener('click', async () => {
    if (b.dataset.arm !== '1'){ b.dataset.arm = '1'; b.textContent = 'Confirm'; setTimeout(() => { b.dataset.arm = ''; b.textContent = 'Remove'; }, 3000); return; }
    const id = b.dataset.ckdel;
    if (id.startsWith('mem-') || !CAP.db){ REC.checklist = REC.checklist.filter(c => c.id !== id); renderChecklist(); return; }
    try { await CAP.db.doc('checklist/' + id).delete(); } catch (e){ toast('Could not remove: ' + (e.message || e.code)); }
  }));
}
$('#ck-form').addEventListener('submit', async ev => {
  ev.preventDefault();
  const o = {item: $('#ck-item').value.trim(), spec: $('#ck-spec').value.trim(), qty: +$('#ck-qty').value || 1, unit_cost_usd: $('#ck-cost').value === '' ? null : +$('#ck-cost').value,
    category: $('#ck-cat').value, status: 'needed', order: REC.checklist.length ? Math.max(...REC.checklist.map(c => c.order || 0)) + 1 : 1, link: '', notes: ''};
  if (!o.item) return;
  if (CAP.db && CAP.canWrite){ try { await CAP.db.collection('checklist').add(o); } catch (e){ toast('Could not save: ' + (e.message || e.code)); return; } }
  else { o.id = 'mem-' + Date.now(); REC.checklist.push(o); renderChecklist(); }
  $('#ck-form').reset(); $('#ck-qty').value = 1; toast('Component added');
});

/* ------------------------------------------------------------------ ROM page */
function romTable(){
  const M = ROM.metrics, row = (n, u, k, s = 1, d = 5) => [n, u, fmt(M.test[k].RMSE*s, d), fmt(M.test[k].MAE*s, d), fmt(M.test[k].max_abs*s, d), fmt(M.test[k].R2, 6), fmt(M.stress[k].max_abs*s, d)];
  return {head: ['Output', 'Unit', 'RMSE (test)', 'MAE (test)', 'Max |error| (test)', 'R² (test)', 'Max |error| stress'], rows: [
    row('Total pressure ratio', '–', 'PR'), row('Outlet total temperature', 'K', 'T_out_K', 1, 4), row('Outlet total pressure', 'kPa', 'P_out_kPa', 1, 4), row('Mass flow', 'kg/s', 'mdot_kg_s'),
    row('Isentropic efficiency', '–', 'eta', 1, 4), row('Power to air', 'W', 'power_air_W', 1, 2), row('Surge margin', '–', 'SM', 1, 4),
    ['Pressure ratio, Gaussian process', '–', fmt(M.test.PR_GP.RMSE, 5), fmt(M.test.PR_GP.MAE, 5), fmt(M.test.PR_GP.max_abs, 5), fmt(M.test.PR_GP.R2, 6), '–'],
    ['Outlet temperature, Gaussian process', 'K', fmt(M.test.T_out_K_GP.RMSE, 4), fmt(M.test.T_out_K_GP.MAE, 4), fmt(M.test.T_out_K_GP.max_abs, 4), fmt(M.test.T_out_K_GP.R2, 6), '–']]};
}
function sweepTable(){ return {head: ['r', 'Energy captured', 'Basis-only error', 'ROM error', 'Max PR error', 'Max T_out error (K)'], rows: ROM.sweep.map(s => [s.r, fmt(s.energy, 7), fmt(s.proj_err, 5), fmt(s.rom_err, 5), fmt(s.PR_max, 5), fmt(s.Tout_max, 4)])}; }
const ROMCHARTS = {
  'r-sv': () => ({xlabel: 'mode index i', ylabel: 'log₁₀(σᵢ/σ₁)', xticks: 8, series: [{x: ROM.sigma.slice(0, 16).map((_, i) => i + 1), y: ROM.sigma.slice(0, 16).map(v => Math.log10(v/ROM.sigma[0])), color: 'est', marker: 'o', width: 1.5, label: 'singular values'},
    {x: [ROM.r, ROM.r], y: [Math.log10(ROM.sigma[15]/ROM.sigma[0]), 0], color: 'warn', dash: [4, 3], width: 1.2, label: `r = ${ROM.r} kept`}]}),
  'r-sw': () => ({xlabel: 'number of POD modes r', ylabel: 'log₁₀ relative field error', series: [
    {x: ROM.sweep.map(s => s.r), y: ROM.sweep.map(s => Math.log10(s.proj_err)), color: 'des', marker: 's', width: 1.5, label: 'basis only (projection)'},
    {x: ROM.sweep.map(s => s.r), y: ROM.sweep.map(s => Math.log10(s.rom_err)), color: 'est', marker: 'o', width: 2, label: 'ROM forecast (held-out)'}]}),
  'r-md': () => ({xlabel: 'station', ylabel: 'mode entry (scaled)', x: [-0.2, 8.2], xticks: 8, xfmt: v => (ROM.stations[Math.round(v)] || '').replace(' exit', ''), series: ROM.V.map((v, j) => ({x: [...Array(NS).keys()], y: v.slice(0, NS), color: ['est', 'alarm', 'sim', 'warn'][j % 4], marker: 'o', width: 1.6, label: `mode ${j + 1}`}))}),
  'r-par': () => { const p = ROM.points; const lo = 1.0, hi = 1.13; return {xlabel: 'FOM pressure ratio', ylabel: 'ROM pressure ratio', x: [lo, hi], y: [lo, hi], series: [{x: [lo, hi], y: [lo, hi], color: 'des', dash: [5, 4], width: 1, label: 'y = x'},
    {x: p.test.PR, y: p.test_rom.PR, color: 'est', line: false, marker: 's', msize: 3.5, label: '15 test points'}, {x: p.stress.PR, y: p.stress_rom.PR, color: 'warn', line: false, marker: 'd', msize: 4, label: 'stress (outside range)'}]}; },
  'r-doe': () => { const p = ROM.points; return {xlabel: 'speed (rpm)', ylabel: 'valve opening (–)', x: [5000, 25000], y: [0.9, 1.65], series: [
    {x: p.train.N, y: p.train.phi, color: 'est', line: false, marker: 'o', hollow: true, label: '45 training'}, {x: p.test.N, y: p.test.phi, color: 'alarm', line: false, marker: 's', label: '15 test'},
    {x: p.stress.N, y: p.stress.phi, color: 'warn', line: false, marker: 'd', msize: 4.5, label: 'stress'}, {x: [10000, 20000, 20000, 10000, 10000], y: [0.94, 0.94, 1.5, 1.5, 0.94], color: 'des', dash: [4, 3], width: 1, label: 'training domain'}]}; },
  'r-th': () => { const q = ROM.thermal_test; return {xlabel: 'time (s)', ylabel: 'max casing temperature rise (K)', y0zero: true, y2: {label: 'gas ΔT₀ input (K)'}, series: [
    {x: q.t, y: q.fom_max, color: 'des', width: 3, label: 'FOM (40 nodes)'}, {x: q.t, y: q.rom_max, color: 'est', width: 1.5, dash: [5, 3], label: `OpInf ROM (r = ${ROM.thermal.info.r})`}, {x: q.t, y: q.dT, color: 'ink-3', width: 1, axis2: true, label: 'input ΔT₀'}]}; },
};
function renderRomPage(){
  const M = ROM.metrics, th = ROM.thermal.info, tm = ROM.timing;
  const steps = [
    ['Full-order model (Module 02d)', 'Mean-line stage stacking of the real blade geometry: continuity at every station, Euler work ΔT₀ = λU(C<sub>u2</sub> − C<sub>u1</sub>)/c<sub>p</sub>, loss bucket calibrated to η<sub>s</sub> = 0.70, outlet valve as a nozzle. It reproduces the design point exactly (PR 1.1200, 301.77 K) and costs ' + tm.fom_s.toFixed(2) + ' s per operating point.'],
    ['Design of experiments (Module 02a)', '60-point Latin hypercube over speed 10,000–20,000 rpm and valve opening 0.94–1.50 (seed 2026), split 45 training / 15 test, plus 5 stress points outside the domain.'],
    ['Multi-variable snapshots (Modules 02b, 02c; wake notebook)', 'Each snapshot holds 44 values: P₀, T₀, static p and axial Mach number at 9 stations, plus incidence and diffusion factor of the 4 rotors. Each variable group is centred and scaled to unit RMS. Pressure and temperature rises are divided by x² and Mach by x (similarity), so the ROM has the right zero-speed limit.'],
    ['POD by SVD (cooling-strip notebook)', `σ₁…σ₄ = ${ROM.sigma.slice(0, 4).map(v => v.toFixed(3)).join(', ')}. ${ROM.r} modes capture ${(ROM.energy[ROM.r - 1]*100).toFixed(5)} % of the variance. r was chosen from captured energy and the held-out error, not energy alone.`],
    ['Parametric ROM (surrogate of the amplitudes)', `Polynomials in (x, φ) map the operating point to the ${ROM.r} POD amplitudes; leave-one-out CV chose degrees ${ROM.amp.map(a => a.degree).join(', ')}. A Gaussian process was fitted for comparison (table). Online cost: ${tm.rom_python_us.toFixed(0)} µs in Python, about ${Math.round(tm.fom_s*1e6/tm.rom_python_us).toLocaleString()} times faster than the FOM.`],
    ['Dynamic thermal ROM by operator inference', `40-node PLA-casing conduction and convection model, snapshot pairs from 4 random input histories, ${th.r} POD modes. Operators fitted from data: a<sub>k+1</sub> = A<sub>r</sub>a<sub>k</sub> + u₁N<sub>r</sub>a<sub>k</sub> + u₂b<sub>r</sub>. Their Galerkin cross-check gives ‖K<sub>data</sub> − K<sub>physics</sub>‖ = ${th.op_diff_data_vs_physics.toExponential(1)}. The held-out run has a maximum error of ${th.test_max_err_K.toFixed(3)} K; the casing time constant is ${th.tau_s.toFixed(0)} s.`],
    ['Sensing and observability (Module 03a)', `With outlet P₀ and T₀ only, the ${ROM.r} amplitudes give rank ${ROM.observability.rank}: overall degradation is visible, but not which stage. Adding a mid-machine tap and a bellmouth inlet tap raises the rank to ${ROM.observability.rank_with_midtaps_and_bellmouth} (condition number ${ROM.observability.cond_with_midtaps_and_bellmouth.toFixed(1)}).`],
    ['Synchronisation and use (Modules 03b, 04a)', 'A Kalman filter estimates health factors h<sub>p</sub> and h<sub>T</sub> from the measured pressure ratio and lagged outlet temperature. Residuals against the healthy baseline feed CUSUM drift tests. The adapted ROM feeds the motor speed command back to the rig.']];
  $('#rom-steps').innerHTML = steps.map(([t, p]) => `<div class="step"><div><b>${t}</b><p>${p}</p></div></div>`).join('');
  $('#romv-table').innerHTML = tableHTML(romTable());
  $('#rom-note').innerHTML = `Field error on the test set: ${(M.test.field_rel_err*100).toFixed(2)} % (basis-only ${(M.test.field_proj_err*100).toFixed(2)} %), so most of the remaining error comes from the amplitude maps, not the basis. Outside the training domain the error grows (field ${(M.stress.field_rel_err*100).toFixed(1)} %), so the twin flags extrapolation.`;
  setTimeout(() => renderCharts(true), 20);
}

/* ------------------------------------------------------------------ report pack: tables and figures */
const TABLES = {
  op: {title: 'Current operating point: design, expected and measured', get: opRows},
  romv: {title: 'ROM accuracy on the 15 held-out test points', get: romTable},
  sweep: {title: 'POD model-order study', get: sweepTable},
  dsm: {title: 'Dataset agreement: measured vs expected', get: dsmTable},
  log: {title: 'Experiment log', get: logTable},
  ck: {title: 'Lab component checklist', get: ckTable},
  design: {title: 'Design reference', get: () => { const d = designValues(); return {head: ['Quantity', 'Value', 'Unit'], rows: DESIGN_FIELDS.map(([k, l, u]) => [l, d[k], u])}; }},
};
const FIGS = {sim: 'Compressor simulation (current state)', 'c-pr': 'Pressure ratio vs time', 'c-n': 'Speed vs time', 'c-t': 'Temperatures vs time', 'c-p': 'Power and current vs time', 'c-map': 'Compressor map with operating point',
  'c-ax': 'Axial distribution through the stages', 'c-tri': 'Velocity triangles', 'c-kf': 'Kalman-filter health factors', 'd-pr': 'Dataset: pressure ratio', 'd-t': 'Dataset: outlet temperature', 'd-par': 'Dataset: parity plot', 'd-i': 'Dataset: battery current',
  'r-sv': 'POD spectrum', 'r-sw': 'Model-order study', 'r-md': 'POD modes', 'r-par': 'ROM parity on test points', 'r-doe': 'Design of experiments', 'r-th': 'Thermal ROM validation'};
const toCSV = t => [t.head, ...t.rows].map(r => r.map(c => { const s = String(c ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(',')).join('\n') + '\n';
const toMD = (t, title) => `**${title}**\n\n| ${t.head.map(h => String(h).replace(/\|/g, '\\|')).join(' | ')} |\n|${t.head.map(() => '---').join('|')}|\n${t.rows.map(r => `| ${r.map(c => String(c ?? '').replace(/\|/g, '\\|')).join(' | ')} |`).join('\n')}\n`;
const texEsc = s => String(s ?? '').replace(/\\/g, '\\textbackslash{}').replace(/([&%$#_{}])/g, '\\$1').replace(/~/g, '\\textasciitilde{}').replace(/\^/g, '\\^{}').replace(/−/g, '$-$').replace(/±/g, '$\\pm$').replace(/°/g, '\\textdegree{}').replace(/²/g, '$^2$').replace(/η/g, '$\\eta$').replace(/ṁ/g, '$\\dot m$').replace(/·/g, '$\\cdot$');
const toTeX = (t, title) => `% ${title}\n\\begin{table}[htbp]\n\\centering\n\\caption{${texEsc(title)}}\n\\begin{tabular}{${t.head.map((_, i) => i === 0 ? 'l' : 'r').join('')}}\n\\toprule\n${t.head.map(texEsc).join(' & ')} \\\\\n\\midrule\n${t.rows.map(r => r.map(texEsc).join(' & ') + ' \\\\').join('\n')}\n\\bottomrule\n\\end{tabular}\n\\end{table}\n`;
function exportTable(id, fmt_){
  const T = TABLES[id], t = T.get(); if (!t.rows.length){ toast('This table is empty'); return; }
  const base = id + '_' + new Date().toISOString().slice(0, 10);
  if (fmt_ === 'csv') save(base + '.csv', toCSV(t), T.title);
  if (fmt_ === 'md') save(base + '.md', toMD(t, T.title), T.title);
  if (fmt_ === 'tex') copyText(toTeX(t, T.title), 'LaTeX table');
}
function figBlob(id){
  const W = 1800, Hh = id === 'sim' ? 1058 : 1125, cv = document.createElement('canvas'); cv.width = W; cv.height = Hh;
  const ctx = cv.getContext('2d');
  if (id === 'sim') drawSim(ctx, W, Hh, PRINT, 0);
  else if (id === 'c-tri') drawTriangles(ctx, W, Hh, PRINT, +$('#tri-stage').value, 2.6);
  else { const spec = (CHARTS[id] || DSCHARTS[id] || ROMCHARTS[id])(); plot(ctx, W, Hh, PRINT, spec, 2.6); }
  return new Promise(r => cv.toBlob(r, 'image/png'));
}
async function exportFig(id){ if (id.startsWith('d-')) DSCMP = compareDataset(currentDataset()); const b = await figBlob(id); save(`${id}_${new Date().toISOString().slice(0, 10)}.png`, b, FIGS[id]); }
document.addEventListener('click', e => {
  const f = e.target.closest('[data-export-fig]'); if (f){ exportFig(f.dataset.exportFig); return; }
  const t = e.target.closest('[data-export-tbl]'); if (t){ openTableMenu(t, t.dataset.exportTbl); return; }
  const r = e.target.closest('[data-rep]'); if (r){ const [kind, id, fm] = r.dataset.rep.split(':'); kind === 't' ? exportTable(id, fm) : exportFig(id); }
});
function openTableMenu(btn, id){
  const old = document.querySelector('.tblmenu'); if (old) old.remove();
  const m = document.createElement('span'); m.className = 'tblmenu row'; m.style.gap = '4px';
  m.innerHTML = `<button class="btn sm" type="button" data-rep="t:${id}:csv">CSV</button><button class="btn sm" type="button" data-rep="t:${id}:md">Markdown</button><button class="btn sm" type="button" data-rep="t:${id}:tex">Copy LaTeX</button>`;
  btn.after(m); setTimeout(() => { const off = ev => { if (!m.contains(ev.target) && ev.target !== btn){ m.remove(); document.removeEventListener('click', off); } }; document.addEventListener('click', off); }, 0);
}
function renderReport(){
  $('#rep-tables').innerHTML = `<thead><tr><th>Table</th><th>Rows</th><th>Export</th></tr></thead><tbody>${Object.entries(TABLES).map(([id, T]) => { let n = 0; try { n = T.get().rows.length; } catch (e) {}
    return `<tr><td>${esc(T.title)}</td><td class="n">${n}</td><td><span class="row" style="gap:4px;flex-wrap:wrap"><button class="btn sm" type="button" data-rep="t:${id}:csv">CSV</button><button class="btn sm" type="button" data-rep="t:${id}:md">Markdown</button><button class="btn sm" type="button" data-rep="t:${id}:tex">Copy LaTeX</button></span></td></tr>`; }).join('')}</tbody>`;
  $('#rep-figs').innerHTML = `<thead><tr><th>Figure</th><th>Section</th><th>Export</th></tr></thead><tbody>${Object.entries(FIGS).map(([id, t]) => `<tr><td>${esc(t)}</td><td>${id === 'sim' || id.startsWith('c-') ? 'Live twin' : id.startsWith('d-') ? 'Design & data' : 'ROM & validation'}</td><td><button class="btn sm" type="button" data-rep="f:${id}">PNG</button></td></tr>`).join('')}</tbody>`;
}

/* ------------------------------------------------------------------ start */
resetRig();
renderLog(); renderChecklist(); renderDesignForm(); renderDatasetSelect();
route();
requestAnimationFrame(frame);
