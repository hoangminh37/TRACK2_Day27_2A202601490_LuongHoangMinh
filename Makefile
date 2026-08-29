VENV_BIN := .venv/bin
PYTHON ?= $(shell if [ -f $(VENV_BIN)/python ]; then echo $(VENV_BIN)/python; elif command -v python3 >/dev/null 2>&1; then echo python3; else echo python; fi)
DBT ?= $(shell if [ -f $(VENV_BIN)/dbt ]; then echo $(VENV_BIN)/dbt; elif command -v dbt >/dev/null 2>&1; then echo dbt; else echo $(PYTHON) -m dbt.cli.main; fi)
STREAMLIT ?= $(shell if [ -f $(VENV_BIN)/streamlit ]; then echo $(VENV_BIN)/streamlit; elif command -v streamlit >/dev/null 2>&1; then echo streamlit; else echo $(PYTHON) -m streamlit; fi)

.PHONY: reset baseline tests gx dbt dashboard generate

reset:
	$(PYTHON) scripts/reset_lab.py

baseline:
	$(PYTHON) scripts/run_baseline.py

tests:
	$(PYTHON) -m pytest tests_public -v

gx:
	$(PYTHON) gx/validate_orders.py

dbt:
	$(PYTHON) scripts/sync_dbt_seeds.py
	$(DBT) build --project-dir dbt_project --profiles-dir dbt_project

dashboard:
	$(STREAMLIT) run dashboard/app.py

generate:
	$(PYTHON) scripts/generate_data.py --rows 600 --days 42 --seed 27
