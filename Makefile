# Every target is a thin alias over the Python CLI (`python -m cotraffic ...`), so the
# same commands work on Windows without make. See README for the full list of options.

PY ?= python
AGENT ?= coop
NET ?= grid4x4
SEED ?= 1
EXP ?= full_matrix
JOBS ?= 2
ARGS ?=

.PHONY: help setup test lint smoke networks calibrate baselines train select evaluate \
        aggregate figures tables forecast explain dashboard demo reproduce clean

help:
	@echo "setup      install pinned dependencies and the package (editable)"
	@echo "test       unit and integration tests"
	@echo "lint       ruff"
	@echo "smoke      quick end-to-end run of every feature (minutes)"
	@echo "networks   build all SUMO networks from configs/networks"
	@echo "calibrate  estimate reward normalisation constants from baseline runs"
	@echo "baselines  evaluate FT/ACT/MP/EV-RULE for experiment EXP"
	@echo "train      train one variant: make train AGENT=coop NET=grid4x4 SEED=1"
	@echo "select     pick the best checkpoint of every run on validation seeds"
	@echo "evaluate   run experiment EXP (all methods) with JOBS processes"
	@echo "aggregate  statistics and summary tables from results/raw"
	@echo "figures    report figures into figures/"
	@echo "tables     results/summary/REPORT_TABLES.md"
	@echo "dashboard  Streamlit dashboard (reads result files only)"
	@echo "reproduce  networks -> baselines -> evaluation -> statistics -> figures -> tables"

setup:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e . --no-deps

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests scripts dashboard
	$(PY) -m ruff format --check src tests scripts dashboard

smoke:
	$(PY) -m cotraffic smoke $(ARGS)

networks:
	$(PY) -m cotraffic networks --all $(ARGS)

calibrate:
	$(PY) -m cotraffic calibrate --net $(NET) $(ARGS)

baselines:
	$(PY) -m cotraffic evaluate --experiment $(EXP) --methods baselines --jobs $(JOBS) $(ARGS)

train:
	$(PY) -m cotraffic train --agent $(AGENT) --net $(NET) --seed $(SEED) $(ARGS)

select:
	$(PY) -m cotraffic select --net $(NET) $(ARGS)

evaluate:
	$(PY) -m cotraffic evaluate --experiment $(EXP) --jobs $(JOBS) $(ARGS)

aggregate:
	$(PY) -m cotraffic aggregate $(ARGS)

figures:
	$(PY) -m cotraffic figures $(ARGS)

tables:
	$(PY) -m cotraffic tables $(ARGS)

forecast:
	$(PY) -m cotraffic forecast $(ARGS)

explain:
	$(PY) -m cotraffic explain $(ARGS)

dashboard:
	$(PY) -m streamlit run dashboard/app.py

demo:
	$(PY) scripts/demo_side_by_side.py $(ARGS)

reproduce:
	bash scripts/reproduce_all.sh

clean:
	$(PY) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('results/tmp', 'sumo_files/routes', 'sumo_files/tmp')]"
