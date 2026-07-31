"""Shot-level feature construction for the expected-points (xPTS) model.

Design rule that governs everything here: **no leakage across time.** Shooter-skill priors
are the obvious trap — a player's 2024-25 three-point rate cannot be a feature for his
2024-25 shots. Priors are therefore built from strictly prior seasons via an as-of join, and
players with no history fall back to the league mean for their zone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Court geometry, in the tenths-of-a-foot units stats.nba.com uses for LOC_X / LOC_Y.
HOOP_Y = 0.0
RIM_ZONES = ("Restricted Area",)

CATEGORICAL = [
    "SHOT_ZONE_BASIC",
    "SHOT_ZONE_AREA",
    "SHOT_ZONE_RANGE",
    "ACTION_TYPE",
    "CHANCE_START_TYPE",
]

NUMERIC = [
    "SHOT_DISTANCE",
    "LOC_X",
    "LOC_Y",
    "SHOT_ANGLE",
    "SHOT_CLOCK",
    "CLOCK_ELAPSED",
    "PERIOD",
    "GAME_SECONDS_REMAINING",
    "IS_CLUTCH",
    "IS_HOME",
    "SCORE_MARGIN",
    "IS_3",
    "PRIOR_ZONE_FG_PCT",
    "PRIOR_FGA",
]


def _shot_angle(df: pd.DataFrame) -> pd.Series:
    """Angle from the centre of the rim, 0 = straight on, 90 = along the baseline."""
    return np.degrees(np.arctan2(df.LOC_X.abs(), np.maximum(df.LOC_Y - HOOP_Y, 1e-6)))


def _game_seconds_remaining(df: pd.DataFrame) -> pd.Series:
    """Seconds left in the game, counting overtime periods as 5 minutes."""
    in_period = df.MINUTES_REMAINING * 60 + df.SECONDS_REMAINING
    periods_left = np.maximum(4 - df.PERIOD, 0)
    return in_period + periods_left * 720


def add_target(df: pd.DataFrame) -> pd.DataFrame:
    """Points produced by the attempt itself: 0, 2 or 3.

    And-1 free throws are deliberately excluded — this model predicts the value of the field
    goal, and folding in FT points would conflate shot quality with foul-drawing. Foul-drawing
    is modelled separately at possession level.
    """
    df = df.copy()
    df["IS_3"] = df.SHOT_TYPE.astype(str).str.startswith("3").astype(int)
    df["PTS"] = df.SHOT_MADE_FLAG * (2 + df.IS_3)
    return df


def build_shooter_priors(shots: pd.DataFrame) -> pd.DataFrame:
    """Per (player, season, zone) shooting rates, shifted so they only describe the past.

    Returns one row per (PLAYER_ID, SEASON, SHOT_ZONE_BASIC) holding the player's cumulative
    rate over all *earlier* seasons — safe to join onto that season's shots.
    """
    grouped = (
        shots.groupby(["PLAYER_ID", "SEASON", "SHOT_ZONE_BASIC"], observed=True)
        .agg(FGM=("SHOT_MADE_FLAG", "sum"), FGA=("SHOT_MADE_FLAG", "size"))
        .reset_index()
        .sort_values(["PLAYER_ID", "SHOT_ZONE_BASIC", "SEASON"])
    )

    by_player_zone = grouped.groupby(["PLAYER_ID", "SHOT_ZONE_BASIC"], observed=True)
    # cumsum then shift: the value on season N covers seasons < N only.
    grouped["PRIOR_FGM"] = by_player_zone.FGM.cumsum() - grouped.FGM
    grouped["PRIOR_FGA"] = by_player_zone.FGA.cumsum() - grouped.FGA

    # Empirical-Bayes shrinkage toward the zone's league rate. Without this, a player with
    # three career attempts in a zone would carry a 0% or 100% prior.
    league = shots.groupby("SHOT_ZONE_BASIC", observed=True).SHOT_MADE_FLAG.mean()
    prior_strength = 50.0
    zone_mean = grouped.SHOT_ZONE_BASIC.map(league)
    grouped["PRIOR_ZONE_FG_PCT"] = (
        grouped.PRIOR_FGM + prior_strength * zone_mean
    ) / (grouped.PRIOR_FGA + prior_strength)

    return grouped[
        ["PLAYER_ID", "SEASON", "SHOT_ZONE_BASIC", "PRIOR_ZONE_FG_PCT", "PRIOR_FGA"]
    ]


def build_shot_features(shots: pd.DataFrame, pbp: pd.DataFrame | None = None) -> pd.DataFrame:
    """Assemble the modelling frame from shot-level data joined with reconstructed clock."""
    df = add_target(shots)

    df["SHOT_ANGLE"] = _shot_angle(df)
    df["GAME_SECONDS_REMAINING"] = _game_seconds_remaining(df)
    df["CLOCK_ELAPSED"] = 24.0 - df.SHOT_CLOCK
    df["IS_HOME"] = (df.TEAM_ABBREVIATION == df.HTM).astype(int) if "TEAM_ABBREVIATION" in df else 0
    df["IS_CLUTCH"] = (
        (df.GAME_SECONDS_REMAINING <= 300) & (df.SCORE_MARGIN.abs() <= 5)
        if "SCORE_MARGIN" in df
        else False
    ).astype(int)

    priors = build_shooter_priors(df)
    df = df.merge(priors, on=["PLAYER_ID", "SEASON", "SHOT_ZONE_BASIC"], how="left")

    league_rate = df.SHOT_MADE_FLAG.mean()
    df["PRIOR_ZONE_FG_PCT"] = df.PRIOR_ZONE_FG_PCT.fillna(league_rate)
    df["PRIOR_FGA"] = df.PRIOR_FGA.fillna(0.0)

    for col in CATEGORICAL:
        if col in df:
            df[col] = df[col].astype("category")
    return df


def attach_game_state(shots: pd.DataFrame, pbp: pd.DataFrame) -> pd.DataFrame:
    """Bring score margin across from play-by-play, forward-filled within each game.

    SCOREMARGIN is only populated on scoring events, so it must be carried forward; the
    leading NaNs before the first basket are a genuine 0-0 tie.
    """
    margin = pbp[["GAME_ID", "EVENTNUM", "SCOREMARGIN"]].copy()
    margin["SCOREMARGIN"] = (
        margin.SCOREMARGIN.replace("TIE", "0").astype("string").astype("Float64")
    )
    margin = margin.sort_values(["GAME_ID", "EVENTNUM"])
    margin["SCORE_MARGIN"] = (
        margin.groupby("GAME_ID").SCOREMARGIN.ffill().fillna(0.0).astype(float)
    )
    return shots.merge(
        margin[["GAME_ID", "EVENTNUM", "SCORE_MARGIN"]].rename(
            columns={"EVENTNUM": "GAME_EVENT_ID"}
        ),
        on=["GAME_ID", "GAME_EVENT_ID"],
        how="left",
    )
