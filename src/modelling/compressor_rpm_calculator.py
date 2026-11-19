"""
Four-stage 3D-printed axial-flow compressor (Team 12, AE 541) - operating-point calculator
==========================================================================================

Change RPM in the INPUTS block below and run:

    python compressor_rpm_calculator.py

or give the speed(s) on the command line (this overrides RPM):

    python compressor_rpm_calculator.py 15000
    python compressor_rpm_calculator.py 10000 12500 15000 17500 20000      (summary table + CSV file)

For one speed it prints the overall performance (pressure ratio, outlet temperature and pressure, mass flow,
power, torque, efficiency, surge margin) and the stage-by-stage values. For several speeds it prints a table
and writes compressor_results.csv with the same columns as Compressor_4stage_dataset.csv.

Model: the same mean-line stage-stacking off-design model that generated the dataset. The blade geometry is
frozen at the design values; for a given speed the stages are marched with continuity, Euler work and an
incidence-dependent loss calibrated to a stage efficiency of 0.70 at the design point, and the operating point
is where the speed line meets the outlet-valve characteristic. At 20,000 rpm it reproduces the design
calculation (PR 1.1200, T_out 301.77 K). The results are MODEL PREDICTIONS (simulated), not measurements.

Requires: Python 3 and numpy.
"""
import sys, csv, math
import numpy as np

# ================================= INPUTS: change these ==================================
RPM = 15000          # shaft speed, rev/min              (dataset: 10,000 - 20,000 rpm)
T_AMB_C = 15.0       # inlet (ambient) total temperature, deg C   (dataset: 15.0)
P_AMB_KPA = 101.325  # inlet (ambient) total pressure, kPa        (dataset: 101.325)
VALVE = 1.0          # outlet-valve opening = valve area / design valve area (dataset: 1.0; surge below about 0.93)
ETA_MECH = 0.97      # mechanical efficiency used for shaft power  (dataset: 0.97)
# ==========================================================================================

# ----------------------------------------------------------------------------- gas and model constants
g = 1.4; R = 287.0; cp = g*R/(g - 1); EXP = g/(g - 1)
T_REF, P_REF = 288.15, 101325.0          # design inlet state
N_DESIGN = 20000.0                       # design speed, rpm
CA_DESIGN = 50.0                         # design axial velocity, m/s
ETA_STAGE_D = 0.70                       # design stage isentropic efficiency (loss calibration)
I_POS, I_NEG = 7.0, 11.0                 # half widths of the incidence loss bucket, deg (stall / choke side)
CD_VALVE = 0.80                          # outlet-valve discharge coefficient
DF_LIMIT = 0.60                          # rotor diffusion-factor limit used for surge
R_TIP = 0.050                            # constant tip radius, m

# Design geometry of the four stages (from the design calculation):
#   rm = mean radius [m]; rh = hub radius at rotor inlet, rotor exit, stator exit [m]; lam = work-done factor;
#   b2 = rotor exit relative angle [deg]; a3 = stator exit angle [deg]; k1r / k1s = rotor / stator inlet metal angle [deg];
#   sig_r / sig_s = rotor / stator solidity (mean radius)
GEOMETRY = [
    dict(rm=0.04382124297420846, rh=(0.0375, 0.037668203629232525, 0.03778497189470861), lam=0.98,
         b2=43.54372329629171, a3=8.0, k1r=61.41902805626004, k1s=41.51409716401514, sig_r=1.9334657311233236, sig_s=1.3715469853215019),
    dict(rm=0.04395699069486923, rh=(0.03778497189470861, 0.037896246262338146, 0.03804299088338777), lam=0.93,
         b2=39.82815505684828, a3=8.0, k1r=59.545134424959336, k1s=45.20736356554639, sig_r=2.0292839283887085, sig_s=1.975650237842034),
    dict(rm=0.04408053198849739, rh=(0.03804299088338777, 0.038137335882558236, 0.03827913706943905), lam=0.88,
         b2=39.98294817100155, a3=8.0, k1r=59.62113509051248, k1s=45.22396017428524, sig_r=2.0741234622890024, sig_s=2.1218677592199295),
    dict(rm=0.044180287818745265, rh=(0.03827913706943905, 0.03835733242615488, 0.03844201420554201), lam=0.83,
         b2=46.894077030665784, a3=0.0, k1r=59.68225335331986, k1s=38.03314555260508, sig_r=0.9586970342724197, sig_s=1.310692610332615),
]


def static(T0, P0, C):
    """static density, temperature and pressure from total state and velocity"""
    T = T0 - C*C/(2*cp)
    if T <= 0: return None
    p = P0*(T/T0)**EXP
    return p/(R*T), T, p


class Compressor:
    def __init__(self):
        self.stg = []
        for s in GEOMETRY:
            self.stg.append(dict(s, A=[math.pi*(R_TIP**2 - rh**2) for rh in s['rh']],
                                 b2r=math.radians(s['b2']), a3r=math.radians(s['a3']), wr=0.0, ws=0.0))
        # design mass flow: continuity at the inlet with Ca = 50 m/s at the design inlet state
        rho1 = static(T_REF, P_REF, CA_DESIGN)[0]
        self.m_d = rho1*CA_DESIGN*self.stg[0]['A'][0]
        self._calibrate()
        # outlet-valve area that puts the design point on the valve characteristic
        d = self.stages(N_DESIGN, self.m_d, T_REF, P_REF)
        self.A_valve = self.m_d/self.valve_flux(d['T0'], d['P0'], P_REF)
        self.design = d

    # --------------------------------------------------------------------- losses
    @staticmethod
    def bucket(i):
        h = I_POS if i > 0 else I_NEG
        return 1.0 + (i/h)**2

    def _calibrate(self):
        """rotor loss coefficient of each stage so that the stage efficiency is 0.70 at the design point;
        the stator adds loss only away from its design incidence"""
        om = N_DESIGN*2*math.pi/60
        T0, P0, a1 = T_REF, P_REF, 0.0
        for s in self.stg:
            s['wr'] = s['ws'] = 0.0
            for _ in range(30):
                r = self.stage(s, om, self.m_d, T0, P0, a1)
                T03 = T0 + r['dT0']
                P03_target = P0*(1 + ETA_STAGE_D*r['dT0']/T0)**EXP
                wr_new = (EXP*math.log(T03/T0) - math.log(P03_target/P0))/r['qr']
                if abs(wr_new - s['wr']) < 1e-12: break
                s['wr'] = wr_new
            s['ws'] = 0.5*s['wr']*r['qr']/r['qs']
            r = self.stage(s, om, self.m_d, T0, P0, a1)
            T0, P0, a1 = r['T03'], r['P03'], s['a3r']

    # --------------------------------------------------------------------- one stage
    def _Ca(self, m, T0, P0, alpha, A):
        """axial velocity from continuity with the actual (static) density"""
        Ca = m/(1.2*A)
        for _ in range(40):
            st = static(T0, P0, Ca/math.cos(alpha))
            if st is None: return None
            Ca_new = m/(st[0]*A)
            if abs(Ca_new - Ca) < 1e-9: break
            Ca = 0.5*Ca + 0.5*Ca_new
            if Ca > 300: return None
        return Ca

    def stage(self, s, om, m, T0, P0, a1):
        U = om*s['rm']
        Ca1 = self._Ca(m, T0, P0, a1, s['A'][0])
        if Ca1 is None: return None
        rho1, T1, p1 = static(T0, P0, Ca1/math.cos(a1))
        tb1 = U/Ca1 - math.tan(a1); b1 = math.atan(tb1)
        W1 = Ca1/math.cos(b1); Cu1 = Ca1*math.tan(a1)
        i_r = math.degrees(b1) - s['k1r']                       # rotor incidence
        qr = 0.5*rho1*W1**2
        Ca2, T02, P02 = Ca1, T0, P0
        for _ in range(60):                                      # rotor exit state
            Cu2 = U - Ca2*math.tan(s['b2r'])                     # constant deviation
            dT0 = s['lam']*U*(Cu2 - Cu1)/cp                      # Euler work
            T02 = T0 + dT0
            if T02 <= 0: return None
            a2 = math.atan2(Cu2, Ca2)
            P02 = P0*(T02/T0)**EXP*math.exp(-s['wr']*self.bucket(i_r)*qr/P0)
            Ca2n = self._Ca(m, T02, P02, a2, s['A'][1])
            if Ca2n is None: return None
            if abs(Ca2n - Ca2) < 1e-8: break
            Ca2 = 0.5*Ca2 + 0.5*Ca2n
        st2 = static(T02, P02, Ca2/math.cos(a2))
        if st2 is None: return None
        rho2, T2, p2 = st2
        C2 = Ca2/math.cos(a2); W2 = Ca2/math.cos(s['b2r'])
        i_s = math.degrees(a2) - s['k1s']                       # stator incidence
        qs = 0.5*rho2*C2**2
        T03 = T02; P03 = P02*math.exp(-s['ws']*(self.bucket(i_s) - 1.0)*qs/P02)
        Ca3 = self._Ca(m, T03, P03, s['a3r'], s['A'][2])
        if Ca3 is None: return None
        rho3, T3, p3 = static(T03, P03, Ca3/math.cos(s['a3r']))
        Wu1, Wu2 = Ca1*tb1, Ca2*math.tan(s['b2r'])
        DFr = 1 - W2/W1 + (Wu1 - Wu2)/(2*s['sig_r']*W1)
        C3 = Ca3/math.cos(s['a3r'])
        DFs = 1 - C3/C2 + (Cu2 - Ca3*math.tan(s['a3r']))/(2*s['sig_s']*C2)
        eta_st = ((P03/P0)**(1/EXP) - 1)/(T03/T0 - 1) if T03 > T0 else float('nan')
        return dict(U=U, Ca1=Ca1, Ca2=Ca2, Ca3=Ca3, i_r=i_r, i_s=i_s, dT0=dT0, T0in=T0, P0in=P0, T03=T03, P03=P03,
                    p3=p3, C3=C3, DFr=DFr, DFs=DFs, DH=W2/W1, M_rel=W1/math.sqrt(g*R*T1), eta=eta_st,
                    qr=qr/P0, qs=qs/P02)

    # --------------------------------------------------------------------- whole machine
    def stages(self, N, m, T0, P0):
        om = N*2*math.pi/60; a1 = 0.0; Tin, Pin = T0, P0; out = []
        for s in self.stg:
            r = self.stage(s, om, m, T0, P0, a1)
            if r is None: return None
            out.append(r); T0, P0, a1 = r['T03'], r['P03'], s['a3r']
        PR = P0/Pin; TR = T0/Tin
        eta = (PR**(1/EXP) - 1)/(TR - 1) if TR > 1 + 1e-9 else float('nan')
        return dict(PR=PR, TR=TR, T0=T0, P0=P0, eta=eta, m=m, N=N, power=m*cp*(T0 - Tin),
                    DFmax=max(r['DFr'] for r in out), p_static=out[-1]['p3'], C_out=out[-1]['C3'], stages=out)

    def valve_flux(self, T0, P0, Pa):
        """mass flow per unit valve area (nozzle discharging to ambient, subsonic or choked)"""
        pr = max(Pa/P0, (2/(g + 1))**EXP)
        if pr >= 1.0: return 0.0
        return CD_VALVE*P0*math.sqrt(2*g/((g - 1)*R*T0)*(pr**(2/g) - pr**((g + 1)/g)))

    def speed_line(self, N, T0, P0, npts=180):
        """pressure ratio against mass flow at constant speed, and the surge point"""
        th = math.sqrt(T0/T_REF); dl = P0/P_REF
        ms = np.linspace(0.15*self.m_d*N/N_DESIGN*dl/th, 2.2*self.m_d*N/N_DESIGN*dl/th, npts); res = []
        for m in ms:
            r = self.stages(N, m, T0, P0)
            if r is None or r['PR'] < 1.0 or not np.isfinite(r['eta']):
                if res: break
                continue
            res.append(r)
        if not res: return None
        m_ = np.array([r['m'] for r in res]); PR_ = np.array([r['PR'] for r in res]); DF_ = np.array([r['DFmax'] for r in res])
        k = int(np.argmax(PR_))
        if 0 < k < len(res) - 1:                                 # peak of the speed line, refined by a parabola
            c = np.polyfit(m_[k-1:k+2], PR_[k-1:k+2], 2)
            m_s = -c[1]/(2*c[0]) if c[0] < 0 else m_[k]; PR_s = np.polyval(c, m_s)
        else:
            m_s, PR_s = m_[k], PR_[k]
        over = np.where(DF_ > DF_LIMIT)[0]                       # or rotor DF = 0.6, whichever is at higher flow
        if len(over) and over.max() + 1 < len(res):
            j = over.max(); f = (DF_LIMIT - DF_[j])/(DF_[j+1] - DF_[j]); m_df = m_[j] + f*(m_[j+1] - m_[j])
            if m_df > m_s: m_s, PR_s = m_df, float(np.interp(m_df, m_, PR_))
        return dict(points=res, surge_m=float(m_s), surge_PR=float(PR_s))

    def operating_point(self, N, T0, P0, valve=1.0):
        """intersection of the speed line with the outlet-valve characteristic"""
        sl = self.speed_line(N, T0, P0)
        if not sl: return None
        line = sl['points']; A = self.A_valve*valve
        f = np.array([r['m'] - A*self.valve_flux(r['T0'], r['P0'], P0) for r in line])
        idx = np.where(np.sign(f[:-1]) != np.sign(f[1:]))[0]
        if len(idx) == 0: return None
        k = idx[-1]
        m_a, m_b, fa, fb = line[k]['m'], line[k+1]['m'], f[k], f[k+1]
        r = line[k]
        for _ in range(50):                                      # regula falsi on the full model
            m_c = m_b - fb*(m_b - m_a)/(fb - fa)
            rc = self.stages(N, m_c, T0, P0)
            if rc is None: break
            r = rc; fc = r['m'] - A*self.valve_flux(r['T0'], r['P0'], P0)
            if abs(fc) < 1e-9*self.m_d: break
            if np.sign(fc) == np.sign(fa): m_a, fa = m_c, fc
            else: m_b, fb = m_c, fc
        r['surge_PR'], r['surge_m'] = sl['surge_PR'], sl['surge_m']
        r['surge_margin'] = (sl['surge_PR']/r['PR'])*(r['m']/sl['surge_m']) - 1.0
        r['stable'] = bool(r['m'] >= sl['surge_m'])
        return r


_C = None
def calculate(rpm, t_amb_c=T_AMB_C, p_amb_kpa=P_AMB_KPA, valve=VALVE, eta_mech=ETA_MECH):
    """operating point at the given speed; returns a dict (None if no stable operating point is found)"""
    global _C
    if _C is None: _C = Compressor()
    Ta, Pa = t_amb_c + 273.15, p_amb_kpa*1e3
    op = _C.operating_point(float(rpm), Ta, Pa, valve)
    if op is None: return None
    om = rpm*2*math.pi/60; P_shaft = op['power']/eta_mech
    return dict(rpm=rpm, T_amb_C=t_amb_c, P_amb_kPa=p_amb_kpa, valve=valve,
                PR=op['PR'], T_out_C=op['T0'] - 273.15, T_out_K=op['T0'], dT0_K=op['T0'] - Ta,
                P_out_kPa=op['P0']/1e3, p_out_static_kPa=op['p_static']/1e3, V_out_m_s=op['C_out'],
                mdot_kg_s=op['m'], mdot_corr_kg_s=op['m']*math.sqrt(Ta/T_REF)/(Pa/P_REF),
                power_air_W=op['power'], power_shaft_W=P_shaft, torque_Nm=P_shaft/om if om > 0 else float('nan'),
                eta_isentropic=op['eta'], surge_margin=op['surge_margin'], surge_PR=op['surge_PR'],
                surge_mdot_kg_s=op['surge_m'], stable=op['stable'], DF_max=op['DFmax'], stages=op['stages'])


# ----------------------------------------------------------------------------- output
CSV_COLS = ['rpm', 'T_amb_C', 'P_amb_kPa', 'PR', 'T_out_C', 'T_out_K', 'P_out_kPa', 'p_out_static_kPa', 'mdot_kg_s',
            'power_air_W', 'power_shaft_W', 'torque_Nm', 'eta_isentropic', 'surge_margin']

def warnings_for(r):
    w = []
    if not 10000 <= r['rpm'] <= 20000:
        w.append('Speed is outside the 10,000-20,000 rpm range of the dataset; the model still runs, but treat the result with more caution.')
    if r['rpm'] > 20000:
        w.append('Speed is above the 20,000 rpm design speed: check the PLA rotor stresses and the motor limits before running the rig this fast.')
    if r['surge_margin'] < 0.03:
        w.append('Surge margin is below 3 %: the operating point is close to surge.')
    if r['T_out_C'] > 50:
        w.append('Outlet air is above 50 C (PLA parts soften at about 55-60 C).')
    return w

def print_report(r):
    L = '-'*78
    print(L); print('FOUR-STAGE AXIAL COMPRESSOR - operating point (model prediction, not a measurement)'); print(L)
    print(f"Inputs   : speed {r['rpm']:,.0f} rpm | inlet {r['T_amb_C']:.2f} C, {r['P_amb_kPa']:.3f} kPa | valve opening {r['valve']:.2f}")
    print(L)
    rows = [('Total pressure ratio', f"{r['PR']:.5f}", '-'),
            ('Outlet total temperature', f"{r['T_out_C']:.3f}  ({r['T_out_K']:.3f} K)", 'C'),
            ('Total temperature rise', f"{r['dT0_K']:.3f}", 'K'),
            ('Outlet total pressure', f"{r['P_out_kPa']:.3f}", 'kPa'),
            ('Outlet static pressure', f"{r['p_out_static_kPa']:.3f}", 'kPa'),
            ('Outlet velocity', f"{r['V_out_m_s']:.2f}", 'm/s'),
            ('Mass flow rate', f"{r['mdot_kg_s']:.5f}", 'kg/s'),
            ('Corrected mass flow', f"{r['mdot_corr_kg_s']:.5f}", 'kg/s'),
            ('Power absorbed by the air', f"{r['power_air_W']:.1f}", 'W'),
            (f"Shaft power (mech. eff. {ETA_MECH:.2f})", f"{r['power_shaft_W']:.1f}", 'W'),
            ('Shaft torque', f"{r['torque_Nm']:.4f}", 'N m'),
            ('Isentropic efficiency', f"{r['eta_isentropic']:.4f}", '-'),
            ('Surge margin', f"{r['surge_margin']*100:.2f}", '%'),
            ('Surge point at this speed', f"PR {r['surge_PR']:.4f}, mdot {r['surge_mdot_kg_s']:.4f}", 'kg/s'),
            ('Maximum rotor diffusion factor', f"{r['DF_max']:.3f}", '-'),
            ('Operating point stable', 'yes' if r['stable'] else 'NO (in surge)', '')]
    for a, b, c in rows: print(f"{a:<34s}{b:>30s}  {c}")
    print(L); print('Stage-by-stage'); print(L)
    print(f"{'stage':>5s}{'U':>8s}{'Ca1':>7s}{'i_rot':>7s}{'i_sta':>7s}{'dT0':>7s}{'T03':>8s}{'P03':>9s}{'PR_st':>8s}{'eta_st':>7s}{'DF_r':>6s}{'W2/W1':>7s}{'M_rel':>6s}")
    print(f"{'':>5s}{'m/s':>8s}{'m/s':>7s}{'deg':>7s}{'deg':>7s}{'K':>7s}{'C':>8s}{'kPa':>9s}{'-':>8s}{'-':>7s}{'-':>6s}{'-':>7s}{'-':>6s}")
    for k, s in enumerate(r['stages']):
        print(f"{k+1:>5d}{s['U']:8.2f}{s['Ca1']:7.2f}{s['i_r']:7.2f}{s['i_s']:7.2f}{s['dT0']:7.3f}{s['T03']-273.15:8.3f}"
              f"{s['P03']/1e3:9.3f}{s['P03']/s['P0in']:8.5f}{s['eta']:7.3f}{s['DFr']:6.3f}{s['DH']:7.3f}{s['M_rel']:6.3f}")
    print(L)
    for w in warnings_for(r): print('WARNING: ' + w)


def main(argv):
    speeds = [float(a.replace(',', '')) for a in argv[1:]] or [RPM]
    if any(n <= 0 for n in speeds): sys.exit('Speed must be positive.')
    if len(speeds) == 1:
        r = calculate(speeds[0])
        if r is None:
            sys.exit(f'No operating point found at {speeds[0]:,.0f} rpm with valve opening {VALVE} (speed too low, or the valve is so far closed that the compressor surges).')
        print_report(r); return
    # several speeds: summary table + CSV in the dataset format
    out = []
    print(f"{'rpm':>8s}{'PR':>9s}{'T_out C':>9s}{'P_out kPa':>11s}{'mdot kg/s':>11s}{'P_air W':>9s}{'P_shaft W':>10s}{'torque Nm':>10s}{'eta':>7s}{'SM %':>7s}")
    for n in speeds:
        r = calculate(n)
        if r is None: print(f'{n:8.0f}   no operating point'); continue
        out.append(r)
        print(f"{n:8.0f}{r['PR']:9.5f}{r['T_out_C']:9.3f}{r['P_out_kPa']:11.3f}{r['mdot_kg_s']:11.5f}{r['power_air_W']:9.1f}"
              f"{r['power_shaft_W']:10.1f}{r['torque_Nm']:10.4f}{r['eta_isentropic']:7.4f}{r['surge_margin']*100:7.2f}")
    with open('compressor_results.csv', 'w', newline='') as fh:
        wr = csv.writer(fh); wr.writerow(CSV_COLS)
        for r in out: wr.writerow([f'{r[c]:g}' if c == 'rpm' else (f'{r[c]:.6f}' if isinstance(r[c], float) else r[c]) for c in CSV_COLS])
    print('\nSaved compressor_results.csv')


if __name__ == '__main__':
    main(sys.argv)
