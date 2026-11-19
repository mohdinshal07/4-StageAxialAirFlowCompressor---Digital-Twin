'use strict';
/* =====================================================================================================
   draw.js: theme tokens, colour maps, the animated compressor (meridional + cascade), velocity
   triangles and a small chart plotter used for every figure (screen and PNG export).
   ===================================================================================================== */
const TOKS = ['bg', 'panel', 'panel-2', 'ink', 'ink-2', 'ink-3', 'line', 'accent', 'meas', 'sim', 'est', 'des', 'ok', 'warn', 'alarm', 'metal', 'metal-2', 'hub'];
let TOK = {};
function readTokens(){ const cs = getComputedStyle(document.documentElement); TOKS.forEach(k => TOK[k] = cs.getPropertyValue('--' + k).trim() || '#888'); }
const PRINT = {bg: '#ffffff', panel: '#ffffff', 'panel-2': '#f3f5f7', ink: '#111111', 'ink-2': '#444444', 'ink-3': '#777777', line: '#d0d5da',
  accent: '#1f4e79', meas: '#0e7469', sim: '#6a4fa0', est: '#1e62b0', des: '#6b7280', ok: '#17803d', warn: '#b26e12', alarm: '#c42222',
  metal: '#8b98a3', 'metal-2': '#c3ccd3', hub: '#5b6872'};
const col = (tok, c) => (c && tok[c]) || c || tok.ink;

/* ------------------------------------------------------------------ colour maps */
const CMAP = [[0, [38, 48, 107]], [0.25, [31, 120, 180]], [0.5, [43, 179, 159]], [0.75, [233, 196, 71]], [1, [216, 69, 42]]];
function cmap(t){
  t = clamp(t, 0, 1); let i = 0; while (i < CMAP.length - 2 && t > CMAP[i + 1][0]) i++;
  const [t0, c0] = CMAP[i], [t1, c1] = CMAP[i + 1], w = (t - t0)/(t1 - t0);
  return `rgb(${Math.round(lerp(c0[0], c1[0], w))},${Math.round(lerp(c0[1], c1[1], w))},${Math.round(lerp(c0[2], c1[2], w))})`;
}
function heat(t){ t = clamp(t, 0, 1); return `rgb(${Math.round(lerp(70, 220, t))},${Math.round(lerp(130, 60, t))},${Math.round(lerp(200, 40, t))})`; }
const FIELD = {
  P0: {label: 'P₀ − p_amb (kPa)', get: e => e.P0.map(v => (v - e.PaPa)/1e3), lo: 0, hi: 16},
  T0: {label: 'T₀ (°C)', get: e => e.T0.map(v => v - 273.15), lo: null, hi: null},
  p:  {label: 'p − p_amb (kPa)', get: e => e.p.map(v => (v - e.PaPa)/1e3), lo: -3, hi: 12},
  Ca: {label: 'Cₐ (m/s)', get: e => e.Ca, lo: 0, hi: 70},
};

/* ------------------------------------------------------------------ axial geometry (metres; s = 0 at the first module face) */
const STATION_S = [0.002]; for (let k = 0; k < 4; k++){ STATION_S.push(0.032*k + 0.016, 0.032*k + 0.031); }
function rhub(s){
  if (s <= 0) return GEO[0].rh[0];
  if (s >= 0.128) return GEO[3].rh[2];
  const k = Math.min(Math.floor(s/0.032), 3), m = (s - 0.032*k)/0.032, rh = GEO[k].rh;
  return m < 0.5 ? lerp(rh[0], rh[1], m/0.5) : lerp(rh[1], rh[2], (m - 0.5)/0.5);
}
function interpStations(vals, s){
  if (s <= STATION_S[0]) return vals[0];
  for (let i = 0; i < NS - 1; i++) if (s <= STATION_S[i + 1]) return lerp(vals[i], vals[i + 1], (s - STATION_S[i])/(STATION_S[i + 1] - STATION_S[i]));
  return vals[NS - 1];
}
// absolute tangential velocity Cu(s) from the velocity triangles at mean radius
function cuAt(s, e, omega){
  if (s < 0) return 0;
  const k = Math.min(Math.floor(s/0.032), 3), g = GEO[k], m = s - 0.032*k;
  const U = omega*g.rm, Ca1 = e.Ca[2*k], Ca2 = e.Ca[2*k + 1], Ca3 = e.Ca[2*k + 2];
  const Cu1 = Ca1*Math.tan(g.alpha1_deg*Math.PI/180), Cu2 = U - Ca2*Math.tan(g.beta2_deg*Math.PI/180), Cu3 = Ca3*Math.tan(g.alpha3_deg*Math.PI/180);
  if (s >= 0.128) return Cu3;
  if (m < 0.002) return Cu1;
  if (m < 0.016) return lerp(Cu1, Cu2, (m - 0.002)/0.014);
  if (m < 0.017) return Cu2;
  if (m < 0.031) return lerp(Cu2, Cu3, (m - 0.017)/0.014);
  return Cu3;
}

/* ------------------------------------------------------------------ animated compressor */
const ANIM = {mp: [], cp: [], phase: [0, 0, 0, 0], shaft: 0, last: 0, field: 'P0', slow: 2000};
function initParticles(){
  ANIM.mp = Array.from({length: 150}, () => ({s: -0.035 + rnd()*0.19, r: 0.06 + 0.88*rnd(), up: 0}));
  ANIM.cp = Array.from({length: 120}, () => ({s: -0.01 + rnd()*0.15, y: rnd()}));
}
initParticles();

function layout(W, H){
  const kx = 0.46*W/0.128, ky = kx*2.3, x0 = 0.085*W;
  const X = s => x0 + (s + 0.035)*kx;
  const Yc = 0.535*H, hubBody = 0.075*H;
  const Y = r => Yc - hubBody - (r - 0.0375)*ky;
  return {kx, ky, X, Yc, Y, Yt: Y(0.0505), casT: 12, casY0: 0.60*H, casY1: 0.985*H};
}

function drawSim(ctx, W, H, tok, dtReal, opts = {}){
  const e = S.est, L = layout(W, H), X = L.X, Y = L.Y;
  ctx.save(); ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = tok['panel-2']; ctx.fillRect(0, 0, W, H);
  const fs = Math.max(10, W/95), font = (w, sz) => `${w} ${sz}px "IBM Plex Sans", system-ui, sans-serif`, mono = sz => `${sz}px "IBM Plex Mono", ui-monospace, monospace`;
  if (!e){ ctx.restore(); return; }
  const N = e.N, omega = N*2*Math.PI/60, surge = S.surge > 0;
  // advance animation (real time)
  const dv = dtReal/ANIM.slow;
  for (let k = 0; k < 4; k++){ const pr = 2*Math.PI*GEO[k].rm/GEO[k].Z_rotor; ANIM.phase[k] = (ANIM.phase[k] + omega*GEO[k].rm*dv) % pr; }
  ANIM.shaft = (ANIM.shaft + N/60*dtReal*0.02) % 1;

  /* ---- colour field in the annulus */
  const F = FIELD[ANIM.field], vals = F.get(e);
  let lo = F.lo, hi = F.hi;
  if (ANIM.field === 'T0'){ lo = e.TaK - 273.15; hi = lo + 20; }
  const sA = -0.035, sB = 0.150, step = Math.max(2, W/400);
  for (let px = X(sA); px < X(sB); px += step){
    const s = (px - X(sA))/L.kx + sA, v = interpStations(vals, s);
    ctx.fillStyle = cmap((v - lo)/(hi - lo));
    ctx.fillRect(px, L.Yt, step + 0.6, Y(rhub(s)) - L.Yt);
  }
  /* ---- hub body, shaft, centre line */
  ctx.fillStyle = tok.hub;
  ctx.beginPath(); ctx.moveTo(X(-0.035), L.Yc);
  for (let s = -0.035; s <= 0.150; s += 0.002) ctx.lineTo(X(s), Y(rhub(s)));
  ctx.lineTo(X(0.150), L.Yc); ctx.closePath(); ctx.fill();
  // nose cone
  ctx.beginPath(); ctx.moveTo(X(-0.035), Y(rhub(0))); ctx.quadraticCurveTo(X(-0.055), L.Yc - 0.02*H, X(-0.050), L.Yc); ctx.lineTo(X(-0.035), L.Yc); ctx.fill();
  ctx.strokeStyle = tok['ink-3']; ctx.setLineDash([12, 4, 2, 4]); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, L.Yc + 0.5); ctx.lineTo(W, L.Yc + 0.5); ctx.stroke(); ctx.setLineDash([]);
  // shaft through the rear frame to the coupling and motor, with moving marks to show rotation
  const shY0 = L.Yc - 0.03*H, xm0 = 0.80*W, xm1 = 0.975*W;
  ctx.fillStyle = tok.metal; ctx.fillRect(X(0.150), shY0, xm0 - X(0.150), L.Yc - shY0);
  ctx.save(); ctx.beginPath(); ctx.rect(X(0.150), shY0, xm0 - X(0.150), L.Yc - shY0); ctx.clip();
  ctx.strokeStyle = tok.ink; ctx.globalAlpha = 0.35; ctx.lineWidth = 2;
  const sp = 0.02*W, off = ANIM.shaft*sp*8 % sp;
  for (let x = X(0.150) - sp + off; x < xm0; x += sp){ ctx.beginPath(); ctx.moveTo(x, shY0); ctx.lineTo(x + 0.4*sp, L.Yc); ctx.stroke(); }
  ctx.restore();
  // rear bearing frame and coupling
  ctx.fillStyle = tok['metal-2']; ctx.fillRect(X(0.158), L.Yt - 0.02*H, 0.012*W, L.Yc - L.Yt + 0.02*H);
  ctx.fillStyle = tok.metal; ctx.fillRect(xm0 - 0.03*W, shY0 - 0.015*H, 0.025*W, L.Yc - shY0 + 0.015*H);
  // front bearing struts in the inlet
  ctx.fillStyle = tok['metal-2']; ctx.globalAlpha = 0.8; ctx.fillRect(X(-0.028), L.Yt, 0.006*W, Y(rhub(0)) - L.Yt); ctx.globalAlpha = 1;

  /* ---- blades (meridional view) */
  for (let k = 0; k < 4; k++){
    const g = GEO[k];
    const rows = [[0.032*k + 0.002, 0.032*k + 0.016, true], [0.032*k + 0.017, 0.032*k + 0.031, false]];
    rows.forEach(([s0, s1, rot]) => {
      const pts = [[X(s0), Y(rhub(s0)) - 1], [X(s0) + 0.15*(X(s1) - X(s0)), L.Yt + 2], [X(s1), L.Yt + 2], [X(s1) - 0.1*(X(s1) - X(s0)), Y(rhub(s1)) - 1]];
      ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath();
      ctx.fillStyle = rot ? tok.metal : tok['metal-2']; ctx.globalAlpha = 0.88; ctx.fill(); ctx.globalAlpha = 1;
      ctx.strokeStyle = tok.ink; ctx.lineWidth = 0.8; ctx.stroke();
      if (rot && N > 50){ // passing-blade shading: bands sweep radially at blade-passing rate (stroboscopic)
        ctx.save(); ctx.clip(); ctx.globalAlpha = 0.28; ctx.fillStyle = tok.ink;
        const bandH = (Y(rhub(s0)) - L.Yt)/3, ph = ANIM.phase[k]/(2*Math.PI*g.rm/g.Z_rotor);
        for (let b = -1; b < 4; b++){ const y = L.Yt + (b + ph)*bandH; ctx.fillRect(X(s0), y, X(s1) - X(s0), bandH*0.35); }
        ctx.restore();
      }
    });
    // stage label and loading chip above the casing
    const cx = X(0.032*k + 0.016), dP = (e.P0[2*k + 2] - e.P0[2*k])/1e3, dT = e.T0[2*k + 2] - e.T0[2*k], DF = e.DF[k];
    const dfc = DF > 0.55 ? tok.alarm : DF > 0.48 ? tok.warn : tok.ok;
    ctx.fillStyle = tok.ink; ctx.font = font(600, fs*1.0); ctx.textAlign = 'center';
    ctx.fillText(`Stage ${k + 1}`, cx, L.Yt - L.casT - fs*4.0);
    ctx.font = mono(fs*0.78); ctx.fillStyle = tok['ink-2'];
    ctx.fillText(`ΔP₀ ${dP.toFixed(2)} kPa`, cx, L.Yt - L.casT - fs*2.95);
    ctx.fillText(`ΔT₀ ${dT.toFixed(2)} K`, cx, L.Yt - L.casT - fs*1.95);
    ctx.fillStyle = dfc; ctx.fillText(N > 1000 ? `DF ${DF.toFixed(2)} · i ${e.ir[k] >= 0 ? '+' : ''}${e.ir[k].toFixed(1)}°` : 'DF –', cx, L.Yt - L.casT - fs*0.85);
    ctx.font = font(600, fs*0.8); ctx.fillStyle = tok['ink-2'];
    ctx.fillText(`R${k + 1}`, X(0.032*k + 0.009), Y(rhub(0.032*k + 0.009)) + fs*1.1);
    ctx.fillText(`S${k + 1}`, X(0.032*k + 0.024), Y(rhub(0.032*k + 0.024)) + fs*1.1);
  }
  ctx.textAlign = 'left';

  /* ---- PLA casing wall coloured by the thermal ROM (EST) */
  const cas = casingField(S.thA), TaC = e.TaK - 273.15;
  for (let i = 0; i < TH.x.length - 1; i++){
    const s0 = TH.x[i], s1 = TH.x[i + 1], T = TaC + 0.5*(cas[i] + cas[i + 1]);
    ctx.fillStyle = heat((T - TaC)/Math.max(PLA_LIMIT - TaC, 5));
    ctx.fillRect(X(s0), L.Yt - L.casT, X(s1) - X(s0) + 0.8, L.casT);
  }
  ctx.fillStyle = tok['metal-2']; ctx.fillRect(X(-0.035), L.Yt - L.casT, X(0) - X(-0.035), L.casT); ctx.fillRect(X(0.128), L.Yt - L.casT, X(0.150) - X(0.128), L.casT);
  ctx.strokeStyle = tok.ink; ctx.lineWidth = 1; ctx.strokeRect(X(-0.035), L.Yt - L.casT, X(0.150) - X(-0.035), L.casT);
  const casMax = TaC + Math.max(...cas);
  ctx.font = mono(fs*0.8); ctx.fillStyle = tok['ink-2'];
  ctx.fillText(`PLA casing wall: max ${casMax.toFixed(1)} °C (EST, limit ${PLA_LIMIT} °C)`, X(0), L.Yt - L.casT - fs*5.6);
  // bellmouth lip
  ctx.strokeStyle = tok.ink; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(X(-0.035), L.Yt - L.casT); ctx.quadraticCurveTo(X(-0.043), L.Yt - L.casT, X(-0.044), L.Yt - L.casT - 0.035*H); ctx.stroke();

  /* ---- outlet duct and valve */
  const dx0 = X(0.136), dx1 = X(0.150), top = 0.05*H;
  const ductInterp = Math.max(0, e.Ca[NS - 1]);
  ctx.fillStyle = cmap((vals[NS - 1] - lo)/(hi - lo)); ctx.fillRect(dx0, top, dx1 - dx0, L.Yt - L.casT - top);
  ctx.strokeStyle = tok.ink; ctx.lineWidth = 1.5; ctx.strokeRect(dx0, top, dx1 - dx0, L.Yt - L.casT - top);
  const vy = 0.13*H, ang = (1 - clamp((S.phi - 0.9)/0.7, 0, 1))*70*Math.PI/180, half = (dx1 - dx0)/2;
  ctx.save(); ctx.translate((dx0 + dx1)/2, vy); ctx.rotate(Math.PI/2 - ang);
  ctx.strokeStyle = tok.ink; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(-half*0.95, 0); ctx.lineTo(half*0.95, 0); ctx.stroke();
  ctx.fillStyle = tok.ink; ctx.beginPath(); ctx.arc(0, 0, 3, 0, 7); ctx.fill(); ctx.restore();
  ctx.font = font(600, fs*0.9); ctx.fillStyle = tok.ink; ctx.fillText(`Outlet valve ${(S.phi*100).toFixed(0)} %`, dx1 + 8, vy + 4);
  ctx.font = mono(fs*0.82); ctx.fillStyle = tok['ink-2'];
  ctx.fillText(`P₀ ${(e.Pout/1e3).toFixed(2)} kPa · T₀ ${(e.Tout - 273.15).toFixed(2)} °C`, dx1 + 8, vy + 4 + fs*1.25);
  ctx.fillText(`PR ${e.PR.toFixed(4)} · ṁ ${e.m.toFixed(4)} kg/s`, dx1 + 8, vy + 4 + fs*2.4);
  // inlet labels
  ctx.font = font(600, fs*0.9); ctx.fillStyle = tok.ink; ctx.fillText('Inlet', 0.02*W, 0.17*H);
  ctx.font = mono(fs*0.82); ctx.fillStyle = tok['ink-2'];
  ctx.fillText(`T ${(e.TaK - 273.15).toFixed(1)} °C`, 0.02*W, 0.17*H + fs*1.2); ctx.fillText(`p ${(e.PaPa/1e3).toFixed(2)} kPa`, 0.02*W, 0.17*H + fs*2.3);

  /* ---- motor */
  const mt = S.motEst.Tw, mest = S.mest || {tq: 0, Ib: 0, Pe: 0};
  const my0 = L.Yc - 0.30*H;
  ctx.fillStyle = tok.metal; roundRect(ctx, xm0, my0, xm1 - xm0, L.Yc - my0, 8); ctx.fill();
  ctx.globalAlpha = 0.55; ctx.fillStyle = heat((mt - TaC)/Math.max(MOTOR.Tlim - TaC, 10)); roundRect(ctx, xm0 + 4, my0 + 4, xm1 - xm0 - 8, L.Yc - my0 - 8, 6); ctx.fill(); ctx.globalAlpha = 1;
  ctx.fillStyle = tok.ink; ctx.font = font(700, fs*0.95); ctx.fillText('BLDC motor', xm0 + 8, my0 + fs*1.4);
  ctx.font = mono(fs*0.8);
  [`${Math.round(N).toLocaleString()} rpm`, `τ ${mest.tq.toFixed(2)} N·m`, `I_batt ${mest.Ib.toFixed(1)} A`, `P_el ${(mest.Pe/1e3).toFixed(2)} kW`, `winding ${mt.toFixed(0)} °C`].forEach((t, i) => ctx.fillText(t, xm0 + 8, my0 + fs*(2.7 + 1.15*i)));
  ctx.font = font(500, fs*0.72); ctx.fillStyle = tok['ink-2']; ctx.fillText('EST: motor model', xm0 + 8, L.Yc - 6);

  /* ---- meridional tracers */
  ctx.fillStyle = tok.bg === '#0D1419' ? '#ffffff' : '#ffffff';
  const surgeFlow = surge ? Math.sin(2*Math.PI*3.2*S.t) : 1;
  ANIM.mp.forEach(p => {
    let v;
    if (p.up){ v = Math.max(ductInterp, 2)*0.8; p.up += v*dv/ (L.Yt - top) * L.kx; }
    else {
      const ca = interpStations(e.Ca, Math.max(p.s, 0));
      v = p.s < 0 ? ca*(0.45 + 0.55*(p.s + 0.035)/0.035) : ca;
      p.s += v*dv*surgeFlow;
      if (p.s > 0.137 + 0.012*p.r) p.up = 1e-6;
      if (p.s < -0.035) p.s = 0.12;
    }
    if (p.up > 1 || N < 30 && rnd() < 0.002){ p.s = -0.035 - 0.004*rnd(); p.up = 0; p.r = 0.06 + 0.88*rnd(); }
    let px, py;
    if (p.up){ px = X(0.137) + (X(0.149) - X(0.137))*p.r; py = (L.Yt - L.casT) - p.up*(L.Yt - L.casT - top); }
    else { px = X(p.s); const yh = Y(rhub(Math.max(Math.min(p.s, 0.150), -0.035))); py = L.Yt + 3 + p.r*(yh - L.Yt - 6); }
    ctx.globalAlpha = 0.85; ctx.fillStyle = surge ? tok.alarm : '#ffffff'; ctx.beginPath(); ctx.arc(px, py, 1.6, 0, 7); ctx.fill();
  });
  ctx.globalAlpha = 1;

  /* ---- field legend */
  const lgX = 0.02*W, lgY = 0.045*H, lgW = 0.16*W, lgH = 0.016*H;
  for (let i = 0; i < 60; i++){ ctx.fillStyle = cmap(i/59); ctx.fillRect(lgX + i*lgW/60, lgY, lgW/60 + 0.6, lgH); }
  ctx.strokeStyle = tok.ink; ctx.lineWidth = 0.8; ctx.strokeRect(lgX, lgY, lgW, lgH);
  ctx.fillStyle = tok['ink-2']; ctx.font = mono(fs*0.75);
  ctx.fillText(lo.toFixed(ANIM.field === 'Ca' ? 0 : 1), lgX, lgY + lgH + fs*1.1); ctx.textAlign = 'right'; ctx.fillText(hi.toFixed(ANIM.field === 'Ca' ? 0 : 1), lgX + lgW, lgY + lgH + fs*1.1); ctx.textAlign = 'left';
  ctx.font = font(600, fs*0.8); ctx.fillStyle = tok.ink; ctx.fillText('Field: ' + F.label, lgX, lgY - fs*0.4);

  /* ---- cascade (blade-to-blade) view at mean radius */
  const c0 = L.casY0, c1 = L.casY1, ch = c1 - c0;
  ctx.fillStyle = tok.panel; ctx.fillRect(X(-0.035), c0, X(0.150) - X(-0.035), ch);
  ctx.strokeStyle = tok.line; ctx.strokeRect(X(-0.035), c0, X(0.150) - X(-0.035), ch);
  ctx.save(); ctx.beginPath(); ctx.rect(X(-0.035), c0, X(0.150) - X(-0.035), ch); ctx.clip();
  const spanM = ch/L.kx;                                   // circumferential extent shown (m)
  for (let k = 0; k < 4; k++){
    const g = GEO[k], pitchR = 2*Math.PI*g.rm/g.Z_rotor, pitchS = 2*Math.PI*g.rm/g.Z_stator;
    const sR0 = 0.032*k + 0.002, sS0 = 0.032*k + 0.017, c = 0.014;
    const rotK1 = g.kappa1_rotor_deg, rotK2 = g.beta2_deg, staK1 = g.kappa1_stator_deg, staK2 = g.alpha3_deg;
    const shiftR = ANIM.phase[k];
    for (let y = -pitchR; y < spanM + 2*pitchR; y += pitchR) blade(ctx, X(sR0), c0 + (y - shiftR)*L.kx, c*L.kx, rotK1, rotK2, +1, tok.metal, tok.ink);
    for (let y = -pitchS; y < spanM + 2*pitchS; y += pitchS) blade(ctx, X(sS0), c0 + y*L.kx, c*L.kx, staK1, staK2, -1, tok['metal-2'], tok.ink);
  }
  // tracers with the absolute velocity (Ca, Cu); U points up the screen
  ANIM.cp.forEach(p => {
    const ca = p.s < 0 ? e.Ca[0] : interpStations(e.Ca, p.s), cu = cuAt(p.s, e, omega);
    p.s += ca*dv*surgeFlow; p.y = (p.y - cu*dv/spanM*surgeFlow + 10) % 1;
    if (p.s > 0.150) { p.s = -0.035; p.y = rnd(); } if (p.s < -0.035) p.s = 0.149;
    ctx.fillStyle = surge ? tok.alarm : tok.est; ctx.globalAlpha = 0.9; ctx.beginPath(); ctx.arc(X(p.s), c0 + p.y*ch, 1.8, 0, 7); ctx.fill();
  });
  ctx.restore(); ctx.globalAlpha = 1;
  ctx.fillStyle = tok['ink-2']; ctx.font = font(600, fs*0.85);
  ctx.fillText('Blade-to-blade view at mean radius (rotor rows move, stator rows fixed)', X(-0.035), c0 - fs*0.5);
  // U arrow
  const ax = X(0.150) + 14, ay = c0 + ch*0.75;
  ctx.strokeStyle = tok.ink; ctx.fillStyle = tok.ink; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(ax, ay - 0.10*H); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(ax - 5, ay - 0.10*H + 8); ctx.lineTo(ax, ay - 0.10*H); ctx.lineTo(ax + 5, ay - 0.10*H + 8); ctx.stroke();
  ctx.font = mono(fs*0.8); ctx.fillText(`U = ${(omega*GEO[0].rm).toFixed(1)} m/s`, ax + 8, ay - 0.05*H);
  ctx.fillText('rotor motion', ax + 8, ay - 0.05*H + fs*1.1);
  ctx.fillText(`slowed ${ANIM.slow}×`, ax + 8, ay - 0.05*H + fs*2.2);
  if (surge){ ctx.fillStyle = tok.alarm; ctx.globalAlpha = 0.10 + 0.08*Math.sin(S.t*20); ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
  ctx.restore();
}
function roundRect(ctx, x, y, w, h, r){ ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
// cambered blade: camber angle varies linearly from k1 to k2 (deg from axial); dir +1 = rotor (turns towards +y screen), -1 = stator
function blade(ctx, x0, y0, len, k1, k2, dir, fill, stroke){
  const n = 12, pts = [[x0, y0]]; let x = x0, y = y0;
  for (let i = 0; i < n; i++){ const a = (k1 + (k2 - k1)*(i + 0.5)/n)*Math.PI/180, dx = len/n; x += dx; y += dir*dx*Math.tan(a); pts.push([x, y]); }
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.strokeStyle = stroke; ctx.lineWidth = Math.max(3.2, len*0.13); ctx.globalAlpha = 0.5;
  ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.stroke();
  ctx.strokeStyle = fill; ctx.lineWidth = Math.max(2, len*0.10); ctx.globalAlpha = 1; ctx.stroke();
}

/* ------------------------------------------------------------------ velocity triangles */
function drawTriangles(ctx, W, H, tok, k, fsScale = 1){
  ctx.clearRect(0, 0, W, H); ctx.fillStyle = tok.panel; ctx.fillRect(0, 0, W, H);
  const fs = 11*fsScale, e = S.est;
  if (!e || e.N < 500){ ctx.fillStyle = tok['ink-2']; ctx.font = `${fs*1.1}px "IBM Plex Sans",sans-serif`; ctx.fillText('Speed too low to draw the triangles', 14*fsScale, 30*fsScale); return; }
  const g = GEO[k], U = e.N*2*Math.PI/60*g.rm, Ca1 = e.Ca[2*k], Ca2 = e.Ca[2*k + 1];
  const Cu1 = Ca1*Math.tan(g.alpha1_deg*Math.PI/180), Cu2 = U - Ca2*Math.tan(g.beta2_deg*Math.PI/180);
  const b1 = Math.atan2(U - Cu1, Ca1)*180/Math.PI, a2 = Math.atan2(Cu2, Ca2)*180/Math.PI;
  const top = 0.20*H, avail = 0.52*H, sc = Math.min(0.34*W/Math.max(Ca1, Ca2, 1), avail/(U + Math.max(Cu1, Cu2, 0)));
  const oy = top + Math.max(Cu1, Cu2, 0)*sc;
  // legend on one line
  ctx.font = `${fs*0.9}px "IBM Plex Sans",sans-serif`; let lx = 10*fsScale;
  [['C absolute', tok.est, []], ['W relative', tok.sim, []], ['U blade', tok.ink, []], ['metal angle κ₁', tok.warn, [5, 4]]].forEach(([t, c, d]) => {
    ctx.strokeStyle = c; ctx.lineWidth = 2*fsScale; ctx.setLineDash(d.map(v => v*fsScale)); ctx.beginPath(); ctx.moveTo(lx, 12*fsScale); ctx.lineTo(lx + 16*fsScale, 12*fsScale); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = tok['ink-2']; ctx.fillText(t, lx + 20*fsScale, 15*fsScale); lx += 30*fsScale + ctx.measureText(t).width; });
  const tri = (ox, Ca, Cu, label, metal) => {
    const C = [ox + Ca*sc, oy - Cu*sc], Wt = [ox + Ca*sc, oy + (U - Cu)*sc];
    if (metal != null){ const a = metal*Math.PI/180, Lm = 1.05*Math.hypot(Ca, U - Cu)*sc; ctx.setLineDash([5*fsScale, 4*fsScale]); ctx.strokeStyle = tok.warn; ctx.lineWidth = 1.5*fsScale;
      ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(ox + Lm*Math.cos(a), oy + Lm*Math.sin(a)); ctx.stroke(); ctx.setLineDash([]); }
    arrow(ctx, ox, oy, C[0], C[1], tok.est, 2.2*fsScale); arrow(ctx, ox, oy, Wt[0], Wt[1], tok.sim, 2.2*fsScale); arrow(ctx, Wt[0], Wt[1], C[0], C[1], tok.ink, 1.5*fsScale);
    ctx.fillStyle = tok.ink; ctx.font = `600 ${fs}px "IBM Plex Sans",sans-serif`; ctx.fillText(label, ox, top - Math.max(Cu1, Cu2, 0)*0 - 8*fsScale);
  };
  tri(0.06*W, Ca1, Cu1, 'Rotor inlet', g.kappa1_rotor_deg);
  tri(0.54*W, Ca2, Cu2, 'Rotor exit', null);
  ctx.font = `${fs*0.88}px "IBM Plex Mono",monospace`; ctx.fillStyle = tok['ink-2'];
  const lines = [`U ${U.toFixed(1)} m/s · Cₐ₁ ${Ca1.toFixed(1)} · Cₐ₂ ${Ca2.toFixed(1)} m/s · DF ${e.DF[k].toFixed(3)}`,
    `β₁ ${b1.toFixed(1)}° vs metal κ₁ ${g.kappa1_rotor_deg.toFixed(1)}°  →  incidence ${(b1 - g.kappa1_rotor_deg >= 0 ? '+' : '')}${(b1 - g.kappa1_rotor_deg).toFixed(1)}°`,
    `α₂ ${a2.toFixed(1)}° · β₂ ${g.beta2_deg.toFixed(1)}° · ΔT₀ = λU(Cᵤ₂ − Cᵤ₁)/cₚ = ${(g.lam*U*(Cu2 - Cu1)/CP).toFixed(2)} K`];
  lines.forEach((t, i) => ctx.fillText(t, 10*fsScale, H - (lines.length - i - 0.3)*fs*1.4));
}
function arrow(ctx, x0, y0, x1, y1, c, w){
  ctx.strokeStyle = c; ctx.fillStyle = c; ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
  const a = Math.atan2(y1 - y0, x1 - x0), L = 8 + w*2; ctx.beginPath(); ctx.moveTo(x1, y1);
  ctx.lineTo(x1 - L*Math.cos(a - 0.35), y1 - L*Math.sin(a - 0.35)); ctx.lineTo(x1 - L*Math.cos(a + 0.35), y1 - L*Math.sin(a + 0.35)); ctx.closePath(); ctx.fill();
}

/* ------------------------------------------------------------------ chart plotter */
function niceTicks(lo, hi, n = 5){
  if (!(hi > lo)){ hi = lo + 1; }
  const raw = (hi - lo)/n, mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw/mag;
  const st = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10)*mag, t = [];
  for (let v = Math.ceil(lo/st - 1e-9)*st; v <= hi + st*1e-6; v += st) t.push(+v.toPrecision(12));
  return {t, st};
}
function fmtTick(v, st){ const d = Math.max(0, -Math.floor(Math.log10(st) + 1e-9)); return Math.abs(v) >= 10000 ? v.toLocaleString(undefined, {maximumFractionDigits: 0}) : v.toFixed(Math.min(d, 5)); }
function plot(ctx, W, H, tok, spec, fsScale = 1){
  ctx.save(); ctx.clearRect(0, 0, W, H); ctx.fillStyle = tok.panel; ctx.fillRect(0, 0, W, H);
  const fs = 11*fsScale, padL = 56*fsScale, padR = (spec.y2 ? 50 : 22)*fsScale, padB = 38*fsScale;
  // legend layout first (wraps onto extra lines), so the plot area starts below it
  ctx.font = `${fs*0.95}px "IBM Plex Sans",sans-serif`;
  const legItems = []; { let lx = padL + 2*fsScale, line = 0;
    spec.series.filter(s => s.label).forEach(s => { const w = 28*fsScale + ctx.measureText(s.label).width; if (lx + w > W - 6*fsScale && lx > padL + 2*fsScale){ line++; lx = padL + 2*fsScale; } legItems.push({s, x: lx, line}); lx += w; }); }
  const nLeg = legItems.length ? Math.max(...legItems.map(i => i.line)) + 1 : 0, padT = (12 + nLeg*14)*fsScale;
  const pw = W - padL - padR, ph = H - padT - padB;
  const all = (k, ser) => ser.flatMap(s => (s[k] || []).filter(v => v != null && isFinite(v)));
  const bandVals = spec.series.flatMap(s => s.band ? [...s.band.lo, ...s.band.hi].filter(v => v != null && isFinite(v)) : []);
  let xs = all('x', spec.series), ys = all('y', spec.series.filter(s => !s.axis2)).concat(bandVals, (spec.hlines || []).map(h => h.y));
  if (!xs.length){ ctx.fillStyle = tok['ink-2']; ctx.font = `${fs*1.1}px "IBM Plex Sans",sans-serif`; ctx.fillText(spec.empty || 'No data yet', padL, padT + 20*fsScale); ctx.restore(); return; }
  let [x0, x1] = spec.x || [Math.min(...xs), Math.max(...xs)], [y0, y1] = spec.y || [Math.min(...ys), Math.max(...ys)];
  if (x1 - x0 < 1e-12){ x0 -= 1; x1 += 1; }
  if (!spec.y){ const pad = (y1 - y0)*0.08 || Math.abs(y0)*0.01 || 1; y0 -= pad; y1 += pad; if (spec.y0zero) y0 = Math.min(0, y0); }
  const X = v => padL + (v - x0)/(x1 - x0)*pw, Y = v => padT + ph - (v - y0)/(y1 - y0)*ph;
  let Y2 = null, ys2 = null;
  if (spec.y2){ const v2 = all('y', spec.series.filter(s => s.axis2)); let a = spec.y2.lim ? spec.y2.lim[0] : Math.min(...v2), b = spec.y2.lim ? spec.y2.lim[1] : Math.max(...v2); if (!spec.y2.lim){ const p = (b - a)*0.08 || 1; a -= p; b += p; } ys2 = [a, b]; Y2 = v => padT + ph - (v - a)/(b - a)*ph; }
  // grid and ticks
  ctx.font = `${fs}px "IBM Plex Mono",monospace`; ctx.lineWidth = 1;
  const tx = niceTicks(x0, x1, spec.xticks || 6), ty = niceTicks(y0, y1, 5);
  ctx.strokeStyle = tok.line; ctx.fillStyle = tok['ink-2'];
  ty.t.forEach(v => { if (v < y0 - 1e-12 || v > y1 + 1e-12) return; const y = Math.round(Y(v)) + 0.5; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + pw, y); ctx.stroke(); ctx.textAlign = 'right'; ctx.fillText(fmtTick(v, ty.st), padL - 6*fsScale, y + fs*0.35); });
  tx.t.forEach(v => { if (v < x0 - 1e-12 || v > x1 + 1e-12) return; const x = Math.round(X(v)) + 0.5; ctx.globalAlpha = 0.55; ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + ph); ctx.stroke(); ctx.globalAlpha = 1; ctx.textAlign = 'center'; ctx.fillText(spec.xfmt ? spec.xfmt(v) : fmtTick(v, tx.st), x, padT + ph + fs*1.45); });
  if (Y2){ const t2 = niceTicks(ys2[0], ys2[1], 5); ctx.textAlign = 'left'; t2.t.forEach(v => { if (v < ys2[0] || v > ys2[1]) return; ctx.fillText(fmtTick(v, t2.st), padL + pw + 6*fsScale, Y2(v) + fs*0.35); }); }
  ctx.strokeStyle = tok['ink-3']; ctx.strokeRect(padL + 0.5, padT + 0.5, pw, ph);
  ctx.fillStyle = tok['ink-2']; ctx.font = `500 ${fs}px "IBM Plex Sans",sans-serif`; ctx.textAlign = 'center';
  ctx.fillText(spec.xlabel || '', padL + pw/2, H - 6*fsScale);
  ctx.save(); ctx.translate(13*fsScale, padT + ph/2); ctx.rotate(-Math.PI/2); ctx.fillText(spec.ylabel || '', 0, 0); ctx.restore();
  if (spec.y2){ ctx.save(); ctx.translate(W - 8*fsScale, padT + ph/2); ctx.rotate(Math.PI/2); ctx.fillText(spec.y2.label || '', 0, 0); ctx.restore(); }
  ctx.textAlign = 'left';
  ctx.save(); ctx.beginPath(); ctx.rect(padL, padT, pw, ph); ctx.clip();
  (spec.hlines || []).forEach(h => { ctx.strokeStyle = col(tok, h.color); ctx.setLineDash(h.dash || [5, 4]); ctx.lineWidth = 1.2*fsScale; const y = Y(h.y); ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + pw, y); ctx.stroke(); ctx.setLineDash([]);
    if (h.label){ ctx.fillStyle = col(tok, h.color); ctx.font = `${fs*0.9}px "IBM Plex Sans",sans-serif`; ctx.fillText(h.label, padL + 6*fsScale, y - 4*fsScale); } });
  spec.series.forEach(s => {
    const c = col(tok, s.color), YY = s.axis2 ? Y2 : Y;
    if (s.band){ ctx.fillStyle = c; ctx.globalAlpha = 0.15; ctx.beginPath(); let started = false;
      s.x.forEach((xv, i) => { const v = s.band.hi[i]; if (v == null) return; started ? ctx.lineTo(X(xv), YY(v)) : (ctx.moveTo(X(xv), YY(v)), started = true); });
      for (let i = s.x.length - 1; i >= 0; i--){ const v = s.band.lo[i]; if (v != null) ctx.lineTo(X(s.x[i]), YY(v)); } ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1; }
    if (s.line !== false){ ctx.strokeStyle = c; ctx.lineWidth = (s.width || 1.6)*fsScale; ctx.setLineDash((s.dash || []).map(d => d*fsScale)); ctx.globalAlpha = s.alpha || 1;
      ctx.beginPath(); let pen = false;
      s.x.forEach((xv, i) => { const yv = s.y[i]; if (yv == null || !isFinite(yv) || xv == null){ pen = false; return; } const px = X(xv), py = YY(yv); pen ? ctx.lineTo(px, py) : ctx.moveTo(px, py); pen = true; });
      ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1; }
    if (s.marker){ ctx.fillStyle = s.hollow ? tok.panel : c; ctx.strokeStyle = c; ctx.lineWidth = 1.3*fsScale; const r = (s.msize || 3.2)*fsScale;
      s.x.forEach((xv, i) => { const yv = s.y[i]; if (yv == null || !isFinite(yv)) return; const px = X(xv), py = YY(yv); ctx.beginPath();
        if (s.marker === 's') ctx.rect(px - r, py - r, 2*r, 2*r); else if (s.marker === 'd'){ ctx.moveTo(px, py - r*1.4); ctx.lineTo(px + r*1.4, py); ctx.lineTo(px, py + r*1.4); ctx.lineTo(px - r*1.4, py); ctx.closePath(); } else ctx.arc(px, py, r, 0, 7);
        ctx.fill(); ctx.stroke(); }); }
    if (s.labels){ ctx.fillStyle = c; ctx.font = `${fs*0.85}px "IBM Plex Mono",monospace`; s.labels.forEach((t, i) => { if (t && s.y[i] != null) ctx.fillText(t, X(s.x[i]) + 4*fsScale, Y(s.y[i]) - 4*fsScale); }); }
  });
  ctx.restore();
  // legend
  ctx.font = `${fs*0.95}px "IBM Plex Sans",sans-serif`;
  legItems.forEach(({s, x: lx, line}) => { const ly = (10 + line*14)*fsScale, c = col(tok, s.color); ctx.strokeStyle = c; ctx.fillStyle = c; ctx.lineWidth = 2*fsScale; ctx.setLineDash((s.dash || []).map(d => d*fsScale));
    if (s.line !== false){ ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(lx + 16*fsScale, ly); ctx.stroke(); } else { ctx.beginPath(); ctx.arc(lx + 8*fsScale, ly, 3*fsScale, 0, 7); ctx.fill(); }
    ctx.setLineDash([]); ctx.fillStyle = tok['ink-2']; ctx.fillText(s.label, lx + 20*fsScale, ly + fs*0.35); });
  ctx.restore();
}
