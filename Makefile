# Common commands. Run from the repo root. Needs Python 3.11+ and make.
# On Windows without make, copy the command after each target into a terminal.

PYTHON ?= python3
VENV = .venv
PY = $(VENV)/bin/python
SCENARIO ?= scenarios/bearing_wear_p2_02.json

.PHONY: help setup test test-fast validate generate detect site-data demo healthy run dashboard clean

help:
	@echo "make setup      create .venv and install requirements"
	@echo "make test       run every test, ~2 min (stubs show as skipped)"
	@echo "make test-fast  skip the whole-scenario runs, ~10 s"
	@echo "make validate   check config, scenarios and fixtures against schemas/"
	@echo "make generate   simulate telemetry only (SCENARIO=..., default bearing wear)"
	@echo "make detect     simulate + Missions 1-4 + scoring, open loop (SCENARIO=...)"
	@echo "make site-data  regenerate the website demo data (site/demo/generated/)"
	@echo "make demo       run the bearing-wear scenario end to end"
	@echo "make healthy    run the healthy (false-positive) scenario"
	@echo "make run SCENARIO=scenarios/x.json   run any scenario"
	@echo "make dashboard  dashboard + website at http://localhost:8000 (generate runs from the Scenarios button)"
	@echo "make clean      delete runs/ and caches"

setup:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

test:
	$(PY) -m unittest discover -s tests -t .

test-fast:
	P4_FAST=1 $(PY) -m unittest discover -s tests -t .

validate:
	$(PY) schemas/validate.py

generate:
	$(PY) -m p4maint.generator $(SCENARIO)

detect:
	$(PY) -m p4maint.openloop $(SCENARIO)

site-data:
	@# Each fault run is shown a few minutes after its first predictive warning, at a moment its
	@# readings are visibly WARNING; healthy at the end. Re-check the times if the model changes.
	$(PY) -m p4maint.openloop scenarios/healthy_baseline.json --dashboard-out site/demo/generated/healthy_baseline
	$(PY) -m p4maint.openloop scenarios/bearing_wear_p2_02.json --dashboard-out site/demo/generated/bearing_wear_p2_02 --dashboard-at 10679
	$(PY) -m p4maint.openloop scenarios/wheel_drag_p2_01.json --dashboard-out site/demo/generated/wheel_drag_p2_01 --dashboard-at 9899
	$(PY) -m p4maint.openloop scenarios/cooling_fault_p2_03.json --dashboard-out site/demo/generated/cooling_fault_p2_03 --dashboard-at 7679
	$(PY) -m p4maint.openloop scenarios/battery_degradation_p2_02.json --dashboard-out site/demo/generated/battery_degradation_p2_02 --dashboard-at 9779
	$(PY) schemas/validate.py

demo:
	$(PY) run_scenario.py scenarios/bearing_wear_p2_02.json

healthy:
	$(PY) run_scenario.py scenarios/healthy_baseline.json

run:
	$(PY) run_scenario.py $(SCENARIO)

dashboard:
	$(PY) -m p4maint.server --port 8000

clean:
	rm -rf runs
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
