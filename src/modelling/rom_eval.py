"""Reference evaluator for rom_pod.json (the web twin implements the same equations in JavaScript)."""
import json, numpy as np, os
R = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'models', 'pod_rom', 'rom_pod.json')))
ref = R['meta']['reference']; NS = 9; EXP = ref['gamma']/(ref['gamma'] - 1)
def poly(m, x, phi):
    u = (x - R['norm']['x'][0])/R['norm']['x'][1]; v = (phi - R['norm']['phi'][0])/R['norm']['phi'][1]
    return sum(c*u**i*v**j for (i, j), c in zip(m['exps'], m['coef']))
def predict(N, phi, T_amb=288.15, P_amb=101325.0, clamp=True):
    th = np.sqrt(T_amb/ref['T']); x = N/th/ref['N_D']
    xe = np.clip(x, *R['meta']['train_domain']['N'] and [0.5, 1.0]) if clamp else x
    pe = np.clip(phi, 0.94, 1.50) if clamp else phi
    a = np.array([poly(m, xe, pe) for m in R['amp']])
    q = np.array(R['V']).T@a
    F = q*np.array(R['scale']) + np.array(R['mean'])
    PR = 1 + x**2*F[NS-1]; TR = 1 + x**2*F[2*NS-1]
    m = poly(R['scalars']['mx'], xe, pe)*x*(P_amb/ref['P'])/th
    SM = poly(R['scalars']['SM'], xe, pe)
    eta = (PR**(1/EXP) - 1)/(TR - 1) if x > 0 else np.nan
    return dict(PR=PR, T_out=TR*T_amb, m=m, SM=SM, eta=eta, F=F, x=x)
if __name__ == '__main__':
    s = R['points']['stress']
    for k in range(len(s['N'])):
        for cl in (False, True):
            p = predict(s['N'][k], s['phi'][k], clamp=cl)
            print('N %6.0f phi %.2f clamp %-5s PR fom %.5f rom %.5f err %+.5f | Tout err %+.3f K | m err %+.5f' % (
                s['N'][k], s['phi'][k], cl, s['PR'][k], p['PR'], p['PR'] - s['PR'][k], p['T_out'] - s['T_out'][k], p['m'] - s['m'][k]))
    d = predict(20000, 1.0); print('design', d['PR'], d['T_out'], d['m'], d['eta'], d['SM'])
