#!/usr/bin/env bash
# Rebuild the whole project from the physics model up. All outputs are SIMULATED.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
echo "== 1 dataset";            $PY src/modelling/gen_dataset.py > /dev/null
echo "== 2 dashboard map";      $PY src/modelling/make_map_json.py
echo "== 3 ROM v1 (speed)";     $PY src/modelling/build_rom.py > /dev/null
echo "== 4 POD ROM";            $PY src/modelling/build_pod_rom.py | tail -1
echo "== 5 web twin";           $PY src/dashboard/build_site.py
echo "== 6 twin closed loop";   $PY src/twin/run_closed_loop_test.py | tail -1
echo "== 7 uncertainty";        $PY src/analysis/uq_mc.py > /dev/null; $PY src/analysis/gum.py > /dev/null
if $PY -c "import playwright" 2>/dev/null; then
  echo "== 8 virtual-rig scenarios"; $PY src/analysis/twin_scenarios.py > /dev/null
else
  echo "== 8 skipped (pip install playwright && playwright install chromium)"
fi
echo "== 9 figures";            $PY src/analysis/make_figs.py > /dev/null; $PY src/analysis/fig_arch.py > /dev/null
if $PY -c "import playwright" 2>/dev/null; then $PY src/analysis/shot_dash.py > /dev/null; rm -f figures/paper/_*.png; fi
echo "== 10 tests";             $PY -m pytest -q tests
