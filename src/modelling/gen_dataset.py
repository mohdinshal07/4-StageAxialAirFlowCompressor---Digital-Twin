"""Generate the surrogate-training dataset of the 4-stage compressor with the physics-based off-design model.

Operating condition: design inlet (ambient) state used in the design calculation, T01 = 288.15 K (15 C),
P01 = 101.325 kPa, design outlet-valve opening. Speeds are random (uniform) in 10 000 - 20 000 rpm:
45 points for training the surrogate and 15 different points for testing it.

Outputs (folder data/):
  train_45_points.csv, test_15_points.csv     surrogate training / test data
  compressor_map_speedlines.csv, surge_line.csv  compressor map (dashboard)
  Compressor_4stage_dataset.xlsx              all of the above + description sheet
"""
import numpy as np, pandas as pd, os, time, io
from multiprocessing import Pool
import offdesign as od

N_LO, N_HI, N_TRAIN, N_TEST, SEED = 10000, 20000, 45, 15, 2026
C = None
def init():
    global C
    C = od.Compressor('B')

COLS = ['rpm', 'T_amb_C', 'P_amb_kPa', 'PR', 'T_out_C', 'T_out_K', 'P_out_kPa', 'p_out_static_kPa', 'mdot_kg_s',
        'power_air_W', 'power_shaft_W', 'torque_Nm', 'eta_isentropic', 'surge_margin']

def point(N):
    op = C.operating_point(N, od.T_REF, od.P_REF, 1.0)
    Psh = op['power']/0.97
    return [N, od.T_REF - 273.15, od.P_REF/1e3, op['PR'], op['T0'] - 273.15, op['T0'], op['P0']/1e3, op['p_static']/1e3, op['m'],
            op['power'], Psh, Psh/(N*2*np.pi/60), op['eta'], op['surge_margin']]

def speedline(N):
    sl = C.speed_line(N, npts=120)
    return [[N, r['m'], r['PR'], r['TR'], r['eta'], int(r['stable'])] for r in sl['points']], (N, sl['surge_m'], sl['surge_PR'])

if __name__ == '__main__':
    DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'processed'); os.makedirs(DATA, exist_ok=True); t = time.time()
    rng = np.random.default_rng(SEED)
    pool_ = rng.permutation(np.arange(N_LO, N_HI + 1))          # distinct random integer speeds
    train = np.sort(pool_[:N_TRAIN]); test = np.sort(pool_[N_TRAIN:N_TRAIN + N_TEST])
    with Pool(2, initializer=init) as p:
        A = p.map(point, train.tolist()); B = p.map(point, test.tolist())
        SL = p.map(speedline, list(range(8000, 22001, 2000)))
    dfA = pd.DataFrame(A, columns=COLS); dfB = pd.DataFrame(B, columns=COLS)
    dfA.insert(0, 'point', ['TR%02d' % (i+1) for i in range(len(dfA))]); dfB.insert(0, 'point', ['TE%02d' % (i+1) for i in range(len(dfB))])
    dfM = pd.DataFrame([x for s in SL for x in s[0]], columns=['rpm', 'mdot_kg_s', 'PR', 'T_ratio', 'eta_isentropic', 'stable'])
    dfS = pd.DataFrame([s[1] for s in SL], columns=['rpm', 'surge_mdot_kg_s', 'surge_PR'])
    dfA.to_csv(os.path.join(DATA, 'train_45_points.csv'), index=False, float_format='%.6f')
    dfB.to_csv(os.path.join(DATA, 'test_15_points.csv'), index=False, float_format='%.6f')
    dfM.to_csv(os.path.join(DATA, 'compressor_map_speedlines.csv'), index=False, float_format='%.6g')
    dfS.to_csv(os.path.join(DATA, 'surge_line.csv'), index=False, float_format='%.6g')
    # combined file (train + test) with rounding suited to each quantity
    dfC = pd.concat([dfA.assign(set='train'), dfB.assign(set='test')], ignore_index=True)
    dfC = dfC[['point', 'set'] + [c for c in dfA.columns if c != 'point']]
    dfC = pd.read_csv(io.StringIO(dfC.to_csv(index=False, float_format='%.6f')))   # same 6-decimal values as the train/test files
    for c, d in dict(PR=6, T_out_C=4, T_out_K=4, P_out_kPa=4, p_out_static_kPa=4, mdot_kg_s=5, power_air_W=2, power_shaft_W=2,
                     torque_Nm=5, eta_isentropic=5, surge_margin=5).items():
        dfC[c] = dfC[c].round(d)
    dfC.to_csv(os.path.join(DATA, 'Compressor_4stage_dataset.csv'), index=False)
    desc = pd.DataFrame([
        ['operating condition', 'design inlet state T = 288.15 K (15 C), P = 101.325 kPa; design outlet-valve opening'],
        ['speeds', '45 random training speeds and 15 different random test speeds, uniform in 10 000 - 20 000 rpm (seed %d)' % SEED],
        ['rpm', 'rotational speed (rev/min)'], ['T_amb_C, P_amb_kPa', 'ambient = inlet total temperature and pressure'],
        ['PR', 'total-to-total pressure ratio P_out/P_amb'], ['T_out_C, T_out_K', 'outlet total temperature'],
        ['P_out_kPa', 'outlet total pressure (abs)'], ['p_out_static_kPa', 'outlet static pressure (abs)'], ['mdot_kg_s', 'mass flow rate'],
        ['power_air_W', 'power absorbed by the air m*cp*(T_out - T_amb)'], ['power_shaft_W', 'shaft power, mechanical efficiency 0.97'],
        ['torque_Nm', 'shaft torque'], ['eta_isentropic', 'overall isentropic efficiency'], ['surge_margin', '(PR_surge/PR)(m/m_surge) - 1 at the same speed'],
        ['design check', 'at 20 000 rpm the model gives PR 1.1200 and T_out 301.77 K (28.62 C), identical to the design calculation']],
        columns=['item', 'meaning'])
    with pd.ExcelWriter(os.path.join(DATA, 'Compressor_4stage_dataset.xlsx')) as xw:
        desc.to_excel(xw, sheet_name='README', index=False)
        dfA.to_excel(xw, sheet_name='train_45', index=False); dfB.to_excel(xw, sheet_name='test_15', index=False)
        dfM.to_excel(xw, sheet_name='map_speedlines', index=False); dfS.to_excel(xw, sheet_name='surge_line', index=False)
    print('train', len(dfA), 'test', len(dfB), 'speedline pts', len(dfM), 'time %.0f s' % (time.time() - t))
    print(dfA[['point', 'rpm', 'PR', 'T_out_C', 'P_out_kPa', 'mdot_kg_s', 'power_shaft_W']].to_string(index=False))
    print(dfB[['point', 'rpm', 'PR', 'T_out_C', 'P_out_kPa', 'mdot_kg_s', 'power_shaft_W']].to_string(index=False))
