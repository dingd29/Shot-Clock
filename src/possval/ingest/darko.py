"""DARKO player-impact projections.

Layer 1 of the projection system. DARKO (Kostya Medvedovsky) publishes a daily-updated
Kalman-filtered estimate of current player value, split into offensive and defensive
components, free via a public Google Sheet.

Bootstrapping from DARKO rather than fitting our own RAPM is deliberate: RAPM is a solved
problem and the largest time sink available, while the original contribution here lives in
the possession-level layer. DPM is treated as an input to be stress-tested, not as truth —
`aging.py` fits independent aging curves precisely because DARKO's own aging prior is the
piece most likely to mislead at the extreme (LeBron plays 2026-27 at 41/42).

EPM (Dunks & Threes) was the alternative and is paywalled. BPM (Basketball-Reference) and
nbarapm.com are free cross-checks.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

SHEET_ID = "1mhwOLqPu2F9026EQiVxFPIN1t9RGafGpl-dokaIsm9c"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

COLUMN_MAP = {
    "NBA ID": "PLAYER_ID",
    "Player Name": "PLAYER_NAME",
    "Position": "POSITION",
    "Age": "AGE",
    "DPM": "DPM",
    "Offensive DPM": "O_DPM",
    "Defensive DPM": "D_DPM",
    "Box Only O-DPM": "BOX_O_DPM",
    "Box Only D-DPM": "BOX_D_DPM",
    "On Off O-DPM": "ONOFF_O_DPM",
    "On Off D-DPM": "ONOFF_D_DPM",
}


def fetch_darko(cache: Path | None = None, refresh: bool = False) -> pd.DataFrame:
    """Download current DARKO DPM. Cached to disk so a run is reproducible after the fact.

    `pandas.read_csv(url)` fails here on macOS with a certificate error because it goes
    through urllib; requests carries certifi, so the fetch goes through requests.
    """
    if cache is not None and cache.exists() and not refresh:
        return pd.read_csv(cache)

    response = requests.get(SHEET_URL, timeout=120)
    response.raise_for_status()
    df = pd.read_csv(io.BytesIO(response.content))

    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(f"DARKO sheet is missing expected columns: {missing}")

    df = df.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())]
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache, index=False)
    return df


def roster_dpm(darko: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """DPM rows for a named roster, in descending order of overall impact."""
    matched = darko[darko.PLAYER_NAME.isin(names)].copy()
    found = set(matched.PLAYER_NAME)
    for name in names:
        if name not in found:
            matched = pd.concat(
                [matched, pd.DataFrame([{"PLAYER_NAME": name, "DPM": float("nan")}])],
                ignore_index=True,
            )
    return matched.sort_values("DPM", ascending=False, na_position="last").reset_index(drop=True)


def league_percentiles(darko: pd.DataFrame) -> pd.Series:
    return darko.DPM.quantile([0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
