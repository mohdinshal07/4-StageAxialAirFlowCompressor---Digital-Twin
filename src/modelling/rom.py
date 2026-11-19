"""
Surrogate / reduced-order model (ROM) of the 4-stage compressor - runtime part (numpy only).

Trained on 45 random speeds (10 000 - 20 000 rpm) at the design inlet state and design valve opening.
Compressor similarity is built in: the non-dimensional outputs depend on the corrected speed
Nc = N / sqrt(T_amb / 288.15 K), so the model also gives physically consistent answers if the ambient
state of the real rig differs slightly from the design value.

    x = Nc / 20 000
    ln(PR)            = x^2 * sum a_i x^i
    T_out / T_amb - 1 = x^2 * sum b_i x^i
    m_corr            = x   * sum c_i x^i        m_corr = m sqrt(T_amb/288.15) / (P_amb/101.325 kPa)
    eta, surge margin = sum e_i x^i , sum s_i x^i
"""
import json, os, numpy as np

T_REF = 288.15; P_REF = 101325.0; CP = 1004.5; ETA_M = 0.97

class ROM:
    def __init__(self, path=None):
        path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'models', 'rom_v1', 'rom.json')
        d = json.load(open(path))
        self.coef = {k: np.array(v, float) for k, v in d['coef'].items()}
        self.N_design = float(d.get('N_design', 20000.0)); self.meta = d.get('meta', {})
        self.range = self.meta.get('rpm_range', [10000, 20000])

    @staticmethod
    def _poly(c, x):
        return sum(ci*x**i for i, ci in enumerate(c))

    def predict(self, N, T_amb_K=T_REF, P_amb_Pa=P_REF, throttle=1.0):
        """N in rpm; ambient (inlet total) state in K and Pa. (throttle kept for interface compatibility: design opening)"""
        N = np.asarray(N, float); th = np.sqrt(np.asarray(T_amb_K, float)/T_REF); dl = np.asarray(P_amb_Pa, float)/P_REF
        x = N/th/self.N_design
        PR = np.exp(x**2*self._poly(self.coef['lnPR'], x))
        TR = 1.0 + x**2*self._poly(self.coef['tau'], x)
        mc = x*self._poly(self.coef['mc'], x)
        eta = self._poly(self.coef['eta'], x); sm = self._poly(self.coef['sm'], x)
        T_out = np.asarray(T_amb_K)*TR; P_out = np.asarray(P_amb_Pa)*PR; m = mc*dl/th
        P_air = m*CP*(T_out - T_amb_K)
        torque = np.where(N > 0, P_air/ETA_M/(N*2*np.pi/60 + 1e-9), 0.0)
        out = dict(PR=PR, T_out=T_out, P_out=P_out, mdot=m, power_air=P_air, power_shaft=P_air/ETA_M, torque=torque, eta=eta, surge_margin=sm)
        return {k: (float(v) if np.ndim(v) == 0 else v) for k, v in out.items()}

    def rpm_for_PR(self, PR_target, T_amb_K=T_REF, P_amb_Pa=P_REF, throttle=1.0, lo=0.0, hi=30000.0):
        """inverse ROM: speed giving the requested total pressure ratio (PR rises monotonically with speed)"""
        if PR_target <= 1.0: return 0.0
        f = lambda N: self.predict(N, T_amb_K, P_amb_Pa)['PR'] - PR_target
        if f(hi) < 0: return hi
        for _ in range(60):
            mid = 0.5*(lo + hi)
            if f(mid) > 0: hi = mid
            else: lo = mid
        return 0.5*(lo + hi)
