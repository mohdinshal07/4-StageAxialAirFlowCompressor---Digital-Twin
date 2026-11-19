"""
Digital-twin core: virtual rig (plant), sensors, PR controller and motor-command generation.
Pure Python + numpy, independent of the web dashboard so it can be tested headless.
"""
import numpy as np, time, threading, collections
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'modelling'))
from rom import ROM, T_REF, P_REF

# outlet spool annulus (bore R50.5 mm, centre body = exit hub R38.44 mm) - used to convert static to total pressure
A_OUT = np.pi*(0.0505**2 - 0.03844**2)
POLE_PAIRS = 2          # 4-pole inrunner -> ERPM = 2 x RPM (VESC uses ERPM)

class VirtualRig:
    """Simulated compressor test rig used when no hardware is connected.
    Motor + driver speed loop as a first-order lag; 'speed sag' disturbance makes the motor run slower than
    commanded (battery sag / load / driver in duty mode); compressor response from the ROM; sensors with lag and noise."""
    def __init__(self, rom, tau_motor=0.6, P_max=4000.0, N_max=26000.0, seed=1):
        self.rom = rom; self.tau = tau_motor; self.P_max = P_max; self.N_max = N_max
        self.N = 0.0; self.sag = 0.0; self.rng = np.random.default_rng(seed)
        self.s = dict(T_amb=None, P_amb=None, T_out=None, P_out=None)
        self.power_limited = False

    def _N_power_limit(self, T, P, thr):
        lo, hi = 0.0, self.N_max
        if self.rom.predict(hi, T, P, thr)['power_shaft'] <= self.P_max: return hi
        for _ in range(40):
            mid = 0.5*(lo + hi)
            if self.rom.predict(mid, T, P, thr)['power_shaft'] > self.P_max: hi = mid
            else: lo = mid
        return lo

    def step(self, dt, N_cmd, T_amb, P_amb, thr):
        target = min(max(N_cmd, 0.0), self.N_max)*(1.0 - self.sag)
        N_lim = self._N_power_limit(T_amb, P_amb, thr)
        self.power_limited = target > N_lim
        target = min(target, N_lim)
        self.N += (target - self.N)*min(dt/self.tau, 1.0)
        true = self.rom.predict(max(self.N, 1.0), T_amb, P_amb, thr)
        noise = self.rng.normal
        meas = dict(T_amb=T_amb + noise(0, 0.03), P_amb=P_amb + noise(0, 8.0),
                    T_out=float(true['T_out']), P_out=float(true['P_out']), N=self.N + noise(0, 8.0))
        # first-order sensor dynamics: RTD probe ~3 s, pressure sensor ~0.1 s
        for k, tau in (('T_amb', 3.0), ('T_out', 3.0), ('P_amb', 0.1), ('P_out', 0.1)):
            v = meas[k] if k not in ('T_out', 'P_out') else meas[k]
            if self.s[k] is None: self.s[k] = v
            self.s[k] += (v - self.s[k])*min(dt/tau, 1.0)
        out = dict(T_amb=self.s['T_amb'], P_amb=self.s['P_amb'], T_out=self.s['T_out'] + noise(0, 0.03),
                   P_out=self.s['P_out'] + noise(0, 8.0), N=max(meas['N'], 0.0))
        return out

class PRController:
    """Outer loop: holds the total pressure ratio by commanding motor speed.
    N_cmd = N_feedforward(ROM inverse) + Kp*e + Ki*int(e),  e = PR_set - PR_measured,
    with output limits, rate limit and anti-windup. Gains are in rpm per unit PR."""
    def __init__(self, rom, Kp=2.0e4, Ki=6.0e4, N_max=25000.0, rate=3000.0):
        self.rom = rom; self.Kp = Kp; self.Ki = Ki; self.N_max = N_max; self.rate = rate
        self.I = 0.0; self.N_cmd = 0.0

    def reset(self, N_now=0.0):
        self.I = 0.0; self.N_cmd = N_now

    def update(self, dt, PR_set, PR_meas, T_amb, P_amb, thr):
        N_ff = self.rom.rpm_for_PR(PR_set, T_amb, P_amb, thr)
        e = PR_set - PR_meas
        u = N_ff + self.Kp*e + self.Ki*(self.I + e*dt)
        u_lim = min(max(u, 0.0), self.N_max)
        du = np.clip(u_lim - self.N_cmd, -self.rate*dt, self.rate*dt)
        # anti-windup: integrate only when neither the speed limits nor the rate limit are active
        if u_lim == u and abs(du) < self.rate*dt*0.999: self.I += e*dt
        self.N_cmd += du
        return self.N_cmd, N_ff, e

class Twin:
    """Runs the loop (10 Hz), keeps history and exposes the state to the dashboard."""
    def __init__(self, rom_path=None, hw=None, dt=0.1):
        self.rom = ROM(rom_path); self.dt = dt; self.hw = hw
        self.rig = VirtualRig(self.rom); self.ctrl = PRController(self.rom)
        self.lock = threading.Lock()
        # ambient = design inlet state used in the design calculation (288.15 K, 101.325 kPa); design valve opening
        self.cfg = dict(mode='AUTO', running=True, PR_set=1.12, N_manual=15000.0, throttle=1.0,
                        T_amb_C=15.0, P_amb_kPa=101.325, sag=0.0, P_max_W=4000.0)
        self.t = 0.0; self.hist = collections.deque(maxlen=900); self.log = collections.deque(maxlen=12)
        self.last = {}; self._last_cmd = None
        self.rig.N = 0.0

    def set(self, **kw):
        with self.lock:
            for k, v in kw.items():
                if k in self.cfg: self.cfg[k] = type(self.cfg[k])(v) if not isinstance(self.cfg[k], bool) else bool(v)
            if 'mode' in kw and kw['mode'] == 'AUTO': self.ctrl.reset(self.ctrl.N_cmd)
            self.rig.sag = float(self.cfg['sag']); self.rig.P_max = float(self.cfg['P_max_W'])

    def step(self):
        c = self.cfg; dt = self.dt
        T_amb_true = c['T_amb_C'] + 273.15; P_amb_true = c['P_amb_kPa']*1e3; thr = c['throttle']
        N_prev_cmd = self.ctrl.N_cmd
        # ---- measurements
        if self.hw is not None:
            m = self.hw.read()                                   # dict T_amb[K], P_amb[Pa], T_out[K], p_out_static[Pa], N[rpm]
            if m is None: m = self.last.get('meas_raw')
            if m is None: return
            pred_tmp = self.rom.predict(max(m['N'], 1.0), m['T_amb'], m['P_amb'], thr)
            rho = m['p_out_static']/(287.0*m['T_out']); C = pred_tmp['mdot']/(rho*A_OUT)
            meas = dict(T_amb=m['T_amb'], P_amb=m['P_amb'], T_out=m['T_out'], P_out=m['p_out_static'] + 0.5*rho*C*C, N=m['N'])
            self.last['meas_raw'] = m
        else:
            meas = self.rig.step(dt, N_prev_cmd if c['running'] else 0.0, T_amb_true, P_amb_true, thr)
        PR_meas = meas['P_out']/meas['P_amb']
        # ---- controller / motor command
        if not c['running']:
            N_cmd, N_ff, e = 0.0, 0.0, 0.0; self.ctrl.reset(0.0)
        elif c['mode'] == 'AUTO':
            N_cmd, N_ff, e = self.ctrl.update(dt, c['PR_set'], PR_meas, meas['T_amb'], meas['P_amb'], thr)
        else:
            target = c['N_manual']; du = np.clip(target - self.ctrl.N_cmd, -self.ctrl.rate*dt, self.ctrl.rate*dt)
            self.ctrl.N_cmd += du; self.ctrl.I = 0.0; N_cmd, N_ff, e = self.ctrl.N_cmd, target, 0.0
        if self.hw is not None: self.hw.write_rpm(N_cmd)
        # ---- ROM prediction (twin) from the measured speed and ambient state
        pred = self.rom.predict(max(meas['N'], 1.0), meas['T_amb'], meas['P_amb'], thr)
        alarms = []
        if pred['surge_margin'] < 0.02 and meas['N'] > 3000: alarms.append('SURGE MARGIN LOW - open the outlet valve')
        if meas['T_out'] - 273.15 > 50: alarms.append('OUTLET TEMPERATURE > 50 C (PLA limit)')
        if self.hw is None and self.rig.power_limited: alarms.append('MOTOR POWER LIMIT')
        if c['mode'] == 'AUTO' and c['running'] and N_cmd >= self.ctrl.N_max - 1: alarms.append('SPEED LIMIT - PR set point not reachable')
        lo, hi = self.rom.range
        notes = [] if lo <= meas['N'] <= 1.025*hi or not c['running'] else ['speed outside the surrogate training range (%d-%d rpm)' % (lo, hi)]
        settled = c['mode'] == 'AUTO' and abs(e) < 0.002
        cmd = 'SET_RPM %d  (ERPM %d)' % (round(N_cmd), round(N_cmd*POLE_PAIRS))
        if self._last_cmd is None or abs(N_cmd - self._last_cmd) >= 50:
            self.log.appendleft('t=%7.1f s  %s' % (self.t, cmd)); self._last_cmd = N_cmd
        self.t += dt
        s = dict(t=round(self.t, 2), mode=c['mode'], running=c['running'], source='HARDWARE' if self.hw else 'SIMULATION',
                 T_amb_C=meas['T_amb'] - 273.15, P_amb_kPa=meas['P_amb']/1e3, T_out_C=meas['T_out'] - 273.15, P_out_kPa=meas['P_out']/1e3,
                 rpm=meas['N'], PR_meas=PR_meas, PR_pred=pred['PR'], PR_set=c['PR_set'], rpm_cmd=N_cmd, rpm_ff=N_ff, err=e,
                 T_out_pred_C=pred['T_out'] - 273.15, P_out_pred_kPa=pred['P_out']/1e3, mdot=pred['mdot'], power_kW=pred['power_shaft']/1e3,
                 torque=pred['torque'], eta=pred['eta'], surge_margin=pred['surge_margin'], throttle=thr, sag=c['sag'],
                 mcorr=pred['mdot']*np.sqrt(meas['T_amb']/T_REF)/(meas['P_amb']/P_REF), command=cmd, alarms=alarms, notes=notes, settled=settled)
        self.last.update(s); self.hist.append({k: s[k] for k in ('t', 'PR_meas', 'PR_pred', 'PR_set', 'rpm', 'rpm_cmd', 'T_out_C', 'P_out_kPa')})

    def run_forever(self):
        nxt = time.time()
        while True:
            with self.lock: self.step()
            nxt += self.dt; time.sleep(max(0.0, nxt - time.time()))

    def snapshot(self, n_hist=600):
        with self.lock:
            h = list(self.hist)[-n_hist:]
            hist = {k: [round(x[k], 5) for x in h] for k in (h[0].keys() if h else [])}
            s = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in self.last.items() if k != 'meas_raw'}
            return dict(state=s, hist=hist, log=list(self.log), cfg=dict(self.cfg))
