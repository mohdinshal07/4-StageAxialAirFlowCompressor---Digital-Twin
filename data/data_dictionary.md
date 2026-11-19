# Data dictionary

**Source flag:** every file below is **SIMULATED** unless it sits in `data/raw/` and its name starts with `measured_`.
Inlet reference state: T₀₁ = 288.15 K (15 °C), P₀₁ = 101.325 kPa, unless a column gives another inlet state.
All pressures are absolute. "Total" means stagnation.

## data/processed/

### Compressor_4stage_dataset.csv (60 rows), train_45_points.csv, test_15_points.csv
Valve fully open (φ = 1). Speeds come from a seeded random draw over 10,000–20,000 rpm (seed 2026): 45 training rows and 15 test rows.
Produced by `src/modelling/gen_dataset.py` (full-order model).

| Column | Unit | Meaning |
|---|---|---|
| point | – | ID: TRnn = training, TEnn = test |
| set | – | train / test (combined file only) |
| rpm | rev/min | shaft speed |
| T_amb_C | °C | inlet (ambient) total temperature |
| P_amb_kPa | kPa | inlet (ambient) total pressure |
| PR | – | total-to-total pressure ratio P₀,out/P₀₁ |
| T_out_C, T_out_K | °C, K | outlet total temperature |
| P_out_kPa | kPa | outlet total pressure |
| p_out_static_kPa | kPa | outlet static pressure |
| mdot_kg_s | kg/s | mass flow rate |
| power_air_W | W | power absorbed by the air, ṁ c_p ΔT₀ |
| power_shaft_W | W | shaft power = power_air / 0.97 (mechanical efficiency) |
| torque_Nm | N·m | shaft torque = power_shaft / ω |
| eta_isentropic | – | total-to-total isentropic efficiency |
| surge_margin | – | (PR_s/PR)(ṁ/ṁ_s) − 1 at the same speed |

### compressor_map_speedlines.csv (234 rows)
Speed lines from 8,000 to 22,000 rpm.

| Column | Unit | Meaning |
|---|---|---|
| rpm | rev/min | speed line |
| mdot_kg_s | kg/s | mass flow |
| PR | – | total pressure ratio |
| T_ratio | – | T₀,out/T₀₁ |
| eta_isentropic | – | isentropic efficiency |
| stable | 0/1 | 1 = right of the surge point (stable) |

### surge_line.csv (8 rows)
Columns: rpm, surge_mdot_kg_s (kg/s), surge_PR (–). Surge is the speed-line peak or the point where the rotor diffusion factor reaches 0.6, whichever has the higher flow.

### twin_closed_loop_test.csv (1,500 rows, 10 Hz)
Python twin in AUTO mode on the simulated rig: set-point changes and a 10 % speed sag. Produced by `src/twin/run_closed_loop_test.py`.

| Column | Unit | Meaning |
|---|---|---|
| t | s | time |
| PR_set | – | pressure-ratio set point |
| PR | – | "measured" PR from the simulated rig (noise added) |
| PR_rom | – | PR predicted by the ROM |
| rpm, rpm_cmd | rev/min | actual and commanded speed |
| T_out | °C | outlet total temperature |
| P_out | kPa | outlet total pressure |
| T_amb | °C | inlet temperature |
| sag | – | injected speed sag (fraction) |

### analysis/*.json
- `uq_mc.json`: Monte Carlo model uncertainty. 64 Latin-hypercube samples of η_s ∈ [0.65, 0.75], Δβ₂ ∈ [−1°, 1°] and i₊ ∈ [5°, 9°], at 10k, 15k and 20k rpm. Contains the mean, 2.5 % and 97.5 % values per output, and standardized regression coefficients (`src`).
- `gum.json`: GUM measurement-uncertainty budget. Case A: sensors as delivered. Case B: zero-speed cross-calibration plus a Kiel probe.
- `twin_scenarios.json`: virtual-rig runs of the web twin. s1 = erosion fault, s2 = PR control with speed sag, s3 = 35 °C inlet day. `timing` holds the computation times.

## models/pod_rom/

| File | Content |
|---|---|
| rom_pod.json | POD reduced-order model: snapshot layout (44 values: Π, Θ, Ψ, Mₐ at 9 stations + rotor incidence and DF), means, group scales, basis V (r = 4), polynomial amplitude maps, scalar maps (corrected flow, SM), the thermal operator-inference ROM (A_r, N_r, b_r), metrics and observability |
| doe_train_45.csv / doe_test_15.csv | Latin-hypercube DOE over N (10–20k rpm) and φ (0.94–1.50). Columns: N [rpm], phi [–], x = corrected speed fraction, PR, TR, T_out [K], P_out [Pa], m [kg/s], eta, power [W], SM, stable, DFmax, mx = corrected flow / x, set |
| test_comparison.csv | full-order model (FOM) vs ROM on the 15 test points |
| model_order_sweep.csv | r, energy, basis error, ROM error, max PR and T_out error against the number of modes |
| map.json | compact compressor map for the web dashboard |
| snapshots_train.npy | the 44 × 45 training snapshot matrix |

## models/rom_v1/
1-D polynomial surrogate in speed only (valve fully open). `rom.json` holds the coefficients, `rom_metrics.json` the train/test metrics, and `test_points_comparison.csv` the test-point errors.

## data/raw/ (measured, once available)
Lines as received from the board: `D,<T_amb_C>,<P_amb_Pa>,<T_out_C>,<p_out_static_Pa>,<rpm>`, preceded by the UTC receive time.
The MQTT message format is defined in `src/acquisition/message_schema.json`.
