import os as _os, sys as _sys
REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..'))
FIGP = _os.path.join(REPO, 'figures', 'paper') + '/'; RES = _os.path.join(REPO, 'data', 'processed', 'analysis'); _os.makedirs(RES, exist_ok=True)
DASH = 'file://' + _os.path.join(REPO, 'docs', 'index.html')
_sys.path.insert(0, _os.path.join(REPO, 'src', 'modelling'))
"""GUM-style uncertainty budgets for the measured pressure ratio, temperature rise and efficiency at the design point."""
import numpy as np, json
k = 0.4/1.4; PR = 1.12; Pa = 1013.25; Po = PR*Pa; T1 = 288.15; dT = 13.62; T1c = 15.0; T2c = 28.62
def U(bound): return bound/np.sqrt(3)                       # uniform bounds -> standard uncertainty
q_out = 0.5*1.30*47.5**2/100                            # outlet dynamic pressure, hPa
cases = {}
# ---- case A: as delivered, static wall tap converted to total with the ROM mass flow, no cross-calibration
pA_out = dict(sensor_abs=U(2.5), dyn_conv=q_out*2*0.0134, unsteady=0.10, noise_avg=0.02/np.sqrt(10))
pA_amb = dict(sensor_abs=U(2.5), noise_avg=0.02/np.sqrt(10))
tA = dict(class_B_inlet=U(0.30 + 0.005*T1c), class_B_outlet=U(0.30 + 0.005*T2c), ref_resistor_in=U(0.26), ref_resistor_out=U(0.26), recovery=U(0.25*1.12), resolution=2*U(0.0156))
# ---- case B: one-point zero-speed cross-calibration of both channels, total-pressure (Kiel) probe, recovery correction
pB_out = dict(relative=U(0.1), unsteady=0.10, noise_avg=0.02/np.sqrt(10))
pB_amb = dict(relative=U(0.1), noise_avg=0.02/np.sqrt(10))
tB = dict(cross_cal_repeat=np.sqrt(2)*0.03, class_B_gain=U(0.005*dT), recovery=U(0.1*1.12), resolution=2*U(0.0156))
def rss(d): return float(np.sqrt(sum(v**2 for v in d.values())))
def eta(pr, dt): return (pr**k - 1)*T1/dt
for name, po, pa, tt in (('A', pA_out, pA_amb, tA), ('B', pB_out, pB_amb, tB)):
    uPo, uPa, udT = rss(po), rss(pa), rss(tt)
    uPR = PR*np.sqrt((uPo/Po)**2 + (uPa/Pa)**2)
    e0 = eta(PR, dT); de_dPR = (eta(PR + 1e-6, dT) - e0)/1e-6; de_ddT = (eta(PR, dT + 1e-6) - e0)/1e-6
    ueta = np.sqrt((de_dPR*uPR)**2 + (de_ddT*udT)**2)
    cases[name] = dict(u_Pout_hPa=uPo, u_Pamb_hPa=uPa, u_PR=uPR, U95_PR=2*uPR, U95_PR_pct_of_rise=100*2*uPR/(PR - 1), u_dT=udT, U95_dT=2*udT,
                       U95_dT_pct=100*2*udT/dT, eta=e0, U95_eta=2*ueta, terms=dict(Pout=po, Pamb=pa, dT=tt))
json.dump(cases, open(_os.path.join(RES, 'gum.json'), 'w'), indent=1)
for n, c in cases.items(): print(n, {k_: round(v, 5) for k_, v in c.items() if not isinstance(v, dict)})
print('q_out hPa', q_out)
