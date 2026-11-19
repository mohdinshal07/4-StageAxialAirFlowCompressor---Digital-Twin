"""Serial -> MQTT bridge for the compressor rig (laptop side).

Reads the board's 10 Hz lines   D,<T_amb_C>,<P_amb_Pa>,<T_out_C>,<p_out_static_Pa>,<rpm>
and publishes one JSON message per line on   <prefix>/telemetry   (schema: message_schema.json).
Speed commands published on   <prefix>/cmd   as {"N_cmd_rpm": 15000} are forwarded to the board as  R,<rpm>.
Raw lines are also appended, unchanged, to data/raw/<session>.csv.

    python mqtt_bridge.py --port COM5 --broker localhost            (Windows)
    python mqtt_bridge.py --port /dev/ttyACM0 --broker localhost    (Linux / macOS)

Requires pyserial and paho-mqtt (pip install pyserial paho-mqtt) and a broker (e.g. Mosquitto) on the laptop.
STATUS: written against the interface in the interim paper; not yet tested on the hardware.
"""
import argparse, json, os, threading, time, uuid
from datetime import datetime, timezone

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
MAX_RPM, MAX_RATE = 24000, 3000.0          # same limits as the twin controller (rpm, rpm/s)


def parse_line(line):
    """'D,25.10,101300,38.40,112900,15020' -> dict or None"""
    p = line.strip().split(',')
    if len(p) != 6 or p[0] != 'D':
        return None
    try:
        T_amb, P_amb, T_out, p_out, N = map(float, p[1:])
    except ValueError:
        return None
    return dict(T_amb_C=T_amb, P_amb_Pa=P_amb, T_out_C=T_out, p_out_static_Pa=p_out, N_rpm=N)


def quality(v):
    """simple range checks -> 'ok' or 'suspect'"""
    ok = (-20 < v['T_amb_C'] < 60 and 80e3 < v['P_amb_Pa'] < 110e3 and -20 < v['T_out_C'] < 90
          and 80e3 < v['p_out_static_Pa'] < 140e3 and 0 <= v['N_rpm'] < 30000)
    return 'ok' if ok else 'suspect'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', required=True); ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--broker', default='localhost'); ap.add_argument('--mqtt-port', type=int, default=1883)
    ap.add_argument('--prefix', default='team12/c4'); ap.add_argument('--asset', default='C4-rig-01')
    a = ap.parse_args()

    import serial                                      # pyserial
    import paho.mqtt.client as mqtt

    ser = serial.Serial(a.port, a.baud, timeout=0.1)
    boot = uuid.uuid4().hex[:8]; seq = 0; lock = threading.Lock()
    session = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(os.path.join(REPO, 'data', 'raw'), exist_ok=True)
    rawf = open(os.path.join(REPO, 'data', 'raw', f'session_{session}.csv'), 'a', buffering=1)
    rawf.write('t_utc,line\n')
    last_cmd = {'rpm': 0.0, 't': time.time()}

    def on_connect(c, userdata, flags, rc, *args):
        c.subscribe(f'{a.prefix}/cmd', qos=1)
        print('MQTT connected; listening for commands on', f'{a.prefix}/cmd')

    def on_message(c, userdata, msg):
        try:
            rpm = float(json.loads(msg.payload)['N_cmd_rpm'])
        except (ValueError, KeyError, TypeError):
            return
        now = time.time(); dt = max(now - last_cmd['t'], 1e-3)
        rpm = min(max(rpm, 0.0), MAX_RPM)                                       # clamp
        rpm = min(max(rpm, last_cmd['rpm'] - MAX_RATE*dt), last_cmd['rpm'] + MAX_RATE*dt)   # rate limit
        last_cmd.update(rpm=rpm, t=now)
        with lock:
            ser.write(('R,%d\n' % round(rpm)).encode())

    cli = mqtt.Client(client_id=f'{a.asset}-bridge-{boot}')
    cli.on_connect = on_connect; cli.on_message = on_message
    cli.connect(a.broker, a.mqtt_port, keepalive=10); cli.loop_start()

    print(f'bridge running: {a.port} -> mqtt://{a.broker}:{a.mqtt_port}/{a.prefix}/telemetry   (Ctrl+C to stop)')
    buf = b''
    try:
        while True:
            buf += ser.read(256)
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                s = line.decode(errors='ignore').strip(); t = datetime.now(timezone.utc).isoformat()
                if not s: continue
                rawf.write(f'{t},"{s}"\n')                                     # raw data kept unchanged
                v = parse_line(s)
                if v is None: continue
                seq += 1
                msg = dict(asset_id=a.asset, boot_id=boot, seq=seq, t_event_utc=t, source='measured',
                           values=v, units=dict(T_amb_C='degC', P_amb_Pa='Pa', T_out_C='degC', p_out_static_Pa='Pa', N_rpm='rpm'),
                           quality=quality(v))
                cli.publish(f'{a.prefix}/telemetry', json.dumps(msg), qos=1)
    except KeyboardInterrupt:
        pass
    finally:
        with lock: ser.write(b'R,0\n')                                         # ask the board to stop the motor
        cli.loop_stop(); rawf.close(); ser.close(); print('stopped')


if __name__ == '__main__':
    main()
