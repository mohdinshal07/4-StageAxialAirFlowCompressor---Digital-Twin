# data/raw

Raw rig logs go here **unchanged** (one file per session, written by `src/acquisition/mqtt_bridge.py` as
`session_YYYYMMDD_HHMMSS.csv`, or saved from the dashboard's CSV export).

**Status (19 Nov 2026): empty.** The rig is under construction, so no measured data exist yet.
Everything in `data/processed/` is **simulated** by the physics model.

Rules
- Never edit a raw file. Corrections and filtering go into `data/processed/` with a script.
- Keep the quality flag and sequence number beside every value.
- Name measured files `measured_*` and simulated files `simulated_*` so they can never be confused.

Example raw line from the board (10 Hz):
```
D,25.10,101300,38.40,112900,15020      # T_amb [C], P_amb [Pa], T_out [C], p_out_static [Pa], speed [rpm]
```
