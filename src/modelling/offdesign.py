"""
Off-design performance model of the 4-stage axial compressor (mean-line stage stacking).

The blade geometry is frozen at the design values (mean radius, annulus areas, blade metal
angles, solidity, work-done factors). For any rotational speed N, mass flow m and inlet
(ambient) state T0, P0, the model marches through the stages:

  rotor   : Cu2 = U - Ca2 tan(beta2_design)            (constant-deviation assumption)
            dT0 = lambda U (Cu2 - Cu1) / cp            (Euler work)
            relative total-pressure loss  w_r(i) * 0.5 rho1 W1^2, i = beta1 - kappa1
  stator  : alpha3 = alpha3_design                     (constant deviation)
            total-pressure loss w_s(i) * 0.5 rho2 C2^2, i = alpha2 - kappa1_stator
  annulus : Ca at every station from continuity with the actual density (fixed areas)

Loss coefficients follow a parabolic incidence "loss bucket" calibrated so that every stage has
the design stage efficiency (0.70) at the design point. The compressor discharges through a fixed
throttle (outlet valve / nozzle) to ambient; its area is sized so that the design point
(20 000 rpm, PR 1.12) lies on the throttle line. Surge is taken at the peak of each speed line
(maximum total pressure ratio) or when a rotor diffusion factor exceeds 0.6.
"""
import numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blades import build, CFG

g = 1.4; R = 287.0; cp = g*R/(g-1); EXP = g/(g-1)
T_REF = 288.15; P_REF = 101325.0
ETA_STAGE_D = 0.70
I_POS = 7.0      # deg, positive-incidence (stall side) half width of the loss bucket
I_NEG = 11.0     # deg, negative-incidence (choke side) half width
CD_THR = 0.80    # throttle discharge coefficient

def static(T0, P0, C):
    T = T0 - C*C/(2*cp)
    if T <= 0: return None
    P = P0*(T/T0)**EXP
    return P/(R*T), T, P

class Compressor:
    def __init__(self, key='B'):
        cfg = CFG[key]; st, mdot, om, rows = build(cfg)
        self.cfg = cfg; self.n = cfg['n']; self.N_d = cfg['rpm']; self.m_d = mdot; self.Ca_d = cfg['Ca']
        RT = 0.05
        self.stg = []
        for s in st:
            r_rot = [r for r in rows if r['stage'] == s['stage'] and r['kind'] == 'rotor'][0]
            r_sta = [r for r in rows if r['stage'] == s['stage'] and r['kind'] == 'stator'][0]
            A = [np.pi*(RT**2 - rh**2) for rh in (s['rh1'], s['rh2'], s['rh3'])]
            self.stg.append(dict(rm=s['rm'], A=A, lam=s['lam'],
                                 b2=np.radians(s['b2']), a3=np.radians(s['a3']),
                                 k1r=s['b1'], k1s=s['a2'],
                                 sig_r=r_rot['secs'][2]['sig'], sig_s=r_sta['secs'][2]['sig'],
                                 wr=0.0, ws=0.0, d=s))
        self._calibrate()
        # throttle area so that the design point lies on the throttle line
        r = self.stages(self.N_d, self.m_d, T_REF, P_REF)
        self.A_thr = self.m_d/self.throttle_flux(r['T0'], r['P0'], P_REF)
        self.design = r

    # --------------------------------------------------------------- losses
    @staticmethod
    def bucket(i):
        h = I_POS if i > 0 else I_NEG
        return 1.0 + (i/h)**2

    def _calibrate(self):
        """loss coefficients so that each stage has eta = 0.70 at the design point.
        As in the design calculation (P02 = P03), the whole design-point stage loss is assigned to the rotor;
        the stator only adds loss when it operates away from its design incidence."""
        om = self.N_d*2*np.pi/60
        T0, P0, a1 = T_REF, P_REF, 0.0
        for s in self.stg:
            res = self.stage(s, om, self.m_d, T0, P0, a1, calib=True)
            s['ws'] = 0.0; s['wr'] = 0.0
            for _ in range(30):                     # fixed point: loss consistent with the actual (lossy) work
                res = self.stage(s, om, self.m_d, T0, P0, a1)
                dT = res['dT0']; T03 = T0 + dT
                P03_target = P0*(1 + ETA_STAGE_D*dT/T0)**EXP
                ds_tot = EXP*np.log(T03/T0) - np.log(P03_target/P0)      # entropy rise / R for eta_s
                wr_new = ds_tot/res['qr']
                if abs(wr_new - s['wr']) < 1e-12: break
                s['wr'] = wr_new
            s['ws'] = 0.5*s['wr']*res['qr']/res['qs']      # stator off-design loss scale (only adds away from design incidence)
            res = self.stage(s, om, self.m_d, T0, P0, a1)
            T0, P0, a1 = res['T03'], res['P03'], s['a3']

    # --------------------------------------------------------------- one stage
    def _Ca(self, m, T0, P0, alpha, A):
        Ca = m/(1.2*A)
        for _ in range(40):
            st = static(T0, P0, Ca/np.cos(alpha))
            if st is None: return None
            Ca_new = m/(st[0]*A)
            if abs(Ca_new - Ca) < 1e-9: break
            Ca = 0.5*Ca + 0.5*Ca_new
            if Ca > 300: return None
        return Ca

    def stage(self, s, om, m, T0, P0, a1, calib=False):
        U = om*s['rm']
        Ca1 = self._Ca(m, T0, P0, a1, s['A'][0])
        if Ca1 is None: return None
        rho1, T1, p1 = static(T0, P0, Ca1/np.cos(a1))
        tb1 = U/Ca1 - np.tan(a1); b1 = np.arctan(tb1)
        W1 = Ca1/np.cos(b1); Cu1 = Ca1*np.tan(a1)
        i_r = np.degrees(b1) - s['k1r']
        qr = 0.5*rho1*W1**2                       # rotor inlet relative dynamic pressure
        # rotor exit: iterate Ca2 (depends on exit state)
        Ca2 = Ca1; T02 = T0; P02 = P0
        for _ in range(60):
            Cu2 = U - Ca2*np.tan(s['b2'])
            dT0 = s['lam']*U*(Cu2 - Cu1)/cp
            T02 = T0 + dT0
            if T02 <= 0: return None
            a2 = np.arctan2(Cu2, Ca2)
            ds_r = 0.0 if calib else s['wr']*self.bucket(i_r)*qr/P0
            P02 = P0*(T02/T0)**EXP*np.exp(-ds_r)
            Ca2n = self._Ca(m, T02, P02, a2, s['A'][1])
            if Ca2n is None: return None
            if abs(Ca2n - Ca2) < 1e-8: break
            Ca2 = 0.5*Ca2 + 0.5*Ca2n
        st2 = static(T02, P02, Ca2/np.cos(a2))
        if st2 is None: return None
        rho2, T2, p2 = st2
        C2 = Ca2/np.cos(a2); W2 = Ca2/np.cos(s['b2'])
        i_s = np.degrees(a2) - s['k1s']
        qs = 0.5*rho2*C2**2
        ds_s = 0.0 if calib else s['ws']*(self.bucket(i_s) - 1.0)*qs/P02     # stator: extra loss away from design incidence only
        T03 = T02; P03 = P02*np.exp(-ds_s)
        Ca3 = self._Ca(m, T03, P03, s['a3'], s['A'][2])
        if Ca3 is None: return None
        rho3, T3, p3 = static(T03, P03, Ca3/np.cos(s['a3']))
        Wu1, Wu2 = Ca1*tb1, Ca2*np.tan(s['b2'])
        DFr = 1 - W2/W1 + (Wu1 - Wu2)/(2*s['sig_r']*W1)
        C3 = Ca3/np.cos(s['a3'])
        DFs = 1 - C3/C2 + (Cu2 - Ca3*np.tan(s['a3']))/(2*s['sig_s']*C2)
        a_sound = np.sqrt(g*R*T1)
        return dict(U=U, Ca1=Ca1, Ca2=Ca2, Ca3=Ca3, b1=np.degrees(b1), a2=np.degrees(a2), i_r=i_r, i_s=i_s,
                    dT0=dT0, T03=T03, P03=P03, p3=p3, DFr=DFr, DFs=DFs, DH=W2/W1, MW1=W1/a_sound,
                    qr=qr/P0, qs=qs/P02, C3=C3, rho3=rho3, work_ok=dT0 > 0,
                    T0in=T0, P0in=P0, p1=p1, T02=T02, P02=P02, p2=p2, i_s_deg=i_s)

    # --------------------------------------------------------------- whole machine
    def stages(self, N, m, T0, P0):
        om = N*2*np.pi/60; a1 = 0.0; Tin, Pin = T0, P0; out = []
        for s in self.stg:
            r = self.stage(s, om, m, T0, P0, a1)
            if r is None: return None
            out.append(r); T0, P0, a1 = r['T03'], r['P03'], s['a3']
        PR = P0/Pin; TR = T0/Tin
        eta = (PR**(1/EXP) - 1)/(TR - 1) if TR > 1 + 1e-9 else np.nan
        return dict(PR=PR, TR=TR, T0=T0, P0=P0, eta=eta, m=m, N=N, power=m*cp*(T0 - Tin),
                    DFmax=max(r['DFr'] for r in out), imax=max(r['i_r'] for r in out),
                    p_static=out[-1]['p3'], C_out=out[-1]['C3'], stages=out)

    def throttle_flux(self, T0, P0, Pa):
        """mass flux per unit area through the outlet throttle (subsonic/choked nozzle to ambient)"""
        pr = max(Pa/P0, (2/(g+1))**EXP)
        if pr >= 1.0: return 0.0
        return CD_THR*P0*np.sqrt(2*g/((g-1)*R*T0)*(pr**(2/g) - pr**((g+1)/g)))

    def speed_line(self, N, T0=T_REF, P0=P_REF, npts=180):
        """total pressure ratio vs mass flow at constant speed (from low flow to choke)"""
        th = np.sqrt(T0/T_REF); dl = P0/P_REF
        m_lo, m_hi = 0.15*self.m_d*N/self.N_d*dl/th, 2.2*self.m_d*N/self.N_d*dl/th
        ms = np.linspace(m_lo, m_hi, npts); res = []
        for m in ms:
            r = self.stages(N, m, T0, P0)
            if r is None or r['PR'] < 1.0 or not np.isfinite(r['eta']):
                if res: break
                continue
            res.append(r)
        if not res: return None
        # surge: peak of the speed line (refined by a parabola), or rotor DF = 0.6 (whichever is at higher flow)
        ms_ = np.array([r['m'] for r in res]); PRs = np.array([r['PR'] for r in res]); DFs = np.array([r['DFmax'] for r in res])
        ipk = int(np.argmax(PRs))
        if 0 < ipk < len(res) - 1:
            cpar = np.polyfit(ms_[ipk-1:ipk+2], PRs[ipk-1:ipk+2], 2)
            m_pk = -cpar[1]/(2*cpar[0]) if cpar[0] < 0 else ms_[ipk]
            PR_pk = np.polyval(cpar, m_pk)
        else:
            m_pk, PR_pk = ms_[ipk], PRs[ipk]
        m_s, PR_s = m_pk, PR_pk
        over = np.where(DFs > 0.60)[0]
        if len(over) and over.max() + 1 < len(res):
            k = over.max()
            f = (0.60 - DFs[k])/(DFs[k+1] - DFs[k])
            m_df = ms_[k] + f*(ms_[k+1] - ms_[k])
            if m_df > m_s: m_s, PR_s = m_df, float(np.interp(m_df, ms_, PRs))
        for r in res: r['stable'] = r['m'] >= m_s
        return dict(points=res, surge_m=float(m_s), surge_PR=float(PR_s))

    def operating_point(self, N, T0=T_REF, P0=P_REF, throttle=1.0, line=None):
        """intersection of the speed line with the throttle characteristic (throttle = valve area / design area)"""
        sl = line if line is not None else self.speed_line(N, T0, P0)
        if not sl: return None
        line = sl['points']
        A = self.A_thr*throttle
        f = np.array([r['m'] - A*self.throttle_flux(r['T0'], r['P0'], P0) for r in line])
        idx = np.where(np.sign(f[:-1]) != np.sign(f[1:]))[0]
        if len(idx) == 0: return None
        k = idx[-1]                                   # stable (right-hand) intersection
        m_a, m_b = line[k]['m'], line[k+1]['m']
        fa, fb = f[k], f[k+1]
        for _ in range(50):                           # refine by regula falsi on the full model
            m_c = m_b - fb*(m_b - m_a)/(fb - fa)
            r = self.stages(N, m_c, T0, P0)
            if r is None: break
            fc = r['m'] - A*self.throttle_flux(r['T0'], r['P0'], P0)
            if abs(fc) < 1e-9*self.m_d: break
            if np.sign(fc) == np.sign(fa): m_a, fa = m_c, fc
            else: m_b, fb = m_c, fc
        r['surge_PR'] = sl['surge_PR']; r['surge_m'] = sl['surge_m']
        r['surge_margin'] = (sl['surge_PR']/r['PR'])*(r['m']/sl['surge_m']) - 1.0
        r['stable'] = bool(r['m'] >= sl['surge_m'])
        r['throttle'] = throttle
        return r

if __name__ == '__main__':
    c = Compressor('B')
    d = c.design
    print('design check: PR %.5f  TR %.5f  T0out %.3f K  eta %.4f  m %.5f  power %.1f W' % (d['PR'], d['TR'], d['T0'], d['eta'], d['m'], d['power']))
    for s in d['stages']: print('  stage i_r %.3f i_s %.3f dT0 %.4f DFr %.3f Ca1 %.2f' % (s['i_r'], s['i_s'], s['dT0'], s['DFr'], s['Ca1']))
    for N in (8000, 12000, 16000, 20000, 22000):
        op = c.operating_point(N)
        print(N, 'PR %.4f m %.4f T0 %.2f eta %.3f P %.0f W SM %.3f stable %s' % (op['PR'], op['m'], op['T0'], op['eta'], op['power'], op['surge_margin'], op['stable']))
