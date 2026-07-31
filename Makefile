.PHONY: install data clock validate test lint app clean

SEASON ?= 2024
PY := .venv/bin/python

install:
	$(PY) -m pip install -e ".[models,app,dev]"

data:  ## download + cache one season of PBP and shot detail
	$(PY) -m possval.pipeline ingest --season $(SEASON)

clock:  ## reconstruct shot clock for one season
	$(PY) -m possval.pipeline clock --season $(SEASON)

validate:  ## reconstruction vs NBA's published aggregates (2024-25 only)
	$(PY) -m possval.pipeline validate --season 2024

test:
	$(PY) -m pytest tests/ -q

lint:
	.venv/bin/ruff check src tests

app:
	.venv/bin/streamlit run app/dashboard.py

clean:  ## drop regenerable artifacts, keep raw downloads
	rm -rf data/processed
