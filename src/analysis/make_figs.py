import os as _os, sys as _sys
REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..'))
FIGP = _os.path.join(REPO, 'figures', 'paper') + '/'; RES = _os.path.join(REPO, 'data', 'processed', 'analysis'); _os.makedirs(RES, exist_ok=True)
DASH = 'file://' + _os.path.join(REPO, 'docs', 'index.html')
_sys.path.insert(0, _os.path.join(REPO, 'src', 'modelling'))
"""Figures for the interim paper (AIAA style: serif, labelled axes with units, 300 dpi)."""
import json, numpy as np, os, sys
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from PIL import Image
F = FIGP
plt.rcParams.update({'font.family': 'serif', 'font.serif': ['STIXGeneral', 'Times New Roman', 'DejaVu Serif'], 'mathtext.fontset': 'stix',
                     'font.size': 8.5, 'axes.labelsize': 8.5, 'legend.fontsize': 7.5, 'xtick.labelsize': 8, 'ytick.labelsize': 8, 'axes.linewidth': 0.7,
                     'lines.linewidth': 1.2, 'savefig.dpi': 300, 'savefig.bbox': 'tight', 'savefig.pad_inches': 0.03})
R = json.load(open(_os.path.join(REPO, 'models', 'pod_rom', 'rom_pod.json'))); M = json.load(open(_os.path.join(REPO, 'models', 'pod_rom', 'map.json')))
UQ = json.load(open(_os.path.join(RES, 'uq_mc.json'))); TW = json.load(open(_os.path.join(RES, 'twin_scenarios.json')))
C1, C2, C3, C4, CG = '#1f4e79', '#c00000', '#548235', '#bf8f00', '#7f7f7f'

# ---- Fig 1: CAD (two renders side by side)
a = Image.open(FIGP + 'B_cad3_iso.png').convert('RGB'); b = Image.open(FIGP + 'B_cad3_section.png').convert('RGB')
def crop(im):
    arr = np.asarray(im).astype(int); mask = (np.abs(arr - arr[0, 0]).sum(2) > 12)
    ys, xs = np.where(mask); return im.crop((xs.min() - 10, ys.min() - 10, xs.max() + 10, ys.max() + 10))
a, b = crop(a), crop(b); h = 700
a = a.resize((int(a.width*h/a.height), h)); b = b.resize((int(b.width*h/b.height), h))
canvas = Image.new('RGB', (a.width + b.width + 40, h), 'white'); canvas.paste(a, (0, 0)); canvas.paste(b, (a.width + 40, 0)); canvas.save(F + 'fig01_cad.png', dpi=(300, 300))

# ---- Fig 2: architecture (four bands, ISO 23247 style)
fig, ax = plt.subplots(figsize=(6.6, 4.1)); ax.set_xlim(0, 100); ax.set_ylim(0, 64); ax.axis('off')
bands = [(0, 'Asset (OME)', '#eef3f8'), (16, 'Sense & act (DCDC)', '#f3f8ee'), (32, 'Twin core', '#fbf6e9'), (48, 'User', '#f4eff8')]
for y, lab, c in bands:
    ax.add_patch(plt.Rectangle((0, y), 100, 16, fc=c, ec='#bbbbbb', lw=0.6)); ax.text(1.2, y + 14.3, lab, fontsize=7.5, weight='bold', va='top')
def box(x, y, w, hh, t, fc='white'):
    ax.add_patch(FancyBboxPatch((x, y), w, hh, boxstyle='round,pad=0.25,rounding_size=1.2', fc=fc, ec='#333333', lw=0.7)); ax.text(x + w/2, y + hh/2, t, ha='center', va='center', fontsize=6.6)
def arr(x0, y0, x1, y1, c='#1f4e79', ls='-', lw=1.0, txt=None, tx=0, ty=0):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle='-|>', mutation_scale=7, color=c, lw=lw, ls=ls))
    if txt: ax.text((x0 + x1)/2 + tx, (y0 + y1)/2 + ty, txt, fontsize=5.8, color=c, ha='center')
box(14, 3, 30, 9, '4-stage PLA axial compressor\n(R1–R4, S1–S4, Ø100 mm)'); box(50, 3, 18, 9, 'BLDC motor\n5687, 1100 kV'); box(74, 3, 22, 9, 'Outlet valve\n(load, % area)')
box(4, 19, 18, 9, '2 × PT100\n+ MAX31865\n(10 Hz)'); box(24, 19, 18, 9, '2(+1) × LPS33HW\nabs. pressure\n(25 Hz, LPF)'); box(44, 19, 16, 9, 'Arduino UNO\nR4 WiFi:\ntimestamp, seq.'); box(63, 19, 15, 9, 'VESC 75200\nspeed loop\nI, V, rpm'); box(81, 19, 15, 9, 'Watchdog: ramp\ndown if no cmd\nfor 1 s')
box(3, 35, 17, 10, 'MQTT broker\n(Mosquitto)\nQoS 1, JSON'); box(22, 35, 15, 10, 'Logger / TSDB\nraw + quality\nflags'); box(39, 35, 18, 10, 'POD ROM\n+ motor model\n+ thermal ROM'); box(59, 35, 17, 10, 'Kalman filter\nhealth h_p, h_T\nCUSUM, NIS'); box(78, 35, 19, 10, 'Decision: PR\ncontroller (FF+PI),\nsurge & thermal\nlimits')
box(10, 51, 34, 9, 'Dashboard: measured vs predicted,\ndeviation, alarms, map, logs'); box(52, 51, 40, 9, 'Operator / researcher: set-point, load,\nwhat-if (inlet T), stop-inspect decision')
arr(29, 12, 13, 19, txt='T', tx=-2); arr(32, 12, 33, 19, txt='p', tx=1.5); arr(59, 12, 70, 19, c=C1)
arr(13, 28, 47, 28.5, c=C1); arr(33, 28, 47, 27.5, c=C1)
arr(52, 28, 12, 35, c=C1, txt='publish sensors/… (10 Hz)', ty=1.2); arr(70, 28, 56, 28.3, c=C1, ls='-', txt='UART telemetry', ty=1.0)
arr(20, 40, 22, 40); arr(20, 42, 39, 42.5); arr(57, 40, 59, 40); arr(76, 40, 78, 40); arr(48, 45, 30, 51); arr(68, 45, 40, 51)
arr(72, 51, 87, 45, c=C2, txt='set-point', tx=4)
arr(87, 35, 70.5, 28, c=C2, lw=1.6, txt='cmd/rpm (return path)', tx=3, ty=0.8); arr(66, 19, 59, 12, c=C2, lw=1.6); arr(88, 28, 84, 19.2, c=C2, ls='--')
ax.text(99, 0.8, 'blue: data upward (physical → digital)   red: commands downward (digital → physical)', fontsize=5.8, ha='right', color='#444444')
plt.savefig(F + 'fig02_architecture.png'); plt.close()

# ---- Fig 3: DOE and compressor map
fig, ax = plt.subplots(1, 2, figsize=(6.6, 2.6))
P = R['points']
ax[0].plot(P['train']['N'], P['train']['phi'], 'o', ms=3.2, mfc='white', mec=C1, label='45 training'); ax[0].plot(P['test']['N'], P['test']['phi'], 's', ms=3.4, color=C2, label='15 test')
ax[0].plot(P['stress']['N'], P['stress']['phi'], 'D', ms=3.4, color=C4, label='5 stress'); ax[0].plot([1e4, 2e4, 2e4, 1e4, 1e4], [.94, .94, 1.5, 1.5, .94], '--', color=CG, lw=0.8, label='training domain')
ax[0].set_xlabel('rotational speed, rpm'); ax[0].set_ylabel('valve opening φ (area / design area)'); ax[0].legend(frameon=False, ncol=2, loc='upper center', bbox_to_anchor=(0.5, 1.22)); ax[0].grid(alpha=.3)
for l in M['lines']:
    m, pr, s = np.array(l['m']), np.array(l['PR']), np.array(l['s'])
    ax[1].plot(m[s == 1], pr[s == 1], '-', color=CG, lw=0.9); ax[1].plot(m[s == 0], pr[s == 0], ':', color=CG, lw=0.8)
    if m[-1] < 0.255: ax[1].text(m[-1] + 0.002, pr[-1], f"{l['N']//1000}k", fontsize=6, color='#555555', va='center')
ax[1].plot(M['surge']['m'], M['surge']['PR'], '-', color=C2, lw=1.5, label='surge line')
import rom_eval as RE
for phi, ls in ((0.94, '--'), (1.0, '-'), (1.5, '-.')):
    Ns = np.linspace(6000, 22000, 40); pts = [RE.predict(n, phi) for n in Ns]
    ax[1].plot([q['m'] for q in pts], [q['PR'] for q in pts], ls, color=C1, lw=1.0, label=f'operating line φ = {phi:.2f} (ROM)')
ax[1].plot(R['design']['m'], R['design']['PR'], '*', ms=9, color='k', label='design point')
ax[1].set_xlim(0.06, 0.26); ax[1].set_ylim(1.0, 1.17); ax[1].set_xlabel('corrected mass flow, kg/s'); ax[1].set_ylabel('total pressure ratio'); ax[1].grid(alpha=.3)
ax[1].legend(frameon=False, fontsize=6.4, loc='upper left')
plt.tight_layout(); plt.savefig(F + 'fig03_doe_map.png'); plt.close()

# ---- Fig 4: POD spectrum, modes, model order
fig, ax = plt.subplots(1, 3, figsize=(6.6, 2.25))
s = np.array(R['sigma']); ax[0].semilogy(np.arange(1, 17), s[:16]/s[0], 'o-', ms=3, color=C1); ax[0].axvline(R['r'], color=C4, ls='--', lw=0.9); ax[0].text(R['r'] + 0.3, 0.3, f'r = {R["r"]}', color=C4, fontsize=7)
ax[0].set_xlabel('mode index i'); ax[0].set_ylabel('σ$_i$/σ$_1$'); ax[0].grid(alpha=.3, which='both')
V = np.array(R['V']); st = ['in', 'R1', 'S1', 'R2', 'S2', 'R3', 'S3', 'R4', 'S4']
for j, c in enumerate((C1, C2, C3, C4)): ax[1].plot(range(9), V[j, :9], 'o-', ms=2.6, color=c, label=f'mode {j+1}')
ax[1].set_xticks(range(9)); ax[1].set_xticklabels(st, fontsize=6.5); ax[1].set_xlabel('station'); ax[1].set_ylabel('mode entry (P$_0$ group)'); ax[1].legend(frameon=False, fontsize=6, ncol=2); ax[1].grid(alpha=.3)
sw = R['sweep']; rr = [q['r'] for q in sw]
ax[2].semilogy(rr, [q['proj_err'] for q in sw], 's-', ms=3, color=CG, label='basis only (projection)'); ax[2].semilogy(rr, [q['rom_err'] for q in sw], 'o-', ms=3, color=C1, label='ROM (held-out test)')
ax[2].set_xlabel('number of POD modes r'); ax[2].set_ylabel('relative field error'); ax[2].legend(frameon=False, fontsize=6.2); ax[2].grid(alpha=.3, which='both')
plt.tight_layout(); plt.savefig(F + 'fig04_pod.png'); plt.close()

# ---- Fig 5: parity (test + stress)
fig, ax = plt.subplots(1, 2, figsize=(6.6, 2.6))
for k_, (key, lab, sc, off) in enumerate((('PR', 'total pressure ratio', 1, 0), ('T_out', 'outlet total temperature, °C', 1, -273.15))):
    x = np.array(P['test'][key])*sc + off; y = np.array(P['test_rom'][key])*sc + off; xs = np.array(P['stress'][key]) + off; ys = np.array(P['stress_rom'][key]) + off
    lo, hi = min(x.min(), xs.min()), max(x.max(), xs.max()); pad = (hi - lo)*0.05
    ax[k_].plot([lo - pad, hi + pad], [lo - pad, hi + pad], '--', color=CG, lw=0.8)
    ax[k_].plot(x, y, 's', ms=3.6, color=C1, label='15 test points'); ax[k_].plot(xs, ys, 'D', ms=3.6, color=C4, label='stress (outside domain)')
    ax[k_].set_xlabel(f'FOM {lab}'); ax[k_].set_ylabel(f'ROM {lab}'); ax[k_].grid(alpha=.3); ax[k_].legend(frameon=False, loc='upper left')
plt.tight_layout(); plt.savefig(F + 'fig05_parity.png'); plt.close()

# ---- Fig 6: thermal ROM
q = R['thermal_test']; fig, ax = plt.subplots(figsize=(6.6, 2.2)); ax2 = ax.twinx()
ax.plot(q['t'], q['fom_max'], '-', color=CG, lw=3, label='FOM, 40 nodes'); ax.plot(q['t'], q['rom_max'], '--', color=C1, lw=1.3, label=f'OpInf ROM, r = {R["thermal"]["info"]["r"]}')
ax2.plot(q['t'], q['dT'], '-', color=C4, lw=0.8, label='input: gas ΔT$_0$'); ax.set_xlabel('time, s'); ax.set_ylabel('max casing temperature rise, K'); ax2.set_ylabel('gas ΔT$_0$, K', color=C4)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax.legend(h1 + h2, l1 + l2, frameon=False, loc='lower right', ncol=3); ax.grid(alpha=.3)
plt.tight_layout(); plt.savefig(F + 'fig06_thermal.png'); plt.close()

# ---- Fig 7: UQ band + SRC
fig, ax = plt.subplots(1, 2, figsize=(6.6, 2.5), gridspec_kw={'width_ratios': [1.25, 1]})
Ns = UQ['speeds']; S_ = UQ['summary']
Nn = np.linspace(9000, 21000, 60); ax[0].plot(Nn, [RE.predict(n, 1.0)['PR'] for n in Nn], '-', color=C1, label='ROM, nominal model')
lo = [S_[f'PR@{n}']['p2_5'] for n in Ns]; hi = [S_[f'PR@{n}']['p97_5'] for n in Ns]; mu = [S_[f'PR@{n}']['mean'] for n in Ns]
ax[0].errorbar(Ns, mu, yerr=[np.array(mu) - lo, np.array(hi) - mu], fmt='o', ms=3.5, color=C2, capsize=3, lw=1, label='FOM Monte Carlo, 95 % interval (n = 64)')
ax[0].set_xlabel('rotational speed, rpm'); ax[0].set_ylabel('total pressure ratio'); ax[0].legend(frameon=False, fontsize=6.6, loc='upper left'); ax[0].grid(alpha=.3)
src = UQ['src']; outs = ['PR', 'T_out_C', 'mdot', 'eta', 'SM']; labs = ['PR', 'T$_{out}$', 'ṁ', 'η', 'SM']; w = 0.26; xx = np.arange(len(outs))
for i, (k_, c, lb) in enumerate((('eta_s', C1, 'η$_s$ ∈ [0.65, 0.75]'), ('dbeta2', C2, 'Δβ$_2$ ∈ [−1°, 1°]'), ('I_pos', C3, 'i$_+$ ∈ [5°, 9°]'))):
    ax[1].bar(xx + (i - 1)*w, [src[o][k_] for o in outs], w, color=c, label=lb)
ax[1].axhline(0, color='k', lw=0.6); ax[1].set_xticks(xx); ax[1].set_xticklabels(labs); ax[1].set_ylabel('standardised regression coeff.'); ax[1].legend(frameon=False, fontsize=6.2, loc='lower center', bbox_to_anchor=(0.5, 1.0), ncol=3, columnspacing=0.8, handlelength=1.2); ax[1].grid(alpha=.3, axis='y')
plt.tight_layout(); plt.savefig(F + 'fig07_uq.png'); plt.close()

# ---- Fig 8: fault-detection scenario
r = TW['s1']['rec']; t = np.array([z['t'] for z in r]); g = lambda k: np.array([np.nan if z[k] is None else z[k] for z in r])
fig, ax = plt.subplots(3, 1, figsize=(6.6, 4.4), sharex=True)
ax[0].plot(t, g('PRm'), '-', color=C3, lw=0.9, label='measured (virtual rig, SIM)'); ax[0].plot(t, g('PRe'), '--', color=C1, lw=1.2, label='twin expectation, healthy baseline (EST)')
ax[0].set_ylabel('pressure ratio'); ax[0].set_ylim(1.0, 1.16); ax[0].legend(frameon=False, loc='upper center', ncol=2)
ax[1].fill_between(t, g('hp') - g('hpS'), g('hp') + g('hpS'), color=C1, alpha=.2); ax[1].plot(t, g('hp'), color=C1, label='h$_p$ ± 2σ')
ax[1].fill_between(t, g('ht') - g('htS'), g('ht') + g('htS'), color=C2, alpha=.2); ax[1].plot(t, g('ht'), color=C2, label='h$_T$ ± 2σ')
ax[1].axhline(0.928, color=C1, ls=':', lw=0.8); ax[1].axhline(1.036, color=C2, ls=':', lw=0.8); ax[1].set_ylim(0.9, 1.06); ax[1].set_ylabel('health factor'); ax[1].legend(frameon=False, loc='lower left', ncol=2)
ax[2].plot(t, np.minimum(g('cPR'), 60), color=C1, label='CUSUM, pressure ratio'); ax[2].plot(t, np.minimum(g('cT'), 60), color=C2, label='CUSUM, outlet T$_0$'); ax[2].axhline(8, color='k', ls='--', lw=0.8, label='alarm threshold h = 8')
ax[2].set_ylabel('CUSUM statistic'); ax[2].set_xlabel('time, s'); ax[2].set_ylim(0, 62); ax[2].legend(frameon=False, loc='center right')
for a_ in ax: a_.axvline(40, color=CG, lw=0.7, ls=':'); a_.axvline(60, color=C2, lw=0.8, ls=':'); a_.grid(alpha=.3)
ax[0].text(41, 1.012, 'baseline set', fontsize=6.5, color=CG); ax[0].text(61, 1.012, 'blade erosion injected (severity 60 %)', fontsize=6.5, color=C2)
plt.tight_layout(); plt.savefig(F + 'fig08_fault.png'); plt.close()

# ---- Fig 9: PR control with speed sag
r = TW['s2']['rec']; t = np.array([z['t'] for z in r]); g = lambda k: np.array([np.nan if z[k] is None else z[k] for z in r])
fig, ax = plt.subplots(2, 1, figsize=(6.6, 3.1), sharex=True)
ax[0].plot(t, g('PRset'), '--', color='k', lw=0.9, label='set point'); ax[0].plot(t, g('PRm'), color=C3, lw=1.0, label='measured (SIM)'); ax[0].set_ylabel('pressure ratio'); ax[0].set_ylim(1.0, 1.14); ax[0].legend(frameon=False, loc='center', bbox_to_anchor=(0.42, 0.42), ncol=2)
ax[1].plot(t, g('Ncmd'), '--', color=C2, label='motor speed command (twin → VESC)'); ax[1].plot(t, g('N'), color=C1, label='measured speed'); ax[1].set_ylabel('speed, rpm'); ax[1].set_xlabel('time, s'); ax[1].legend(frameon=False, loc='lower right')
for a_ in ax: a_.axvline(60, color=C2, ls=':', lw=0.8); a_.axvline(110, color=CG, ls=':', lw=0.8); a_.grid(alpha=.3)
ax[0].text(61, 1.01, '10 % speed sag', fontsize=6.5, color=C2); ax[0].text(111, 1.01, 'set point 1.08', fontsize=6.5, color=CG)
plt.tight_layout(); plt.savefig(F + 'fig09_control.png'); plt.close()
print('figures done', sorted(os.listdir(F)))
