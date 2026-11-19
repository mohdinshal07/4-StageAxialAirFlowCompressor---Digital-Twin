"""
Lecture-aligned reduced-order model (ROM) of the 4-stage axial compressor (AE 541).

Workflow (each step mapped to the course module that teaches it)
  1. Full-order model (FOM): mean-line stage-stacking off-design model, conservation of mass,
     energy and the Euler work equation (Module 02d, physics-based modelling).
  2. Design of experiments: 60-point Latin hypercube over (corrected speed, outlet-valve opening);
     45 training / 15 test points, plus 5 out-of-range stress points (Module 02a, surrogate modelling).
  3. Multi-variable snapshot vector at the 9 axial stations (P0, T0, static p, axial Mach) plus
     rotor incidence and diffusion factor per stage, centred and scaled per variable before POD
     (Modules 02b/02c; airfoil-wake notebook scaling).  Physics-informed speed scaling
     (pressure/temperature rise ~ U^2, axial Mach ~ U) keeps the correct zero-speed limit.
  4. POD by SVD; model order r chosen by captured energy AND held-out error (cooling-strip notebook).
  5. Parametric ROM: polynomial maps (x, phi) -> POD amplitudes, degree by leave-one-out CV;
     Gaussian-process comparison (Module 02a; Module 02b "combining surrogate modelling with ROM").
  6. Dynamic thermal ROM of the PLA casing: 40-node conduction/convection FOM, POD basis,
     operator inference a_{k+1} = A_r a_k + u1 N_r a_k + u2 b_r, cross-checked against Galerkin
     projection of the FOM operators (cooling-strip and airfoil-wake notebooks, Module 02b).
  7. Sensing: estimate POD amplitudes from a few sensors (gappy POD / least squares) and the
     observability of the amplitudes from outlet-only sensors (Module 03a).
Outputs: rom_pod.json (everything the web twin needs), metrics, figures, data CSVs.
"""
import numpy as np, pandas as pd, json, os, sys, time, itertools, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = HERE
sys.path.insert(0, ROOT)
import offdesign as od
from blades import build, CFG
from scipy.stats import qmc

OUT = os.path.join(HERE, '..', '..', 'models', 'pod_rom'); os.makedirs(OUT, exist_ok=True)
T_REF, P_REF, g, R, cp = od.T_REF, od.P_REF, od.g, od.R, od.cp
A01 = np.sqrt(g*R*T_REF); N_D = 20000.0
N_LO, N_HI, PHI_LO, PHI_HI = 10000.0, 20000.0, 0.94, 1.50
NS = 9                                     # axial stations: inlet, then rotor exit / stator exit of 4 stages
GROUPS = [('Pi', 'total-pressure rise  (P0/P01-1)/x^2', NS), ('Th', 'total-temperature rise (T0/T01-1)/x^2', NS),
          ('Ps', 'static pressure (p/P01-1)/x^2', NS), ('Ma', 'axial Mach number (Ca/a01)/x', NS),
          ('ir', 'rotor incidence (deg)', 4), ('DF', 'rotor diffusion factor', 4)]
C = od.Compressor('B')

# ----------------------------------------------------------------------------- FOM snapshots
def snapshot(N, phi):
    op = C.operating_point(N, T_REF, P_REF, phi)
    if op is None: return None
    st = op['stages']; x = N/N_D
    P0 = [P_REF]; T0 = [T_REF]; p = [st[0]['p1']]; Ca = [st[0]['Ca1']]
    for s in st:
        P0 += [s['P02'], s['P03']]; T0 += [s['T02'], s['T03']]; p += [s['p2'], s['p3']]; Ca += [s['Ca2'], s['Ca3']]
    P0, T0, p, Ca = map(np.array, (P0, T0, p, Ca))
    field = np.concatenate([(P0/P_REF - 1)/x**2, (T0/T_REF - 1)/x**2, (p/P_REF - 1)/x**2, Ca/A01/x,
                            [s['i_r'] for s in st], [s['DFr'] for s in st]])
    sc = dict(N=N, phi=phi, x=x, PR=op['PR'], TR=op['TR'], T_out=op['T0'], P_out=op['P0'], m=op['m'], eta=op['eta'],
              power=op['power'], SM=op['surge_margin'], stable=op['stable'], DFmax=op['DFmax'], mx=op['m']/x)
    return field, sc

def run_set(points, tag):
    F, S = [], []
    for N, phi in points:
        r = snapshot(N, phi)
        if r is None: print('  no operating point', tag, N, phi); continue
        F.append(r[0]); S.append(r[1])
    return np.array(F).T, pd.DataFrame(S)

t0 = time.time()
lhs = qmc.LatinHypercube(d=2, optimization='random-cd', seed=2026).random(60)
pts = qmc.scale(lhs, [N_LO, PHI_LO], [N_HI, PHI_HI])
pts[:, 0] = np.round(pts[:, 0]); pts[:, 1] = np.round(pts[:, 1], 4)
perm = np.random.default_rng(2026).permutation(60)
train_pts, test_pts = pts[perm[:45]], pts[perm[45:]]
stress_pts = np.array([[6000, 1.2], [8000, 1.0], [22000, 1.2], [24000, 1.0], [15000, 1.6]])
Xtr, Str = run_set(train_pts, 'train'); Xte, Ste = run_set(test_pts, 'test'); Xst, Sst = run_set(stress_pts, 'stress')
print('FOM snapshots: train %d test %d stress %d  (%.0f s)' % (Xtr.shape[1], Xte.shape[1], Xst.shape[1], time.time() - t0))
fom_time = (time.time() - t0)/(Xtr.shape[1] + Xte.shape[1] + Xst.shape[1])

# ----------------------------------------------------------------------------- centring and scaling
mean = Xtr.mean(axis=1)
scale = np.zeros_like(mean); k = 0
for name, _, n in GROUPS:
    blk = Xtr[k:k+n] - mean[k:k+n, None]
    scale[k:k+n] = np.sqrt(np.mean(blk**2)); k += n
def to_q(X): return (X - mean[:, None])/scale[:, None]
def from_q(Q): return Q*scale[:, None] + mean[:, None]
Qtr, Qte, Qst = to_q(Xtr), to_q(Xte), to_q(Xst)
U, sig, Wt = np.linalg.svd(Qtr, full_matrices=False)
energy = np.cumsum(sig**2)/np.sum(sig**2)
print('singular values', np.round(sig[:8], 4)); print('energy', np.round(energy[:8], 7))

# ----------------------------------------------------------------------------- amplitude surrogate
def norm_in(x, phi): return (np.asarray(x) - 0.75)/0.25, (np.asarray(phi) - 1.22)/0.28
def exps(d): return [(i, j) for i in range(d + 1) for j in range(d + 1 - i)]
def design(x, phi, d):
    u, v = norm_in(x, phi); return np.column_stack([u**i*v**j for i, j in exps(d)])
def fit(xs, ph, y, d, lam=1e-10):
    A = design(xs, ph, d); return np.linalg.solve(A.T@A + lam*np.eye(A.shape[1]), A.T@y)
def loocv(xs, ph, y, d):
    e = []
    for i in range(len(y)):
        m = np.arange(len(y)) != i; c = fit(xs[m], ph[m], y[m], d)
        e.append(design(xs[i:i+1], ph[i:i+1], d)@c - y[i])
    return float(np.sqrt(np.mean(np.square(e))))
xtr, ptr = Str.x.values, Str.phi.values
def choose_fit(y):
    cv = {d: loocv(xtr, ptr, y, d) for d in range(1, 7)}
    d = min(cv, key=cv.get); return d, fit(xtr, ptr, y, d), cv

R_MAX = 8
Atr = U[:, :R_MAX].T@Qtr
amp_models = [choose_fit(Atr[j]) for j in range(R_MAX)]
scal_models = {k: choose_fit(Str[k].values) for k in ('mx', 'SM')}
print('amplitude degrees', [m[0] for m in amp_models], 'scalars', {k: v[0] for k, v in scal_models.items()})

def rom_field(x, phi, r):
    x = np.clip(x, 0.5, 1.0)          # similarity: shape outside the trained speed band taken at the band edge (same as the web twin)
    a = np.array([design(x, phi, amp_models[j][0])@amp_models[j][1] for j in range(r)])
    return from_q(U[:, :r]@a)
def outputs_from_field(F, x):
    x = np.asarray(x)
    PR = 1 + x**2*F[NS - 1]; TR = 1 + x**2*F[2*NS - 1]
    eta = (PR**(1/od.EXP) - 1)/(TR - 1)
    return PR, TR, eta
def rom_eval(S, r):
    F = rom_field(S.x.values, S.phi.values, r); PR, TR, eta = outputs_from_field(F, S.x.values)
    xe = np.clip(S.x.values, 0.5, 1.0)
    mx = design(xe, S.phi.values, scal_models['mx'][0])@scal_models['mx'][1]
    SM = design(xe, S.phi.values, scal_models['SM'][0])@scal_models['SM'][1]
    m = mx*S.x.values
    return dict(F=F, PR=PR, T_out=TR*T_REF, P_out=PR*P_REF, eta=eta, m=m, power=m*cp*(TR - 1)*T_REF, SM=SM)

def metr(true, pred):
    e = pred - true; ss = np.sum((true - true.mean())**2)
    return dict(R2=float(1 - np.sum(e**2)/ss) if ss > 0 else float('nan'), RMSE=float(np.sqrt(np.mean(e**2))),
                MAE=float(np.mean(np.abs(e))), max_abs=float(np.max(np.abs(e))))
def rel(A, B): return float(np.linalg.norm(A - B)/np.linalg.norm(B))

# model-order sweep: projection (basis-only) error vs ROM forecast error on the held-out test points
sweep = []
for r in range(1, R_MAX + 1):
    V = U[:, :r]; proj = V@(V.T@Qte)
    ev = rom_eval(Ste, r)
    sweep.append(dict(r=r, energy=float(energy[r-1]), proj_err=rel(proj, Qte), rom_err=rel(to_q(ev['F']), Qte),
                      PR_max=float(np.max(np.abs(ev['PR'] - Ste.PR))), Tout_max=float(np.max(np.abs(ev['T_out'] - Ste.T_out)))))
sw = pd.DataFrame(sweep); print(sw.to_string(index=False))
r_energy = int(np.searchsorted(energy, 0.9999) + 1)
r_sel = int(sw.loc[sw.rom_err <= 1.05*sw.rom_err.min()].r.min())
r_sel = max(r_sel, r_energy) if sw.loc[sw.r == max(r_sel, r_energy), 'rom_err'].values[0] < 2*sw.rom_err.min() else r_sel
print('r by 99.99%% energy = %d, r selected (energy + held-out error) = %d' % (r_energy, r_sel))
RS = r_sel

ev_te = rom_eval(Ste, RS); ev_tr = rom_eval(Str, RS); ev_st = rom_eval(Sst, RS)
metrics = {}
for tag, S, ev in (('train', Str, ev_tr), ('test', Ste, ev_te), ('stress', Sst, ev_st)):
    metrics[tag] = {'PR': metr(S.PR.values, ev['PR']), 'T_out_K': metr(S.T_out.values, ev['T_out']),
                    'P_out_kPa': metr(S.P_out.values/1e3, ev['P_out']/1e3), 'mdot_kg_s': metr(S.m.values, ev['m']),
                    'eta': metr(S.eta.values, ev['eta']), 'power_air_W': metr(S.power.values, ev['power']),
                    'SM': metr(S.SM.values, ev['SM'])}
    Qx = to_q(S[['x']].values.T*0) if False else None
metrics['test']['field_rel_err'] = rel(to_q(ev_te['F']), Qte)
metrics['test']['field_proj_err'] = rel(U[:, :RS]@(U[:, :RS].T@Qte), Qte)
metrics['stress']['field_rel_err'] = rel(to_q(ev_st['F']), Qst)

# Gaussian-process comparison (amplitudes -> PR, T_out)
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
Xin = np.column_stack(norm_in(xtr, ptr)); Xin_te = np.column_stack(norm_in(Ste.x.values, Ste.phi.values))
a_gp = []
for j in range(RS):
    gp = GaussianProcessRegressor(ConstantKernel(1.0)*RBF([1.0, 1.0]) + WhiteKernel(1e-8, (1e-12, 1e-3)),
                                  normalize_y=True, n_restarts_optimizer=3, random_state=0).fit(Xin, Atr[j])
    a_gp.append(gp.predict(Xin_te))
F_gp = from_q(U[:, :RS]@np.array(a_gp)); PRg, TRg, _ = outputs_from_field(F_gp, Ste.x.values)
metrics['test']['PR_GP'] = metr(Ste.PR.values, PRg); metrics['test']['T_out_K_GP'] = metr(Ste.T_out.values, TRg*T_REF)

# online cost
t = time.perf_counter()
for _ in range(2000): rom_field(np.array([0.8]), np.array([1.1]), RS)
rom_time = (time.perf_counter() - t)/2000
print('FOM %.3f s/point, ROM %.1f us/point (python)' % (fom_time, rom_time*1e6))
print(json.dumps(metrics['test'], indent=1)[:1500])

# ----------------------------------------------------------------------------- sensing: amplitudes from outlet sensors only
# measured: outlet total pressure (station 8) and outlet total temperature (station 17) -> 2 equations
rows_meas = [NS - 1, 2*NS - 1]
Phi_s = U[rows_meas, :RS]
obs = dict(rank=int(np.linalg.matrix_rank(Phi_s)), r=RS, sing=list(map(float, np.linalg.svd(Phi_s, compute_uv=False))))
rows_more = [NS - 1, 2*NS - 1, 4, 13, 18, 27]   # + mid-machine P0, T0 (station 4 = stage-2 exit) + inlet static p + inlet Mach
Phi_m = U[rows_more, :RS]
obs['rank_with_midtaps_and_bellmouth'] = int(np.linalg.matrix_rank(Phi_m))
obs['cond_with_midtaps_and_bellmouth'] = float(np.linalg.cond(Phi_m))
print('observability of', RS, 'POD amplitudes: outlet-only rank', obs['rank'], '| with mid taps + bellmouth rank', obs['rank_with_midtaps_and_bellmouth'])

# ----------------------------------------------------------------------------- thermal ROM of the PLA casing (operator inference)
d = C.design; st = d['stages']
NX = 40; L = 4*0.032; xs_c = np.linspace(0, L, NX); dx = xs_c[1] - xs_c[0]
# normalised gas total-temperature rise along the axis (design): rise across each rotor (axial 2-13 mm of each 32 mm module)
T0_st = [T_REF] + [s['T03'] for s in st]
f_prof = np.zeros(NX)
for i, xv in enumerate(xs_c):
    kmod = min(int(xv/0.032), 3); xm = xv - 0.032*kmod
    frac = np.clip((xm - 0.002)/0.011, 0, 1)
    f_prof[i] = (T0_st[kmod] + frac*(T0_st[kmod+1] - T0_st[kmod]) - T_REF)/(T0_st[-1] - T_REF)
PLA = dict(k=0.13, rho=1240.0, c=1800.0, t=0.006, Di=0.101, Do=0.113, h_g=120.0, h_o=7.0)
Pm = np.pi*(PLA['Di'] + PLA['Do'])/2
Cp_ = PLA['rho']*PLA['c']*PLA['t']*Pm; kA = PLA['k']*PLA['t']*Pm
Hg = PLA['h_g']*np.pi*PLA['Di']; Ho = PLA['h_o']*np.pi*PLA['Do']
Lap = (np.diag(-2*np.ones(NX)) + np.diag(np.ones(NX-1), 1) + np.diag(np.ones(NX-1), -1)); Lap[0, 1] = 2; Lap[-1, -2] = 2
A0 = (kA/dx**2*Lap - Ho*np.eye(NX))/Cp_          # conduction + outer natural convection
A1 = -Hg/Cp_*np.eye(NX)                           # inner forced convection (scaled by u1 = (m/m_d)^0.8)
b1 = Hg/Cp_*f_prof                                 # gas heating (scaled by u2 = u1 * dT_gas)
DT = 1.0
def fom_thermal(u1, u2, th0=None):
    th = np.zeros(NX) if th0 is None else th0.copy(); out = [th.copy()]
    for k in range(len(u1)):
        th = th + DT*(A0@th + u1[k]*(A1@th) + u2[k]*b1); out.append(th.copy())
    return np.array(out).T
def random_inputs(seed, T=1800):
    rng = np.random.default_rng(seed); u1, dTg = [], []
    while len(u1) < T:
        hold = int(rng.integers(120, 400)); s = rng.uniform(0.45, 1.15); dT = rng.uniform(2.0, 30.0)
        u1 += [s]*hold; dTg += [dT]*hold
    u1 = np.array(u1[:T]); dTg = np.array(dTg[:T]); return u1, u1*dTg, dTg
Xs, Ys, U1, U2 = [], [], [], []
for sd in (11, 12, 13, 14):
    u1, u2, _ = random_inputs(sd); Th = fom_thermal(u1, u2)
    Xs.append(Th[:, :-1]); Ys.append(Th[:, 1:]); U1.append(u1); U2.append(u2)
Xth, Yth, U1, U2 = np.hstack(Xs), np.hstack(Ys), np.concatenate(U1), np.concatenate(U2)
Ut, st_, _ = np.linalg.svd(Xth, full_matrices=False); en_t = np.cumsum(st_**2)/np.sum(st_**2)
rt = int(np.searchsorted(en_t, 0.99999) + 1); Vt = Ut[:, :rt]
AX, AY = Vt.T@Xth, Vt.T@Yth
D = np.vstack([AX, U1[None, :]*AX, U2[None, :]])            # data matrix for [A_r | N_r | b_r]
Ops = AY@np.linalg.pinv(D)
Ar_d, Nr_d, br_d = Ops[:, :rt], Ops[:, rt:2*rt], Ops[:, 2*rt]
Ar_p = Vt.T@(np.eye(NX) + DT*A0)@Vt; Nr_p = DT*Vt.T@A1@Vt; br_p = DT*Vt.T@b1   # Galerkin projection of the FOM
opdiff = float(np.linalg.norm(np.hstack([Ar_d - Ar_p, Nr_d - Nr_p, (br_d - br_p)[:, None]])))
def rom_thermal(u1, u2, Ar, Nr, br):
    a = np.zeros(rt); out = [a.copy()]
    for k in range(len(u1)):
        a = Ar@a + u1[k]*(Nr@a) + u2[k]*br; out.append(a.copy())
    return Vt@np.array(out).T
# held-out test: start-up to design, hold, throttle change, speed reduction (inputs not in the training set)
T_test = 2400
u1t = np.concatenate([np.full(600, 1.0), np.full(600, 0.93), np.full(600, 0.62), np.full(600, 1.08)])
dTt = np.concatenate([np.full(600, 13.6), np.full(600, 15.0), np.full(600, 6.0), np.full(600, 17.0)])
u2t = u1t*dTt
Th_f = fom_thermal(u1t, u2t); Th_r = rom_thermal(u1t, u2t, Ar_d, Nr_d, br_d)
th_proj = Vt@(Vt.T@Th_f)
thermal = dict(nodes=NX, r=rt, energy=list(map(float, en_t[:6])), op_diff_data_vs_physics=opdiff,
               test_max_err_K=float(np.max(np.abs(Th_r - Th_f))), test_proj_max_err_K=float(np.max(np.abs(th_proj - Th_f))),
               test_rel_err=rel(Th_r, Th_f), tau_s=float(Cp_/(Hg + Ho)), eig_max=float(np.max(np.abs(np.linalg.eigvals(Ar_d + Nr_d)))))
print('thermal ROM: r=%d  |K_data-K_physics|=%.2e  test max err %.4f K (projection %.4f K)  tau %.0f s' %
      (rt, opdiff, thermal['test_max_err_K'], thermal['test_proj_max_err_K'], thermal['tau_s']))

# ----------------------------------------------------------------------------- geometry for drawing / velocity triangles
_, _, _, rows = build(CFG['B'])
geom = []
for i, s in enumerate(C.stg):
    rr = [r for r in rows if r['stage'] == i + 1]
    rot = [r for r in rr if r['kind'] == 'rotor'][0]; sta = [r for r in rr if r['kind'] == 'stator'][0]
    geom.append(dict(stage=i+1, rm=float(s['rm']), lam=float(s['lam']), beta2_deg=float(np.degrees(s['b2'])),
                     alpha3_deg=float(np.degrees(s['a3'])), alpha1_deg=0.0 if i == 0 else float(np.degrees(C.stg[i-1]['a3'])),
                     kappa1_rotor_deg=float(s['k1r']), kappa1_stator_deg=float(s['k1s']),
                     rh=[float(s['d']['rh1']), float(s['d']['rh2']), float(s['d']['rh3'])], A=[float(a) for a in s['A']],
                     Z_rotor=int(rot['Z']), Z_stator=int(sta['Z']), chord_rotor=float(rot['chord']), chord_stator=float(sta['chord'])))
print([(gg['Z_rotor'], gg['Z_stator'], round(gg['chord_rotor']*1e3, 1), round(gg['chord_stator']*1e3, 1)) for gg in geom])

# ----------------------------------------------------------------------------- export
def poly_json(m): return dict(degree=m[0], exps=exps(m[0]), coef=list(map(float, m[1])))
dpt = snapshot(N_D, 1.0)[1]
rom = dict(
    meta=dict(name='C4-ROM v2 (POD + parametric surrogate + OpInf thermal)', created='2026-11-19',
              fom='mean-line stage-stacking off-design model (offdesign.py)', train_domain=dict(N=[N_LO, N_HI], phi=[PHI_LO, PHI_HI]),
              doe='Latin hypercube, 60 points, seed 2026; 45 train / 15 test', inputs='x = N/sqrt(T_amb/288.15)/20000, phi = valve area / design area',
              reference=dict(T=T_REF, P=P_REF, a01=A01, N_D=N_D, cp=cp, gamma=g, R=R)),
    groups=[dict(key=k, label=lab, n=n) for k, lab, n in GROUPS], stations=['inlet', 'R1 exit', 'S1 exit', 'R2 exit', 'S2 exit', 'R3 exit', 'S3 exit', 'R4 exit', 'S4 exit'],
    mean=list(map(float, mean)), scale=list(map(float, scale)), r=RS, V=[list(map(float, U[:, j])) for j in range(RS)],
    sigma=list(map(float, sig)), energy=list(map(float, energy)), norm=dict(x=[0.75, 0.25], phi=[1.22, 0.28]),
    amp=[poly_json(amp_models[j]) for j in range(RS)], scalars={k: poly_json(v) for k, v in scal_models.items()},
    sweep=sweep, metrics=metrics, observability=obs, timing=dict(fom_s=fom_time, rom_python_us=rom_time*1e6),
    thermal=dict(info=thermal, x=list(map(float, xs_c)), f=list(map(float, f_prof)), V=[list(map(float, Vt[:, j])) for j in range(rt)],
                 Ar=Ar_d.tolist(), Nr=Nr_d.tolist(), br=br_d.tolist(), dt=DT, params=PLA, m_design=float(C.m_d)),
    geometry=dict(stages=geom, r_tip=0.0505, module_pitch=0.032),
    design=dict(N=N_D, PR=dpt['PR'], T_out=dpt['T_out'], P_out=dpt['P_out'], m=dpt['m'], eta=dpt['eta'], power_air=dpt['power'], SM=dpt['SM'],
                dT0_stage=[float(s['dT0']) for s in st]),
    points=dict(train=Str[['N', 'phi', 'PR', 'T_out', 'm', 'eta', 'SM']].round(6).to_dict('list'),
                test=Ste[['N', 'phi', 'PR', 'T_out', 'm', 'eta', 'SM']].round(6).to_dict('list'),
                test_rom=dict(PR=list(map(float, ev_te['PR'])), T_out=list(map(float, ev_te['T_out'])), m=list(map(float, ev_te['m'])),
                              eta=list(map(float, ev_te['eta'])), SM=list(map(float, ev_te['SM']))),
                stress=Sst[['N', 'phi', 'PR', 'T_out', 'm']].round(6).to_dict('list'),
                stress_rom=dict(PR=list(map(float, ev_st['PR'])), T_out=list(map(float, ev_st['T_out'])), m=list(map(float, ev_st['m'])))),
    thermal_test=dict(t=list(range(0, T_test + 1, 20)), fom_max=list(map(float, Th_f.max(axis=0)[::20])), rom_max=list(map(float, Th_r.max(axis=0)[::20])),
                      u1=list(map(float, np.append(u1t, u1t[-1])[::20])), dT=list(map(float, np.append(dTt, dTt[-1])[::20]))),
)
json.dump(rom, open(os.path.join(OUT, 'rom_pod.json'), 'w'))
Str.assign(set='train').to_csv(os.path.join(OUT, 'doe_train_45.csv'), index=False)
Ste.assign(set='test').to_csv(os.path.join(OUT, 'doe_test_15.csv'), index=False)
pd.DataFrame(dict(N=Ste.N, phi=Ste.phi, PR_FOM=Ste.PR, PR_ROM=ev_te['PR'], Tout_FOM=Ste.T_out, Tout_ROM=ev_te['T_out'], m_FOM=Ste.m, m_ROM=ev_te['m'],
                  eta_FOM=Ste.eta, eta_ROM=ev_te['eta'], SM_FOM=Ste.SM, SM_ROM=ev_te['SM'])).to_csv(os.path.join(OUT, 'test_comparison.csv'), index=False)
sw.to_csv(os.path.join(OUT, 'model_order_sweep.csv'), index=False)
np.save(os.path.join(OUT, 'snapshots_train.npy'), Xtr)
print('saved; total %.0f s' % (time.time() - t0))
