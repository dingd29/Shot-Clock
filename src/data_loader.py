from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "76ers_shotclock.csv"


@lru_cache(maxsize=1)
def load_shot_clock_data() -> pd.DataFrame:
    """Load the shot-clock dataset with some handy derived metrics."""
    df = pd.read_csv(DATA_PATH)
    df["points_per_possession"] = df["points"] / df["possessions"]
    df["effective_fg_pct"] = (
        (df["fgm"] + 0.5 * df["threes_made"]) / df["fga"]
    ).round(3)
    df["assist_pct"] = (df["assists"] / df["fgm"]).round(3)
    df["turnover_rate"] = (df["turnovers"] / df["possessions"]).round(3)
    df["free_throw_rate"] = (df["free_throw_trips"] / df["possessions"]).round(3)
    return df
