'use strict';
/* =====================================================================================================
   core.js: ROM evaluation, motor model, thermal ROM, virtual rig, Kalman filter, CUSUM, controller.
   All physics constants and ROM operators come from rom_pod.json, built offline by build_pod_rom.py.
   ===================================================================================================== */
const ROM = JSON.parse(document.getElementById('rom-data').textContent);
const MAP = JSON.parse(document.getElementById('map-data').textContent);
const REF = ROM.meta.reference, NS = 9, EXP = REF.gamma/(REF.gamma - 1), CP = REF.cp, ETA_MECH = 0.97;
const GEO = ROM.geometry.stages;
const DESIGN_DEFAULT = {
  stages: 4, N_rpm: 20000, PR: 1.12, mdot_kg_s: 0.2082, T_in_C: 15.0, P_in_kPa: 101.325,
  T_out_C: +(ROM.design.T_out - 273.15).toFixed(2), P_out_kPa: +(ROM.design.P_out/1e3).toFixed(2), dT0_K: 13.62,
  eta_overall: +ROM.design.eta.toFixed(4), eta_stage: 0.70, P_air_kW: +(ROM.design.power_air/1e3).toFixed(3),
  P_shaft_kW: +(ROM.design.power_air/ETA_MECH/1e3).toFixed(3), torque_Nm: 1.40, Ca_m_s: 50, hub_in_mm: 75, tip_mm: 100,
  hub_out_mm: 76.88, rotor_blades: '38, 40, 41, 19', stator_vanes: '27, 39, 42, 26', surge_margin: +ROM.design.SM.toFixed(3)
};
// Motor, battery and thermal parameters: ASSUMED values (Hobbywing 5687SL 1100 kV class, 8S LiPo). Calibrate on the rig.
const MOTOR = {kv: 1100, R: 0.006, Pfe0: 45, esc: 0.97, Voc: 30.8, Rint: 0.020, Cw: 120, Cc: 280, Gwc: 12, Gca: 9, Tlim: 100, Pmax: 4200};
MOTOR.Kt = 60/(2*Math.PI*MOTOR.kv);
const PLA_LIMIT = 55, T_LAG = 3.0, TAU_N = 0.6, DT = 0.1;
// combined sensor + model standard uncertainties used for z-scores (1 sigma)
const SIG = {PR: 0.0015, Pout: 0.15, Tout: 0.25, I: 1.5, Pe: 45, m: 0.002, N: 30};

const clamp = (v, a, b) => Math.min(Math.max(v, a), b);
const lerp = (a, b, t) => a + (b - a)*t;
let _seed = 20261119;
function rnd(){ _seed = (_seed*1664525 + 1013904223) >>> 0; return _seed/4294967296; }
function gauss(){ let u = 0, v = 0; while (u === 0) u = rnd(); v = rnd(); return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); }

/* ------------------------------------------------------------------ parametric POD ROM */
function polyEval(m, u, v){
  let s = 0; const e = m.exps, c = m.coef;
  for (let k = 0; k < c.length; k++) s += c[k]*Math.pow(u, e[k][0])*Math.pow(v, e[k][1]);
  return s;
}
function romPredict(N, phi, TaK = REF.T, PaPa = REF.P){
  N = Math.max(N, 0);
  const th = Math.sqrt(TaK/REF.T), dl = PaPa/REF.P, x = N/th/REF.N_D;
  const xe = clamp(x, 0.5, 1.0);                       // similarity: shape outside the trained speed band taken at the band edge
  const u = (xe - ROM.norm.x[0])/ROM.norm.x[1], v = (phi - ROM.norm.phi[0])/ROM.norm.phi[1];
  const a = ROM.amp.map(m => polyEval(m, u, v));
  const nF = ROM.mean.length, F = new Float64Array(nF);
  for (let i = 0; i < nF; i++){ let q = 0; for (let j = 0; j < ROM.r; j++) q += ROM.V[j][i]*a[j]; F[i] = q*ROM.scale[i] + ROM.mean[i]; }
  const x2 = x*x, a0 = Math.sqrt(REF.gamma*REF.R*TaK);
  const P0 = [], T0 = [], p = [], Ca = [];
  for (let k = 0; k < NS; k++){ P0.push(PaPa*(1 + x2*F[k])); T0.push(TaK*(1 + x2*F[NS + k])); p.push(PaPa*(1 + x2*F[2*NS + k])); Ca.push(F[3*NS + k]*x*a0); }
  const ir = Array.from(F.slice(4*NS, 4*NS + 4)), DF = Array.from(F.slice(4*NS + 4, 4*NS + 8));
  const PR = P0[NS - 1]/PaPa, TR = T0[NS - 1]/TaK;
  const m = Math.max(polyEval(ROM.scalars.mx, u, v), 0)*x*dl/th;
  const SM = polyEval(ROM.scalars.SM, u, v);
  const eta = TR > 1 + 1e-6 ? (Math.pow(PR, 1/EXP) - 1)/(TR - 1) : NaN;
  const Pair = m*CP*(T0[NS - 1] - TaK), omega = N*2*Math.PI/60;
  const Pshaft = Pair/ETA_MECH;
  return {x, phi, N, TaK, PaPa, P0, T0, p, Ca, ir, DF, PR, TR, Pout: P0[NS - 1], Tout: T0[NS - 1], m, SM, eta, Pair, Pshaft,
          torque: omega > 1 ? Pshaft/omega : 0, a, extrap: x < 0.495 || x > 1.005 || phi < 0.935 || phi > 1.505};
}
// inverse ROM: speed that gives a target pressure ratio at this valve setting and inlet state (PR rises monotonically with N)
function romSpeedForPR(PRt, phi, TaK, PaPa, hp = 1){
  if (PRt <= 1.0001) return 0;
  const target = 1 + (PRt - 1)/hp;
  let lo = 0, hi = 26000;
  if (romPredict(hi, phi, TaK, PaPa).PR < target) return hi;
  for (let k = 0; k < 40; k++){ const mid = 0.5*(lo + hi); if (romPredict(mid, phi, TaK, PaPa).PR > target) hi = mid; else lo = mid; }
  return 0.5*(lo + hi);
}

/* ------------------------------------------------------------------ motor + battery (coupled discipline model) */
function motorModel(N, Pshaft, extraLoss = 0){
  const w = N*2*Math.PI/60, tq = w > 1 ? Pshaft/w : 0;
  const Iq = tq/MOTOR.Kt, Pcu = 1.5*MOTOR.R*Iq*Iq;
  const Pfe = MOTOR.Pfe0*Math.pow(Math.max(N, 0)/20000, 1.5) + extraLoss;
  const Pm = Pshaft + Pcu + Pfe, Pe = Pm/MOTOR.esc + (N > 50 ? 4 : 0);
  const disc = MOTOR.Voc*MOTOR.Voc - 4*MOTOR.Rint*Pe;
  const Ib = disc > 0 ? (MOTOR.Voc - Math.sqrt(disc))/(2*MOTOR.Rint) : MOTOR.Voc/(2*MOTOR.Rint);
  return {tq, Iq, Pcu, Pfe, Ploss: Pcu + Pfe, Pe, Ib, Vb: MOTOR.Voc - MOTOR.Rint*Ib, eta_m: Pe > 0 ? Pshaft/Pe : 0};
}
function motorThermalStep(st, Ploss, TaC, dt){
  const dTw = (Ploss - MOTOR.Gwc*(st.Tw - st.Tc))/MOTOR.Cw, dTc = (MOTOR.Gwc*(st.Tw - st.Tc) - MOTOR.Gca*(st.Tc - TaC))/MOTOR.Cc;
  st.Tw += dt*dTw; st.Tc += dt*dTc;
}
function motorTimeToLimit(st, Ploss, TaC){
  const steady = TaC + Ploss*(1/MOTOR.Gca + 1/MOTOR.Gwc);
  if (steady < MOTOR.Tlim) return {steady, t: Infinity};
  const s = {Tw: st.Tw, Tc: st.Tc};
  for (let t = 0; t < 7200; t += 1){ if (s.Tw >= MOTOR.Tlim) return {steady, t}; motorThermalStep(s, Ploss, TaC, 1); }
  return {steady, t: Infinity};
}

/* ------------------------------------------------------------------ PLA casing thermal ROM (operator inference) */
const TH = ROM.thermal, RT = TH.V.length;
function thermalStep(a, u1, u2){
  const o = new Array(RT).fill(0);
  for (let i = 0; i < RT; i++){ let s = 0; for (let j = 0; j < RT; j++) s += (TH.Ar[i][j] + u1*TH.Nr[i][j])*a[j]; o[i] = s + u2*TH.br[i]; }
  return o;
}
function casingField(a){ return TH.x.map((_, i) => { let s = 0; for (let j = 0; j < RT; j++) s += TH.V[j][i]*a[j]; return s; }); }
function thermalInputs(est){
  const u1 = Math.pow(Math.max(est.m, 0)/TH.m_design, 0.8);
  return [u1, u1*Math.max(est.Tout - est.TaK, 0)];
}
function casingTimeToLimit(a, u1, u2, TaC){
  // steady state: a* = (I - Ar - u1 Nr)^-1 br u2 (2x2 or rxr solved by Gauss elimination)
  const M = [], b = [];
  for (let i = 0; i < RT; i++){ M.push([]); for (let j = 0; j < RT; j++) M[i].push((i === j ? 1 : 0) - TH.Ar[i][j] - u1*TH.Nr[i][j]); b.push(TH.br[i]*u2); }
  const as = solve(M, b), steady = TaC + Math.max(...casingField(as));
  if (steady < PLA_LIMIT) return {steady, t: Infinity};
  let s = a.slice();
  for (let t = 0; t < 7200; t++){ if (TaC + Math.max(...casingField(s)) >= PLA_LIMIT) return {steady, t}; s = thermalStep(s, u1, u2); }
  return {steady, t: Infinity};
}
function solve(A, b){
  const n = b.length, M = A.map((r, i) => r.concat([b[i]]));
  for (let c = 0; c < n; c++){
    let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    for (let r = 0; r < n; r++){ if (r === c) continue; const f = M[r][c]/M[c][c]; for (let k = c; k <= n; k++) M[r][k] -= f*M[c][k]; }
  }
  return M.map((r, i) => r[n]/r[i]);
}

/* ------------------------------------------------------------------ faults (virtual rig truth) */
const FAULTS = {
  none:     {label: 'None', h: s => ({p: 1, t: 1, m: 1})},
  erosion:  {label: 'Blade erosion / tip clearance', h: s => ({p: 1 - 0.12*s, t: 1 + 0.06*s, m: 1 - 0.05*s})},
  blockage: {label: 'Inlet blockage', h: s => ({p: 1 - 0.16*s, t: 1 - 0.04*s, m: 1 - 0.22*s})},
  pbias:    {label: 'Outlet pressure-sensor offset', h: s => ({p: 1, t: 1, m: 1}), pbias: s => 600*s},
  rtd:      {label: 'Outlet RTD drift', h: s => ({p: 1, t: 1, m: 1}), tdrift: s => 1.6*s},
  sag:      {label: 'Motor speed sag', h: s => ({p: 1, t: 1, m: 1}), sag: s => 0.14*s},
  bearing:  {label: 'Bearing friction rise', h: s => ({p: 1, t: 1, m: 1}), loss: s => 260*s},
};

/* ------------------------------------------------------------------ simulation state */
const S = {
  t: 0, running: true, speed: 1, source: 'rig', mode: 'manual',
  Nman: 15000, PRset: 1.10, phi: 1.0, TaC: 15, PaK: 101.325, fault: 'none', sev: 0.5, bellmouth: false,
  N: 0, Ncmd: 0, Nexp: 0, I: 0, mot: {Tw: 15, Tc: 15}, motEst: {Tw: 15, Tc: 15}, thA: new Array(RT).fill(0), thAcc: 0,
  sens: {Tout: REF.T, ToutEstLag: REF.T}, surge: 0,
  kf: {x: [1, 1, 1], P: [1e-3, 1e-3, 1e-3]}, base: {p: 1, t: 1, m: 1},
  cus: {}, meas: null, est: null, mest: null, truth: null, replay: null, alarms: [], devRows: [],
};
function resetRig(){
  Object.assign(S, {t: 0, N: 0, Ncmd: 0, Nexp: 0, I: 0, surge: 0, thA: new Array(RT).fill(0), thAcc: 0});
  S.mot = {Tw: S.TaC, Tc: S.TaC}; S.motEst = {Tw: S.TaC, Tc: S.TaC};
  S.sens = {Tout: S.TaC + 273.15, ToutEstLag: S.TaC + 273.15};
  S.kf = {x: [1, 1, 1], P: [1e-3, 1e-3, 1e-3]}; S.cus = {};
  HIST.clear();
}

/* ------------------------------------------------------------------ history (ring buffers, sampled every 0.5 s of sim time) */
const HIST = {
  keys: ['t', 'PRm', 'PRe', 'PRset', 'N', 'Ncmd', 'Tm', 'Te', 'Tw', 'Tcas', 'Pe_m', 'Pe_e', 'Psh', 'Ib_m', 'Ib_e', 'hp', 'ht', 'hpS', 'htS', 'm', 'phi'],
  max: 1440, d: {}, next: 0,
  clear(){ this.keys.forEach(k => this.d[k] = []); this.next = 0; },
  push(o){ this.keys.forEach(k => { const a = this.d[k]; a.push(o[k]); if (a.length > this.max) a.shift(); }); },
};
HIST.clear();

/* ------------------------------------------------------------------ Kalman filter on health factors (random-walk states) */
function kfUpdate(i, y, H, R, q){
  const kf = S.kf; kf.P[i] += q;
  const Sv = H*H*kf.P[i] + R, K = kf.P[i]*H/Sv, nu = y - H*kf.x[i];
  kf.x[i] += K*nu; kf.P[i] = (1 - K*H)*kf.P[i];
  return nu/Math.sqrt(Sv);
}
function cusum(key, z, kappa = 0.5){
  const c = S.cus[key] || (S.cus[key] = {hi: 0, lo: 0});
  if (!isFinite(z)) return c;
  c.hi = Math.max(0, c.hi + z - kappa); c.lo = Math.max(0, c.lo - z - kappa);
  return c;
}
const CUSUM_H = 8;

/* ------------------------------------------------------------------ one simulation step (DT = 0.1 s) */
function measureRig(dt){
  const f = FAULTS[S.fault] || FAULTS.none, s = S.sev, TaK = S.TaC + 273.15, Pa = S.PaK*1e3;
  const sag = f.sag ? f.sag(s) : 0;
  // speed loop of the VESC as a first-order lag, limited by electrical power
  let target = clamp(S.Ncmd, 0, 26000)*(1 - sag);
  const prev = S.truth;
  if (prev && prev.mot.Pe > MOTOR.Pmax && target > S.N) target = S.N;
  S.N += (target - S.N)*Math.min(dt/TAU_N, 1);
  const r = romPredict(S.N, S.phi, TaK, Pa), h = f.h(s);
  const hp = h.p*S.base.p, ht = h.t*S.base.t, hm = h.m*S.base.m;
  let PR = 1 + hp*(r.PR - 1); const Tout = TaK + ht*(r.Tout - TaK); let m = hm*r.m;
  const SM = r.SM - 0.6*(1 - h.m) - 0.4*(1 - h.p);
  // surge: limit-cycle oscillation of pressure and flow when the operating point crosses the surge line
  if (SM < 0 && S.N > 3000){ S.surge += dt; const amp = clamp(-SM*25, 0.25, 1); PR = 1 + (PR - 1)*(1 + 0.18*amp*Math.sin(2*Math.PI*3.2*S.t)); m *= 1 + 0.6*amp*Math.sin(2*Math.PI*3.2*S.t + 1.2); }
  else S.surge = 0;
  const Pair = m*CP*(Tout - TaK), Pshaft = Pair/ETA_MECH;
  const mot = motorModel(S.N, Pshaft, f.loss ? f.loss(s) : 0);
  motorThermalStep(S.mot, mot.Ploss, S.TaC, dt);
  S.sens.Tout += (Tout + (f.tdrift ? f.tdrift(s) : 0) - S.sens.Tout)*Math.min(dt/T_LAG, 1);
  S.truth = {N: S.N, PR, Tout, m, SM, Pshaft, mot, r};
  return {
    t: S.t, N: S.N + 8*gauss(), Ncmd: S.Ncmd, TaC: S.TaC + 0.03*gauss(), Pa: Pa + 2*gauss(),
    Pout: PR*Pa + (f.pbias ? f.pbias(s) : 0) + 10*gauss(), Tout: S.sens.Tout + 0.03*gauss(),
    Ib: mot.Ib + 0.4*gauss(), Vb: mot.Vb + 0.05*gauss(), m: S.bellmouth ? m + 0.0015*gauss() : null, phi: S.phi, kind: 'sim',
  };
}
function measureReplay(){
  const R = S.replay; if (!R || !R.rows.length) return null;
  const rows = R.rows, t0 = rows[0].t, span = rows[rows.length - 1].t - t0 || 1;
  const tt = t0 + ((S.t - R.start) % span);
  let k = R.k || 0; if (rows[k].t > tt) k = 0;
  while (k < rows.length - 2 && rows[k + 1].t <= tt) k++;
  R.k = k; const a = rows[k], b = rows[Math.min(k + 1, rows.length - 1)], w = b.t > a.t ? clamp((tt - a.t)/(b.t - a.t), 0, 1) : 0;
  const L = key => (a[key] == null || b[key] == null) ? (a[key] ?? null) : lerp(a[key], b[key], w);
  const Pa = (L('Pa') ?? S.PaK*1e3);
  const phi = L('phi') ?? S.phi;
  S.N = L('N') ?? 0; S.Ncmd = S.N;
  return {t: tt, N: S.N, Ncmd: S.N, TaC: L('TaC') ?? S.TaC, Pa, Pout: L('Pout'), Tout: L('Tout') != null ? L('Tout') + 273.15 : null,
          Ib: L('Ib'), Vb: L('Vb'), m: L('m'), phi, kind: R.kind === 'measured' ? 'meas' : 'sim'};
}

function step(){
  const dt = DT;
  // controller (rig only): motor speed command
  if (S.source === 'rig'){
    if (S.mode === 'auto'){
      const m = S.meas, TaK = S.TaC + 273.15, Pa = S.PaK*1e3;
      const ff = romSpeedForPR(S.PRset, S.phi, TaK, Pa, clamp(S.kf.x[0], 0.7, 1.2));
      const PRm = m && m.Pout ? m.Pout/m.Pa : 1, e = S.PRset - PRm;
      let u = ff + 2.0e4*e + 6.0e4*(S.I + e*dt);
      const uL = clamp(u, 0, 24000), du = clamp(uL - S.Ncmd, -3000*dt, 3000*dt);
      if (uL === u && Math.abs(du) < 3000*dt*0.999 && S.N > 2000) S.I += e*dt;
      S.Ncmd += du;
    } else {
      S.Ncmd += clamp(S.Nman - S.Ncmd, -3000*dt, 3000*dt); S.I = 0;
    }
  }
  const meas = S.source === 'rig' ? measureRig(dt) : measureReplay();
  S.Nexp += (clamp(S.Ncmd, 0, 26000) - S.Nexp)*Math.min(dt/TAU_N, 1);   // expected response of the VESC speed loop
  S.t += dt;
  if (!meas){ return; }
  S.meas = meas;
  // ---- twin estimate at the MEASURED speed and inlet state (healthy baseline)
  const TaK = meas.TaC + 273.15, est = romPredict(Math.max(meas.N, 0), meas.phi, TaK, meas.Pa);
  const b = S.base, PRb = 1 + b.p*(est.PR - 1), Toutb = TaK + b.t*(est.Tout - TaK), mb = b.m*est.m;
  const Pshb = mb*CP*(Toutb - TaK)/ETA_MECH, mest = motorModel(meas.N, Pshb);
  S.est = Object.assign({}, est, {PRb, Toutb, mb, Pshb});
  S.mest = mest;
  S.sens.ToutEstLag += (Toutb - S.sens.ToutEstLag)*Math.min(dt/T_LAG, 1);
  motorThermalStep(S.motEst, mest.Ploss, meas.TaC, dt);
  // casing thermal ROM, advanced in its own 1 s steps
  S.thAcc += dt;
  while (S.thAcc >= TH.dt){ const [u1, u2] = thermalInputs(S.est); S.thA = thermalStep(S.thA, u1, u2); S.thAcc -= TH.dt; }
  // ---- Kalman filter (synchronisation) and residual checks
  const run = meas.N > 4000 && S.surge === 0;
  const dev = [];
  const z = {};
  if (meas.Pout != null){
    const PRm = meas.Pout/meas.Pa, Hp = est.PR - 1;
    if (run && Hp > 0.004){ const Rp = Math.pow(SIG.PR*0.25, 2); z.kfp = kfUpdate(0, PRm - 1, Hp, Rp, Math.pow(4e-4, 2)); }
    z.PR = (PRm - PRb)/SIG.PR; dev.push(['Pressure ratio', PRb, PRm, 4, 'PR', z.PR]);
    z.Pout = (meas.Pout - PRb*meas.Pa)/1e3/SIG.Pout; dev.push(['Outlet P₀ (kPa)', PRb*meas.Pa/1e3, meas.Pout/1e3, 2, 'Pout', z.Pout]);
  }
  if (meas.Tout != null){
    const Ht = S.sens.ToutEstLag - TaK;
    if (run && Ht > 0.6){ const Rt = Math.pow(0.08, 2); z.kft = kfUpdate(1, meas.Tout - TaK, (Ht)/b.t, Rt, Math.pow(4e-4, 2)); }
    z.Tout = (meas.Tout - S.sens.ToutEstLag)/SIG.Tout; dev.push(['Outlet T₀ (°C)', S.sens.ToutEstLag - 273.15, meas.Tout - 273.15, 2, 'Tout', z.Tout]);
  }
  if (meas.m != null){
    if (run) kfUpdate(2, meas.m, est.m, Math.pow(0.0015, 2), Math.pow(4e-4, 2));
    z.m = (meas.m - mb)/SIG.m; dev.push(['ṁ (kg/s)', mb, meas.m, 4, 'm', z.m]);
  }
  if (meas.Ib != null){ z.I = (meas.Ib - mest.Ib)/SIG.I; dev.push(['Battery I (A)', mest.Ib, meas.Ib, 1, 'I', z.I]);
    if (meas.Vb != null){ const Pe = meas.Ib*meas.Vb; z.Pe = (Pe - mest.Pe)/SIG.Pe; dev.push(['Elec. power (W)', mest.Pe, Pe, 0, 'Pe', z.Pe]); } }
  if (S.source === 'rig'){ z.N = (meas.N - S.Nexp)/Math.max(SIG.N, 0.01*S.Nexp); dev.push(['Speed (rpm)', S.Nexp, meas.N, 0, 'N', z.N]); }
  dev.forEach(d => { if (run || d[4] === 'N') cusum(d[4], d[4] === 'N' ? Math.min(d[5], 0) : d[5]); });
  S.devRows = dev;
  S.alarms = evaluateAlarms(meas, est, z);
  // ---- history every 0.5 s
  if (S.t >= HIST.next){
    HIST.next = S.t + 0.5;
    const cas = S.TaC + Math.max(...casingField(S.thA));
    HIST.push({t: S.t, PRm: meas.Pout != null ? meas.Pout/meas.Pa : null, PRe: PRb, PRset: S.mode === 'auto' && S.source === 'rig' ? S.PRset : null,
      N: meas.N, Ncmd: S.Ncmd, Tm: meas.Tout != null ? meas.Tout - 273.15 : null, Te: S.sens.ToutEstLag - 273.15, Tw: S.motEst.Tw, Tcas: cas,
      Pe_m: meas.Ib != null && meas.Vb != null ? meas.Ib*meas.Vb : null, Pe_e: mest.Pe, Psh: Pshb, Ib_m: meas.Ib, Ib_e: mest.Ib,
      hp: S.kf.x[0], ht: S.kf.x[1], hpS: 2*Math.sqrt(S.kf.P[0]), htS: 2*Math.sqrt(S.kf.P[1]), m: mb, phi: meas.phi});
  }
}

/* ------------------------------------------------------------------ alarms and diagnosis hints */
function status(key){
  const c = S.cus[key]; const row = S.devRows.find(d => d[4] === key); const z = row ? Math.abs(row[5]) : 0;
  if ((c && Math.max(c.hi, c.lo) > CUSUM_H) || z > 4) return 'alarm';
  if (z > 2 || (c && Math.max(c.hi, c.lo) > CUSUM_H/2)) return 'warn';
  return 'ok';
}
function evaluateAlarms(meas, est, z){
  const out = [], st = k => status(k);
  if (S.surge > 0) out.push(['alarm', 'Surge: the operating point is beyond the surge line. Open the outlet valve or lower the speed.']);
  else if (est.SM < 0.03 && meas.N > 4000) out.push(['warn', `Surge margin ${(est.SM*100).toFixed(1)} %: close to surge. Open the valve before raising the speed.`]);
  if (est.extrap && meas.N > 1000) out.push(['warn', 'Outside the ROM training domain (10,000–20,000 rpm corrected, valve 94–150 %). Treat estimates as extrapolation.']);
  if (S.surge > 0) return out;                      // residual diagnosis is meaningless while the flow is surging
  const sP = st('PR'), sT = st('Tout'), sI = st('I'), sN = st('N'), sM = S.bellmouth ? st('m') : 'ok';
  const zp = z.PR || 0, zt = z.Tout || 0, zi = z.I || 0;
  if (sN !== 'ok' && (z.N || 0) < -2) out.push([sN, 'Speed below command: motor speed sag (supply voltage or ESC current limit).']);
  if (sP !== 'ok' && zp < 0 && sT !== 'ok' && zt > 0) out.push(['alarm', 'Pressure rise low and temperature rise high: efficiency loss (blade erosion, tip-clearance growth or surface damage).']);
  else if (sP !== 'ok' && zp < 0 && (zi < -1 || (S.bellmouth && (z.m || 0) < -2))) out.push(['alarm', 'Pressure rise and flow low: flow restriction such as inlet blockage.']);
  else if (sP !== 'ok' && sT === 'ok' && sI === 'ok') out.push([sP, 'Pressure channel deviates alone: suspect the outlet pressure sensor (offset). Repeat the zero-speed cross-calibration.']);
  else if (sP !== 'ok') out.push([sP, 'Pressure ratio deviates from the expected value.']);
  if (sT !== 'ok' && sP === 'ok') out.push([sT, 'Outlet temperature deviates alone: suspect RTD drift or probe recovery error.']);
  if (sI !== 'ok' && sP === 'ok' && sT === 'ok' && zi > 0) out.push([sI, 'Electrical power above expectation with normal aerodynamics: mechanical loss (bearings, coupling) or motor/ESC loss.']);
  if (sM !== 'ok' && sP === 'ok') out.push([sM, 'Measured mass flow deviates from the expected value.']);
  const cas = S.TaC + Math.max(...casingField(S.thA));
  if (cas > PLA_LIMIT - 5) out.push([cas > PLA_LIMIT ? 'alarm' : 'warn', `PLA casing at ${cas.toFixed(1)} °C (limit ${PLA_LIMIT} °C).`]);
  if (S.motEst.Tw > MOTOR.Tlim - 15) out.push([S.motEst.Tw > MOTOR.Tlim ? 'alarm' : 'warn', `Motor winding at ${S.motEst.Tw.toFixed(0)} °C (assumed limit ${MOTOR.Tlim} °C).`]);
  if (S.mest && S.mest.Pe > MOTOR.Pmax*0.95) out.push(['warn', 'Electrical power at the 4.2 kW limit.']);
  return out;
}
