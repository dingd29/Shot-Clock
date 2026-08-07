.PHONY: install data clock validate backfill train score lineups synergy lineup-test ablate rulechange stopping rebound winprob situational twoforone endgame value ratings project scorecard test lint app clean

SEASON ?= 2024
FIRST  ?= 2015
LAST   ?= 2024
PY := .venv/bin/python

install:
	$(PY) -m pip install -e ".[models,app,dev]"

data:  ## download + cache one season of PBP and shot detail
	$(PY) -m possval.pipeline ingest --season $(SEASON)

clock:  ## reconstruct shot clock for one season
	$(PY) -m possval.pipeline clock --season $(SEASON)

validate:  ## reconstruction vs NBA's published aggregates (2024-25 only)
	$(PY) -m possval.pipeline validate --season 2024

backfill:  ## ingest + reconstruct every season in FIRST..LAST
	$(PY) -m possval.pipeline backfill --first $(FIRST) --last $(LAST)

train:  ## fit and evaluate the xPTS model
	$(PY) -m possval.pipeline train --first $(FIRST) --last $(LAST)

score:  ## score every shot and write the grade tables
	$(PY) -m possval.pipeline score --first $(FIRST) --last $(LAST)

lineups:  ## derive on-court lineups from substitutions
	$(PY) -m possval.pipeline lineups --first $(FIRST) --last $(LAST)

synergy:  ## creation overlap vs efficiency, team-season level (findings 11, first test)
	$(PY) -m possval.pipeline synergy --first $(FIRST) --last $(LAST)

lineup-test:  ## the same hypothesis retested on five-man lineups (findings 11, retest)
	$(PY) -m possval.pipeline lineup-test --first $(FIRST) --last $(LAST)

ablate:  ## value feature groups by refitting without them
	$(PY) -m possval.pipeline ablate --first $(FIRST) --last $(LAST)

rulechange:  ## the 2018-19 rule as a difference-in-differences
	$(PY) -m possval.pipeline rulechange --first $(FIRST) --last $(LAST)

stopping:  ## shooting as optimal stopping: continuation value and exercise boundary
	$(PY) -m possval.pipeline stopping --first $(FIRST) --last $(LAST)

rebound:  ## conditional rebound rates; re-price finding 7 with the rebound option
	$(PY) -m possval.pipeline rebound --first $(FIRST) --last $(LAST)

value:  ## the possession valuation curve, its calibration, and team deviation
	$(PY) -m possval.pipeline value --window $(or $(WINDOW),explore)

endgame:  ## post hoc: is there a sawtooth in end-of-period possession value?
	$(PY) -m possval.pipeline endgame --window $(or $(WINDOW),explore)

twoforone:  ## does the 2-for-1 pay? WINDOW=holdout is a one-shot confirmation
	$(PY) -m possval.pipeline twoforone --window $(or $(WINDOW),explore)

situational:  ## H4/H5 on the exploration window; WINDOW=holdout is a one-shot confirmation
	$(PY) -m possval.pipeline situational --window $(or $(WINDOW),explore)

scorecard:  ## score the pre-registered projection against results so far
	$(PY) -m possval.pipeline scorecard --season 2026

winprob:  ## does the shot clock improve a live win-probability model?
	$(PY) -m possval.pipeline winprob --first $(FIRST) --last $(LAST)

ratings:  ## season SRS for every team; required by project and scorecard
	$(PY) -m possval.pipeline ratings --first $(FIRST) --last 2025

project:  ## calibrate DPM and simulate 2026-27 for all thirty teams (needs: ratings)
	$(PY) -m possval.pipeline project --games 70

test:
	$(PY) -m pytest tests/ -q

lint:
	.venv/bin/ruff check src app tests

app:
	.venv/bin/streamlit run app/dashboard.py

clean:  ## drop regenerable artifacts, keep raw downloads
	rm -rf data/processed
