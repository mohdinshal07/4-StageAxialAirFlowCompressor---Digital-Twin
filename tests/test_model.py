"""Checks of the physics model, the dataset and the reduced-order models (all data simulated)."""
import os, json, numpy as np, pandas as pd, pytest
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
P = lambda *a: os.path.join(REPO, *a)


def test_full_order_model_reproduces_design_point():
    import offdesign as od
    op = od.Compressor('B').operating_point(20000.0)
    assert op['PR'] == pytest.approx(1.12, abs=2e-4)
    assert op['T0'] == pytest.approx(301.77, abs=0.02)
    assert op['m'] == pytest.approx(0.2082, abs=5e-4)


def test_rpm_calculator_matches_dataset():
    import compressor_rpm_calculator as cc
    df = pd.read_csv(P('data', 'processed', 'Compressor_4stage_dataset.csv'))
    for _, row in df.sample(8, random_state=0).iterrows():
        r = cc.calculate(float(row['rpm']))
        assert r['PR'] == pytest.approx(row['PR'], abs=2e-6)
        assert r['T_out_C'] == pytest.approx(row['T_out_C'], abs=1e-4)
        assert r['mdot_kg_s'] == pytest.approx(row['mdot_kg_s'], abs=1e-5)


def test_pod_rom_on_held_out_points():
    import rom_eval
    te = pd.read_csv(P('models', 'pod_rom', 'doe_test_15.csv'))
    err_pr = [abs(rom_eval.predict(r.N, r.phi)['PR'] - r.PR) for r in te.itertuples()]
    err_t = [abs(rom_eval.predict(r.N, r.phi)['T_out'] - r.T_out) for r in te.itertuples()]
    assert max(err_pr) < 1e-3 and max(err_t) < 0.05


def test_pod_rom_basis_size_and_energy():
    R = json.load(open(P('models', 'pod_rom', 'rom_pod.json')))
    assert R['r'] == 4 and R['energy'][3] > 0.99999


def test_rom_v1_surrogate():
    from rom import ROM
    m = json.load(open(P('models', 'rom_v1', 'rom_metrics.json')))
    assert ROM() is not None and isinstance(m, dict)


def test_twin_holds_pressure_ratio_through_speed_sag():
    from twin_core import Twin
    tw = Twin(None); tw.set(mode='AUTO', PR_set=1.10, sag=0.0, running=True)
    for k in range(600):
        if k == 300: tw.set(sag=0.10)
        tw.step()
    assert tw.last['PR_meas'] == pytest.approx(1.10, abs=2e-3)


def test_bridge_parser():
    from mqtt_bridge import parse_line, quality
    v = parse_line('D,25.10,101300,38.40,112900,15020')
    assert v['N_rpm'] == 15020 and quality(v) == 'ok'
    assert parse_line('# sensor not found') is None
