from __future__ import annotations

from functools import lru_cache

import pandas as pd
from requests import RequestException

from .nba_stats import (
    GENERAL_RANGES,
    SHOT_CLOCK_RANGES,
    NBAStatsError,
    fetch_shot_clock_breakdown,
)


DEFAULT_SEASON = "2024-25"
DEFAULT_SEASON_TYPE = "Regular Season"


@lru_cache(maxsize=None)
def load_shot_clock_data(
    season: str = DEFAULT_SEASON,
    season_type: str = DEFAULT_SEASON_TYPE,
) -> pd.DataFrame:
    """Download shot-clock dashboard data for the Philadelphia 76ers.

    Parameters
    ----------
    season:
        Season identifier understood by the NBA stats service (e.g. ``"2024-25"``).
    season_type:
        Season type value accepted by the service (e.g. ``"Regular Season"``).
    """

    try:
        return fetch_shot_clock_breakdown(
            season=season,
            season_type=season_type,
            general_ranges=GENERAL_RANGES,
            shot_clock_ranges=SHOT_CLOCK_RANGES,
        )
    except (RequestException, NBAStatsError) as exc:
        raise RuntimeError(
            "Unable to download 76ers shot-clock data from stats.nba.com. "
            "Verify that the network allows access to https://stats.nba.com/stats/"
        ) from exc
