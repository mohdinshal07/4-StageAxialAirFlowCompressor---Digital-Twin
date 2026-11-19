import os as _os, sys as _sys
REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..'))
FIGP = _os.path.join(REPO, 'figures', 'paper') + '/'; RES = _os.path.join(REPO, 'data', 'processed', 'analysis'); _os.makedirs(RES, exist_ok=True)
DASH = 'file://' + _os.path.join(REPO, 'docs', 'index.html')
_sys.path.insert(0, _os.path.join(REPO, 'src', 'modelling'))
import asyncio, json
from playwright.async_api import async_playwright
JS = r"""
() => {
  S.running = false;
  const rec = [];
  const snap = () => { const m = S.meas, c = k => S.cus[k] ? Math.max(S.cus[k].hi, S.cus[k].lo) : 0;
    rec.push({t: +S.t.toFixed(2), PRm: m.Pout/m.Pa, PRe: S.est.PRb, Tm: m.Tout - 273.15, Te: S.sens.ToutEstLag - 273.15, N: m.N, Ncmd: S.Ncmd,
      hp: S.kf.x[0], ht: S.kf.x[1], hpS: 2*Math.sqrt(S.kf.P[0]), htS: 2*Math.sqrt(S.kf.P[1]), cPR: c('PR'), cT: c('Tout'), cI: c('I'),
      Ib: m.Ib, Ie: S.mest.Ib, PRset: S.mode === 'auto' ? S.PRset : null, alarm: S.alarms.filter(a => a[0] === 'alarm').map(a => a[1])}); };
  const out = {};
  // ---------------- scenario 1: fault detection (blade erosion 60 % at 60 s), lab inlet 25 C
  Object.assign(S, {source: 'rig', mode: 'manual', Nman: 20000, TaC: 25, PaK: 100.9, phi: 1.0, fault: 'none', sev: 0, bellmouth: false, base: {p: 1, t: 1, m: 1}});
  resetRig(); let first = null;
  for (let k = 0; k < 1500; k++){
    const t = k*DT;
    if (k === 400){ S.base = {p: S.kf.x[0], t: S.kf.x[1], m: 1}; Object.keys(S.cus).forEach(q => S.cus[q] = {hi: 0, lo: 0}); }
    if (k === 600){ S.fault = 'erosion'; S.sev = 0.6; }
    step(); if (k % 5 === 0) snap();
    if (k > 600 && first === null && S.cus.PR && Math.max(S.cus.PR.hi, S.cus.PR.lo) > CUSUM_H) first = S.t;
  }
  out.s1 = {rec: rec.splice(0), detect_t: first, alarms_end: S.alarms.map(a => a[1]), base: S.base, hp: S.kf.x[0], ht: S.kf.x[1], P: S.kf.P};
  // ---------------- scenario 2: hold PR 1.12, 10 % speed sag at 60 s, set point 1.08 at 110 s
  Object.assign(S, {source: 'rig', mode: 'auto', PRset: 1.12, TaC: 15, PaK: 101.325, phi: 1.0, fault: 'none', sev: 0, base: {p: 1, t: 1, m: 1}});
  resetRig();
  for (let k = 0; k < 1600; k++){
    if (k === 600){ S.fault = 'sag'; S.sev = 0.714; }
    if (k === 1100){ S.PRset = 1.08; }
    step(); if (k % 5 === 0) snap();
  }
  out.s2 = {rec: rec.splice(0)};
  // ---------------- scenario 3: what-if inlet temperature 35 C at design speed: thermal margins
  Object.assign(S, {source: 'rig', mode: 'manual', Nman: 20000, TaC: 35, PaK: 100.9, phi: 1.0, fault: 'none', sev: 0, speed: 1});
  resetRig();
  for (let k = 0; k < 18000; k++){ step(); if (k % 50 === 0) snap(); }
  const [u1, u2] = thermalInputs(S.est);
  out.s3 = {rec: rec.splice(0), cas: casingTimeToLimit(S.thA, u1, u2, S.TaC), mot: motorTimeToLimit(S.motEst, S.mest.Ploss, S.TaC), casMax: S.TaC + Math.max(...casingField(S.thA)), Tw: S.motEst.Tw, Tout: S.meas.Tout - 273.15, PR: S.meas.Pout/S.meas.Pa};
  // ---------------- timing
  let t0 = performance.now(); for (let i = 0; i < 100000; i++) romPredict(10000 + (i % 1000)*10, 1.0 + (i % 7)*0.05, 288.15, 101325); const tRom = (performance.now() - t0)/100000;
  t0 = performance.now(); for (let i = 0; i < 2000; i++) romSpeedForPR(1.05 + (i % 7)*0.01, 1.0, 288.15, 101325); const tInv = (performance.now() - t0)/2000;
  Object.assign(S, {mode: 'auto', PRset: 1.12}); resetRig();
  t0 = performance.now(); for (let i = 0; i < 20000; i++) step(); const tStep = (performance.now() - t0)/20000;
  rec.splice(0);
  out.timing = {rom_ms: tRom, inverse_ms: tInv, step_ms: tStep};
  return out;
}
"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page()
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(DASH + '#rom'); await pg.wait_for_timeout(1500)
        res = await pg.evaluate(JS)
        json.dump(res, open(_os.path.join(RES, 'twin_scenarios.json'), 'w'))
        print('errors', errs)
        print('s1 detect', res['s1']['detect_t'], 'hp', res['s1']['hp'], 'ht', res['s1']['ht'], 'base', res['s1']['base'], res['s1']['alarms_end'])
        r = res['s2']['rec']; 
        for t in (55, 59.5, 70, 100, 108, 150):
            q = min(r, key=lambda z: abs(z['t'] - t)); print('s2', q['t'], 'PR %.4f N %.0f cmd %.0f' % (q['PRm'], q['N'], q['Ncmd']))
        s3 = res['s3']; print('s3', {k: s3[k] for k in ('cas', 'mot', 'casMax', 'Tw', 'Tout', 'PR')})
        print('timing', res['timing'])
        await b.close()
asyncio.run(main())
