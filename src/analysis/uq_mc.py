import os as _os, sys as _sys
REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..'))
FIGP = _os.path.join(REPO, 'figures', 'paper') + '/'; RES = _os.path.join(REPO, 'data', 'processed', 'analysis'); _os.makedirs(RES, exist_ok=True)
DASH = 'file://' + _os.path.join(REPO, 'docs', 'index.html')
_sys.path.insert(0, _os.path.join(REPO, 'src', 'modelling'))
"""Uncertainty and sensitivity of the full-order model to its uncertain inputs (Monte Carlo, Latin hypercube).
Inputs: design stage efficiency eta_s ~ U(0.65, 0.75); rotor exit-angle (deviation/print) error dbeta2 ~ U(-1, +1) deg;
stall-side loss-bucket half width I_POS ~ U(5, 9) deg. The outlet-valve area is held at its physical (nominal) value."""
import sys, os, json, numpy as np
pass
from multiprocessing import Pool
from scipy.stats import qmc
import offdesign as od
NS = [10000, 15000, 20000]
def run(args):
    eta, db2, ipos = args
    od.ETA_STAGE_D = eta; od.I_POS = ipos
    C = od.Compressor('B')
    C.A_thr = A_NOM
    for s in C.stg: s['b2'] = s['b2'] + np.radians(db2)
    out = []
    for N in NS:
        op = C.operating_point(N)
        out.append(None if op is None else [op['PR'], op['T0'] - 273.15, op['m'], op['eta'], op['surge_margin'], op['power']])
    return out
od0 = od.Compressor('B'); A_NOM = od0.A_thr
if __name__ == '__main__':
    X = qmc.scale(qmc.LatinHypercube(d=3, seed=7).random(64), [0.65, -1.0, 5.0], [0.75, 1.0, 9.0])
    with Pool(2) as p: R = p.map(run, [tuple(x) for x in X])
    ok = [i for i, r in enumerate(R) if all(v is not None for v in r)]
    X = X[ok]; R = np.array([R[i] for i in ok])           # (n, 3 speeds, 6 outputs)
    res = dict(n=len(ok), speeds=NS, inputs=X.tolist(), outputs=R.tolist())
    names = ['PR', 'T_out_C', 'mdot', 'eta', 'SM', 'P_air']
    summ = {}
    for k, N in enumerate(NS):
        for j, nm in enumerate(names):
            v = R[:, k, j]; summ[f'{nm}@{N}'] = dict(mean=float(v.mean()), std=float(v.std(ddof=1)), p2_5=float(np.percentile(v, 2.5)), p97_5=float(np.percentile(v, 97.5)))
    # standardized regression coefficients at the design speed
    Z = (X - X.mean(0))/X.std(0)
    src = {}
    for j, nm in enumerate(names):
        y = R[:, 2, j]; yz = (y - y.mean())/y.std()
        c, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(yz)), Z]), yz, rcond=None)
        r2 = 1 - np.sum((yz - np.column_stack([np.ones(len(yz)), Z])@c)**2)/np.sum(yz**2)
        src[nm] = dict(eta_s=float(c[1]), dbeta2=float(c[2]), I_pos=float(c[3]), R2=float(r2))
    res['summary'] = summ; res['src'] = src
    json.dump(res, open(_os.path.join(RES, 'uq_mc.json'), 'w'), indent=1)
    print('n', len(ok)); print(json.dumps({k: v for k, v in summ.items() if k.startswith(('PR', 'T_out', 'mdot'))}, indent=0)[:1500]); print(json.dumps(src, indent=0))
