# Common commands. Run from the repo root. Needs Python 3.11+ and make.
# On Windows without make, copy the command after each target into a terminal.

PYTHON ?= python3
VENV = .venv
PY = $(VENV)/bin/python
SCENARIO ?= scenarios/bearing_wear_p2_02.json

.PHONY: help setup test validate demo healthy run dashboard clean

help:
	@echo "make setup      create .venv and install requirements"
	@echo "make test       run every test (stubs show as skipped)"
	@echo "make validate   check config, scenarios and fixtures against schemas/"
	@echo "make demo       run the bearing-wear scenario end to end"
	@echo "make healthy    run the healthy (false-positive) scenario"
	@echo "make run SCENARIO=scenarios/x.json   run any scenario"
	@echo "make dashboard  serve the repo at http://localhost:8000/dashboard/"
	@echo "make clean      delete runs/ and caches"

setup:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

test:
	$(PY) -m unittest discover -s tests -t .

validate:
	$(PY) schemas/validate.py

demo:
	$(PY) run_scenario.py scenarios/bearing_wear_p2_02.json

healthy:
	$(PY) run_scenario.py scenarios/healthy_baseline.json

run:
	$(PY) run_scenario.py $(SCENARIO)

dashboard:
	@echo "Open http://localhost:8000/dashboard/  (Ctrl+C to stop)"
	$(PYTHON) -m http.server 8000 --bind 127.0.0.1

clean:
	rm -rf runs
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
