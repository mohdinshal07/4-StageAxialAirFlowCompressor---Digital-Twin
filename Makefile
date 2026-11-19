PY ?= python3
.PHONY: all data rom site twin analysis figures test calc clean
all:      ; bash run_all.sh
data:     ; $(PY) src/modelling/gen_dataset.py && $(PY) src/modelling/make_map_json.py
rom:      ; $(PY) src/modelling/build_rom.py && $(PY) src/modelling/build_pod_rom.py
site:     ; $(PY) src/dashboard/build_site.py
twin:     ; $(PY) src/twin/app.py
analysis: ; $(PY) src/analysis/uq_mc.py && $(PY) src/analysis/gum.py && $(PY) src/analysis/twin_scenarios.py
figures:  ; $(PY) src/analysis/make_figs.py && $(PY) src/analysis/fig_arch.py
test:     ; $(PY) -m pytest -q tests
calc:     ; $(PY) src/modelling/compressor_rpm_calculator.py $(RPM)
clean:    ; rm -rf src/dashboard/dist **/__pycache__ .pytest_cache
