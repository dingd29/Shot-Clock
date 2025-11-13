from __future__ import annotations

from typing import List, Mapping, MutableMapping, Sequence

import pandas as pd
import requests


class NBAStatsError(RuntimeError):
    """Raised when the NBA stats service returns an unexpected payload."""


SHOT_CLOCK_RANGES: Sequence[str] = (
    "24-22",
    "22-18 Very Early",
    "18-15 Early",
    "15-7 Average",
    "7-4 Late",
    "4-0 Very Late",
)

GENERAL_RANGES: Sequence[str] = (
    "Overall",
    "Catch and Shoot",
    "Pullups",
    "Less Than 10 ft",
)

BASE_URL = "https://stats.nba.com/stats/leaguedashteamptshot"
TEAM_ID = 1610612755

DEFAULT_HEADERS: Mapping[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/stats/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Accept-Language": "en-US,en;q=0.9",
}


NUMERIC_COLUMNS: Sequence[str] = (
    "FGA_FREQUENCY",
    "FGM",
    "FGA",
    "FG_PCT",
    "EFG_PCT",
    "FG2A_FREQUENCY",
    "FG2M",
    "FG2A",
    "FG2_PCT",
    "FG3A_FREQUENCY",
    "FG3M",
    "FG3A",
    "FG3_PCT",
)


def safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Vectorised safe division that returns NaN on division-by-zero."""
    result = numerator.div(denominator)
    result = result.replace([pd.NA, float("inf"), -float("inf")], pd.NA)
    return result


def _request_params(
    season: str,
    season_type: str,
    general_range: str,
    shot_clock_range: str,
) -> MutableMapping[str, str]:
    params: MutableMapping[str, str] = {
        "Season": season,
        "SeasonType": season_type,
        "PerMode": "Totals",
        "MeasureType": "Base",
        "PaceAdjust": "N",
        "PlusMinus": "N",
        "Rank": "N",
        "Outcome": "",
        "Location": "",
        "Month": "0",
        "SeasonSegment": "",
        "DateFrom": "",
        "DateTo": "",
        "OpponentTeamID": "0",
        "VsConference": "",
        "VsDivision": "",
        "GameSegment": "",
        "LastNGames": "0",
        "Period": "0",
        "ShotClockRange": shot_clock_range,
        "ShotDistRange": "",
        "TouchTimeRange": "",
        "DribbleRange": "",
        "CloseDefDistRange": "",
        "PlayerExperience": "",
        "PlayerPosition": "",
        "StarterBench": "",
        "TeamID": str(TEAM_ID),
        "GameScope": "",
        "GeneralRange": general_range,
    }
    return params


def _extract_rows(payload: Mapping[str, object]) -> pd.DataFrame:
    try:
        result_sets = payload["resultSets"]
    except KeyError as err:
        raise NBAStatsError("Unexpected response shape: missing 'resultSets'.") from err
    if not result_sets:
        raise NBAStatsError("NBA stats response did not include any result sets.")
    dataset = result_sets[0]
    if "rowSet" not in dataset or "headers" not in dataset:
        raise NBAStatsError("Unexpected response shape in NBA stats dataset.")
    return pd.DataFrame(dataset["rowSet"], columns=dataset["headers"])


def fetch_shot_clock_breakdown(
    season: str,
    season_type: str = "Regular Season",
    general_ranges: Sequence[str] = GENERAL_RANGES,
    shot_clock_ranges: Sequence[str] = SHOT_CLOCK_RANGES,
    timeout: float = 30.0,
) -> pd.DataFrame:
    """Fetch shot-clock statistics for the 76ers from stats.nba.com.

    Parameters
    ----------
    season:
        Target season in the NBA Stats format (e.g. ``"2024-25"``).
    season_type:
        Season type, typically ``"Regular Season"``.
    general_ranges:
        Iterable of general shooting ranges to request.
    shot_clock_ranges:
        Iterable of shot-clock buckets to request.
    timeout:
        Timeout (in seconds) for each HTTP request.
    """

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    frames: List[pd.DataFrame] = []

    for general_range in general_ranges:
        for shot_clock_range in shot_clock_ranges:
            params = _request_params(season, season_type, general_range, shot_clock_range)
            response = session.get(BASE_URL, params=params, timeout=timeout)
            response.raise_for_status()
            frame = _extract_rows(response.json())
            frame = frame[frame["TEAM_ID"] == TEAM_ID]
            if frame.empty:
                continue
            frame = frame.copy()
            frame["ShotClockRange"] = shot_clock_range
            frame["GeneralRange"] = general_range
            frames.append(frame)

    if not frames:
        raise NBAStatsError(
            "NBA stats endpoint returned no rows for the requested filters."
        )

    combined = pd.concat(frames, ignore_index=True)
    return _prepare_dataframe(combined, season, season_type)


def _prepare_dataframe(df: pd.DataFrame, season: str, season_type: str) -> pd.DataFrame:
    rename_map = {
        "TEAM_ID": "team_id",
        "TEAM_NAME": "team_name",
        "TEAM_ABBREVIATION": "team_abbreviation",
        "GP": "games_played",
        "G": "games",
        "FGA_FREQUENCY": "fga_frequency",
        "FGM": "fgm",
        "FGA": "fga",
        "FG_PCT": "fg_pct",
        "EFG_PCT": "efg_pct",
        "FG2A_FREQUENCY": "fg2a_frequency",
        "FG2M": "fg2m",
        "FG2A": "fg2a",
        "FG2_PCT": "fg2_pct",
        "FG3A_FREQUENCY": "fg3a_frequency",
        "FG3M": "fg3m",
        "FG3A": "fg3a",
        "FG3_PCT": "fg3_pct",
        "ShotClockRange": "shot_clock_range",
        "GeneralRange": "general_range",
    }

    df = df.rename(columns=rename_map)

    numeric_cols = [rename_map[col] for col in NUMERIC_COLUMNS]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

    # Normalise frequency columns to fraction if necessary.
    for column in ("fga_frequency", "fg2a_frequency", "fg3a_frequency"):
        max_value = df[column].max()
        if pd.notna(max_value) and max_value > 1:
            df[column] = df[column] / 100.0

    df["points"] = df["fg2m"] * 2 + df["fg3m"] * 3
    df["points_per_shot"] = safe_div(df["points"], df["fga"])
    df["fg3_rate"] = safe_div(df["fg3a"], df["fga"])

    df["season"] = season
    df["season_type"] = season_type

    desired_columns = [
        "team_id",
        "team_name",
        "team_abbreviation",
        "season",
        "season_type",
        "shot_clock_range",
        "general_range",
        "games_played",
        "games",
        "fgm",
        "fga",
        "fg_pct",
        "efg_pct",
        "fg2m",
        "fg2a",
        "fg2_pct",
        "fg2a_frequency",
        "fg3m",
        "fg3a",
        "fg3_pct",
        "fg3a_frequency",
        "fga_frequency",
        "points",
        "points_per_shot",
        "fg3_rate",
    ]

    return df[desired_columns]
