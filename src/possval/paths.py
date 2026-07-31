"""Canonical filesystem locations. Everything under data/ except reference/ is regenerable."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
REFERENCE = DATA / "reference"

REPORTS = ROOT / "reports"
NOTEBOOKS = ROOT / "notebooks"

DUCKDB_PATH = PROCESSED / "nba.duckdb"

# NBA's official published shot-clock aggregates for 2024-25, scraped Nov 2025.
# This is the ground-truth validation set for the reconstruction, not an app data source.
OFFICIAL_SHOTCLOCK_2024_25 = REFERENCE / "official_shotclock_2024_25.csv"


def ensure_dirs() -> None:
    for d in (RAW, PROCESSED, REFERENCE, REPORTS):
        d.mkdir(parents=True, exist_ok=True)
