"""Headless closed-loop test of the digital twin (no browser): set-point changes and a motor-speed sag.
Writes data/processed/twin_closed_loop_test.csv and figures/twin/twin_closed_loop_test.png, and prints settling checks."""
import numpy as np, pandas as pd, sys
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from twin_core import Twin
plt.rcParams.update({'font.family': 'serif', 'font.serif': ['STIXGeneral', 'DejaVu Serif'], 'mathtext.fontset': 'stix', 'font.size': 9})

tw = Twin(None); tw.set(mode='AUTO', PR_set=1.10, sag=0.0, running=True)        # design inlet 15 C, 101.325 kPa
events = {300: dict(PR_set=1.12), 600: dict(sag=0.10), 900: dict(PR_set=1.06), 1200: dict(sag=0.0)}
rows = []
for k in range(1500):
    if k in events: tw.set(**events[k])
    tw.step(); s = tw.last
    rows.append(dict(t=s['t'], PR_set=s['PR_set'], PR=s['PR_meas'], PR_rom=s['PR_pred'], rpm=s['rpm'], rpm_cmd=s['rpm_cmd'],
                     T_out=s['T_out_C'], P_out=s['P_out_kPa'], T_amb=s['T_amb_C'], sag=s['sag']))
import os
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
df = pd.DataFrame(rows); df.to_csv(os.path.join(REPO, 'data', 'processed', 'twin_closed_loop_test.csv'), index=False)
def check(t0, t1, label):
    w = df[(df.t > t1 - 5) & (df.t <= t1)]
    print('%-34s PR mean %.4f (set %.3f)  rpm %.0f  cmd %.0f' % (label, w.PR.mean(), w.PR_set.iloc[-1], w.rpm.mean(), w.rpm_cmd.mean()))
    return abs(w.PR.mean() - w.PR_set.iloc[-1])
errs = [check(0, 30, 'PR 1.10'), check(30, 60, 'PR 1.12 (design)'), check(60, 90, 'PR 1.12 + 10 % speed sag'),
        check(90, 120, 'PR 1.06 with sag'), check(120, 150, 'PR 1.06, sag removed')]
print('max steady error %.4f' % max(errs))
fig, ax = plt.subplots(3, 1, figsize=(7, 6.4), sharex=True)
ax[0].plot(df.t, df.PR_set, 'k--', lw=1, label='set point'); ax[0].plot(df.t, df.PR, color='#1f4e79', lw=1.2, label='measured'); ax[0].plot(df.t, df.PR_rom, color='#c55a11', lw=0.8, label='ROM prediction')
ax[0].set_ylabel('total pressure ratio'); ax[0].legend(frameon=False, ncol=3, fontsize=8)
ax[1].plot(df.t, df.rpm_cmd, color='#c55a11', lw=1.1, ls='--', label='motor command'); ax[1].plot(df.t, df.rpm, color='#1f4e79', lw=1.2, label='actual speed')
ax[1].set_ylabel('speed (rpm)'); ax[1].legend(frameon=False, fontsize=8)
ax[2].plot(df.t, df.T_out, color='#c00000', lw=1.2, label='outlet $T_0$'); ax[2].plot(df.t, df.T_amb, color='#548235', lw=1.0, label='ambient $T$'); ax[2].axhline(301.77-273.15, color='grey', lw=0.7, ls='--', label='design outlet 28.62 $^\\circ$C')
ax[2].set_ylabel(r'temperature ($^\circ$C)'); ax[2].set_xlabel('time (s)'); ax[2].legend(frameon=False, fontsize=8)
for a in ax:
    a.grid(alpha=.3)
    for tt in (30, 60, 90, 120):
        a.axvline(tt, color='grey', lw=0.6, ls=':')
for tt, lab in ((30, 'PR set 1.12'), (60, '10 % speed sag'), (90, 'PR set 1.06'), (120, 'sag removed')):
    ax[0].text(tt + 0.8, ax[0].get_ylim()[0] + 0.003, lab, fontsize=7, rotation=90, va='bottom')
plt.tight_layout(); plt.savefig(os.path.join(REPO, 'figures', 'twin', 'twin_closed_loop_test.png'), dpi=170)
