"""Train the surrogate on the 45 training points and test it on the 15 independent test points.
Polynomial degree of every output is chosen by leave-one-out cross-validation on the training set only.
A Gaussian-process regression is trained on the same data for comparison.
Writes rom.json, rom_metrics.json, rom_validation/*.png and rom_validation/test_points_comparison.csv."""
import numpy as np, pandas as pd, json, os, sys
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, '..', '..')); OUTM = os.path.join(REPO, 'models', 'rom_v1'); FIGV = os.path.join(REPO, 'figures', 'rom_v1')
os.makedirs(OUTM, exist_ok=True); os.makedirs(FIGV, exist_ok=True)
from rom import ROM, T_REF, P_REF
plt.rcParams.update({'font.family': 'serif', 'font.serif': ['STIXGeneral', 'DejaVu Serif'], 'mathtext.fontset': 'stix', 'font.size': 9})
N_D = 20000.0
DATA = os.path.join(REPO, 'data', 'processed')

def xs(df): return df.rpm.values/np.sqrt((df.T_amb_C.values + 273.15)/T_REF)/N_D
def targets(df):
    x = xs(df); TR = df.T_out_K.values/(df.T_amb_C.values + 273.15)
    th = np.sqrt((df.T_amb_C.values + 273.15)/T_REF); dl = df.P_amb_kPa.values*1e3/P_REF
    return dict(lnPR=(np.log(df.PR.values)/x**2, 2), tau=((TR - 1)/x**2, 2), mc=(df.mdot_kg_s.values*th/dl/x, 1),
                eta=(df.eta_isentropic.values, 0), sm=(df.surge_margin.values, 0))

def fit(x, y, deg):
    V = np.vander(x, deg + 1, increasing=True); return np.linalg.lstsq(V, y, rcond=None)[0]

def loocv(x, y, w, deg):
    e = []
    for i in range(len(x)):
        k = np.arange(len(x)) != i; c = fit(x[k], y[k], deg)
        e.append((sum(ci*x[i]**j for j, ci in enumerate(c)) - y[i])*x[i]**w)
    return np.sqrt(np.mean(np.square(e)))

if __name__ == '__main__':
    tr = pd.read_csv(os.path.join(DATA, 'train_45_points.csv')); te = pd.read_csv(os.path.join(DATA, 'test_15_points.csv'))
    x = xs(tr); coef = {}; chosen = {}
    for k, (y, w) in targets(tr).items():
        cv = {d: loocv(x, y, w, d) for d in range(0, 6)}
        d = min(cv, key=cv.get); coef[k] = fit(x, y, d).tolist(); chosen[k] = dict(degree=d, loocv_rmse={str(a): float(b) for a, b in cv.items()})
        print('%-5s LOOCV RMSE by degree: %s -> degree %d' % (k, ', '.join('%d:%.2e' % (a, b) for a, b in cv.items()), d))
    json.dump(dict(coef=coef, N_design=N_D, meta=dict(description='4-stage axial compressor surrogate (similarity-based polynomials)',
               trained_on='45 random speeds 10000-20000 rpm, design inlet 288.15 K / 101.325 kPa, design valve', rpm_range=[10000, 20000],
               degrees={k: v['degree'] for k, v in chosen.items()})), open(os.path.join(OUTM, 'rom.json'), 'w'), indent=1)
    r = ROM(os.path.join(OUTM, 'rom.json'))
    # ---------------- Gaussian-process comparison (PR and T_out)
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
    gp = {}
    for k in ('PR', 'T_out_C'):
        kern = ConstantKernel(1.0)*RBF(length_scale=0.3) + WhiteKernel(1e-10, (1e-14, 1e-4))
        Xs = (tr.rpm.values[:, None] - 15000)/5000; ym = tr[k].mean(); ys = tr[k].std()
        g = GaussianProcessRegressor(kern, normalize_y=False, n_restarts_optimizer=3, random_state=0).fit(Xs, (tr[k].values - ym)/ys)
        gp[k] = lambda N, g=g, ym=ym, ys=ys: g.predict((np.asarray(N, float)[:, None] - 15000)/5000)*ys + ym
    # ---------------- metrics
    metrics = dict(degrees={k: v['degree'] for k, v in chosen.items()}, n_train=len(tr), n_test=len(te))
    rows = []
    for name, df in (('training', tr), ('test', te)):
        p = r.predict(df.rpm.values, df.T_amb_C.values + 273.15, df.P_amb_kPa.values*1e3)
        m = {}
        for key, true, pred in (('PR', df.PR.values, p['PR']), ('T_out_C', df.T_out_C.values, p['T_out'] - 273.15), ('P_out_kPa', df.P_out_kPa.values, p['P_out']/1e3),
                                ('mdot_kg_s', df.mdot_kg_s.values, p['mdot']), ('power_shaft_W', df.power_shaft_W.values, p['power_shaft']),
                                ('eta', df.eta_isentropic.values, p['eta']), ('surge_margin', df.surge_margin.values, p['surge_margin'])):
            e = pred - true
            m[key] = dict(R2=float(1 - np.sum(e**2)/np.sum((true - true.mean())**2)), RMSE=float(np.sqrt(np.mean(e**2))), max_abs_error=float(np.max(np.abs(e))),
                          MAPE_percent=float(100*np.mean(np.abs(e/true))))
        if name == 'test':
            for key in ('PR', 'T_out_C'):
                e = gp[key](df.rpm.values) - df[key].values
                m[key + '_GPR'] = dict(R2=float(1 - np.sum(e**2)/np.sum((df[key].values - df[key].values.mean())**2)), RMSE=float(np.sqrt(np.mean(e**2))), max_abs_error=float(np.max(np.abs(e))))
            comp = pd.DataFrame(dict(point=df.point, rpm=df.rpm, PR_model=df.PR, PR_ROM=p['PR'], PR_error=p['PR'] - df.PR,
                                     T_out_model_C=df.T_out_C, T_out_ROM_C=p['T_out'] - 273.15, T_out_error_K=p['T_out'] - 273.15 - df.T_out_C,
                                     P_out_model_kPa=df.P_out_kPa, P_out_ROM_kPa=p['P_out']/1e3, mdot_model=df.mdot_kg_s, mdot_ROM=p['mdot'],
                                     power_model_W=df.power_shaft_W, power_ROM_W=p['power_shaft']))
        metrics[name] = m
    comp.to_csv(os.path.join(OUTM, 'test_points_comparison.csv'), index=False, float_format='%.6f')
    json.dump(metrics, open(os.path.join(OUTM, 'rom_metrics.json'), 'w'), indent=1)
    print(json.dumps(metrics['test'], indent=1))
    # ---------------- figures
    import offdesign as od
    C = od.Compressor('B'); Nf = np.linspace(9000, 21000, 49); phys = np.array([[C.operating_point(N)['PR'], C.operating_point(N)['T0'] - 273.15] for N in Nf[::4]])
    pf = r.predict(Nf); pt = r.predict(te.rpm.values)
    fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.4))
    for a, k, kk, lab in ((ax[0], 'PR', 0, 'total pressure ratio'), (ax[1], 'T_out_C', 1, r'outlet total temperature ($^\circ$C)')):
        yv = pf['PR'] if k == 'PR' else pf['T_out'] - 273.15
        a.plot(Nf, yv, '-', color='#1f4e79', lw=1.3, label='surrogate (ROM)')
        a.plot(tr.rpm, tr[k], 'o', ms=3.5, mfc='white', mec='#1f4e79', label='45 training points')
        a.plot(te.rpm, te[k], 's', ms=4.5, color='#c55a11', label='15 test points')
        a.axvspan(10000, 20000, color='#e7eef7', zorder=0); a.set_xlabel('rotational speed (rpm)'); a.set_ylabel(lab); a.grid(alpha=.3)
    ax[0].plot([20000], [1.12], '*', ms=10, color='#c00000', label='design point'); ax[1].plot([20000], [301.77 - 273.15], '*', ms=10, color='#c00000')
    ax[0].legend(frameon=False, fontsize=7.5)
    plt.tight_layout(); plt.savefig(os.path.join(FIGV, 'surrogate_vs_data.png'), dpi=170); plt.close()
    fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.0))
    ax[0].bar(np.arange(len(te)), 1e4*(pt['PR'] - te.PR.values), color='#1f4e79'); ax[0].set_ylabel(r'PR error $\times10^{4}$')
    ax[1].bar(np.arange(len(te)), 1e3*(pt['T_out'] - 273.15 - te.T_out_C.values), color='#c55a11'); ax[1].set_ylabel(r'$T_{out}$ error (mK)')
    for a in ax: a.set_xticks(np.arange(len(te))); a.set_xticklabels(te.point, rotation=90, fontsize=7); a.grid(alpha=.3, axis='y'); a.axhline(0, color='k', lw=0.6)
    plt.tight_layout(); plt.savefig(os.path.join(FIGV, 'test_point_errors.png'), dpi=170); plt.close()
    print('saved rom.json; degrees', metrics['degrees'])
