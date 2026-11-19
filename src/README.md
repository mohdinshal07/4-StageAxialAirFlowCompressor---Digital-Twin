# src/

| Folder | Files | What they do |
|---|---|---|
| `modelling/` | `eng.py`, `blades.py`, `sec.py` | design geometry (mean-line design, blade rows, sections) |
| | `offdesign.py` | **full-order model**: mean-line stage stacking, loss bucket, valve, surge |
| | `gen_dataset.py` | 60-point dataset (45 train / 15 test), compressor map, surge line |
| | `build_rom.py`, `rom.py` | v1 polynomial surrogate in speed only |
| | `build_pod_rom.py`, `rom_eval.py` | **POD reduced-order model** (speed × valve), GP comparison, thermal OpInf ROM, observability |
| | `make_map_json.py` | compact map for the web dashboard |
| | `compressor_rpm_calculator.py` | change the rpm → full operating point and stage-by-stage table |
| `twin/` | `twin_core.py` | simulated rig, ROM prediction, PR controller (FF + PI), 10 Hz loop |
| | `app.py`, `static/index.html` | Flask dashboard (`python app.py`, add `--port COM5` for hardware) |
| | `run_closed_loop_test.py` | headless closed-loop test with a speed sag |
| `acquisition/` | `firmware/compressor_rig/compressor_rig.ino` | Arduino: PT100/MAX31865, LPS33HW, VESC speed, `D,…` lines out, `R,<rpm>` in |
| | `hw_serial.py` | USB-serial link used by the Python twin |
| | `mqtt_bridge.py`, `message_schema.json` | serial → MQTT bridge with JSON messages (seq, UTC time, quality); raw logging |
| `dashboard/` | `web/*.html, *.css, *.js`, `build_site.py` | the web twin: ROM-driven simulation, virtual rig + faults, KF/CUSUM, control, logging, exports |
| `analysis/` | `uq_mc.py`, `gum.py`, `twin_scenarios.py`, `make_figs.py`, `fig_arch.py`, `shot_dash.py` | uncertainty, sensor budget, virtual-rig scenarios, paper figures |

Run every script from the repository root (`python src/<folder>/<script>.py`). Paths are resolved relative to the repository.
