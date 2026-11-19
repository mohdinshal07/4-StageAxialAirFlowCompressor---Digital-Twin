"""
4-stage axial compressor - digital twin dashboard.

    python app.py                 # simulation mode (virtual rig)
    python app.py --port COM5     # hardware mode (ESP32 / UNO R4 WiFi on COM5, see firmware/)
then open http://127.0.0.1:5000 in a browser.
"""
import argparse, threading, os, json, logging
import numpy as np, pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from twin_core import Twin

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(HERE, 'static'))
logging.getLogger('werkzeug').setLevel(logging.ERROR)
twin = None

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/state')
def state():
    return jsonify(twin.snapshot())

@app.route('/api/cmd', methods=['POST'])
def cmd():
    twin.set(**(request.get_json(force=True) or {}))
    return jsonify(ok=True, cfg=twin.cfg)

@app.route('/api/map')
def cmap():
    """compressor map at ISA: speed lines and surge line from the physics dataset (corrected flow = flow at ISA)"""
    d = os.path.join(HERE, '..', '..', 'data', 'processed')
    sl = pd.read_csv(os.path.join(d, 'compressor_map_speedlines.csv')); su = pd.read_csv(os.path.join(d, 'surge_line.csv'))
    lines = [dict(rpm=int(N), m=g.mdot_kg_s.round(5).tolist(), PR=g.PR.round(5).tolist(), stable=g.stable.tolist()) for N, g in sl.groupby('rpm')]
    return jsonify(lines=lines, surge=dict(m=su.surge_mdot_kg_s.round(5).tolist(), PR=su.surge_PR.round(5).tolist(), rpm=su.rpm.tolist()))

@app.route('/api/opline')
def opline():
    """throttle (operating) line for the current valve opening, from the ROM"""
    thr = float(request.args.get('thr', 1.0)); Ns = np.linspace(8000, 22000, 41)
    p = twin.rom.predict(Ns, 288.15, 101325.0, thr)
    return jsonify(m=np.round(p['mdot'], 5).tolist(), PR=np.round(p['PR'], 5).tolist(), rpm=Ns.tolist())

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--port', default=None, help='serial port of the rig board, e.g. COM5 or /dev/ttyACM0 (hardware mode)')
    ap.add_argument('--http', type=int, default=5000); a = ap.parse_args()
    hw = None
    if a.port:
        import sys; sys.path.insert(0, os.path.join(HERE, '..', 'acquisition'))
        from hw_serial import SerialRig
        hw = SerialRig(a.port)
    rom_path = os.path.join(HERE, '..', '..', 'models', 'rom_v1', 'rom.json')   # produced by src/modelling/build_rom.py
    twin = Twin(rom_path, hw=hw)
    threading.Thread(target=twin.run_forever, daemon=True).start()
    print('Digital twin running:  http://127.0.0.1:%d   (%s mode)' % (a.http, 'hardware' if hw else 'simulation'))
    app.run(host='127.0.0.1', port=a.http, debug=False, threaded=True)
