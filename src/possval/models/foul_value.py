"""All-points shooting-action valuation for the team-profile validation sprint.

The published shot table contains official FGA.  A missed attempt drawing a shooting foul is not
an FGA and therefore never reaches that table; an and-one is an FGA, but its free throw is outside
the existing shot value.  The historical continuation curve is field-goal-only too, so there is
no one-sided free-throw leak, but there is an omitted class of exercise decisions.

This module builds one row per shooting action: an official FGA or a foul-only shooting action.
Its target is all points from that action's chance to the end of the possession.  A model using
only features shared by both action types estimates the value out of time; realized points from
the scored action are never used as its own prediction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from possval.models.value import FULL_CLOCK, RESET_INSTANT

SHOOTING_FOUL_ACTIONS = (2, 29)
PRIOR_STRENGTH = 100.0
ACTION_NUMERIC = [
    "SHOT_CLOCK",
    "PERIOD",
    "GAME_SECONDS_REMAINING",
    "IS_HOME",
    "PRIOR_ACTION_VALUE",
    "PRIOR_ACTION_N",
]
ACTION_CATEGORICAL = ["CHANCE_START_TYPE"]


def shooting_foul_events(events: pd.DataFrame) -> pd.DataFrame:
    """All clocked shooting fouls, with and-ones and resulting FT points identified."""
    ordered = events.sort_values(["GAME_ID", "EVENTNUM"]).reset_index(drop=True)
    mask = ordered.EVENTMSGTYPE.eq(6) & ordered.EVENTMSGACTIONTYPE.isin(
        SHOOTING_FOUL_ACTIONS
    )
    fouls = ordered[mask].copy()
    previous = ordered.shift(1).loc[fouls.index]
    same_clock = previous.PCTIMESTRING.astype("string").to_numpy() == fouls.PCTIMESTRING.astype(
        "string"
    ).to_numpy()
    fouls["AND_ONE"] = (
        previous.GAME_ID.to_numpy() == fouls.GAME_ID.to_numpy()
    ) & previous.EVENTMSGTYPE.eq(1).to_numpy() & same_clock & (
        previous.PLAYER1_ID.to_numpy() == fouls.PLAYER2_ID.to_numpy()
    )
    text = ordered.HOMEDESCRIPTION.fillna("") + " " + ordered.VISITORDESCRIPTION.fillna("")
    free_throws = ordered[ordered.EVENTMSGTYPE.eq(3)].copy()
    free_throws["FT_POINTS"] = (~text[ordered.EVENTMSGTYPE.eq(3)].str.contains("MISS")).astype(int)
    foul_keys = ["GAME_ID", "CHANCE_ID", "PLAYER2_ID"]
    ft_points = (
        free_throws.groupby(["GAME_ID", "CHANCE_ID", "PLAYER1_ID"])
        .FT_POINTS.sum()
        .rename_axis(foul_keys)
        .rename("FT_POINTS")
        .reset_index()
    )
    fouls = fouls.merge(ft_points, on=foul_keys, how="left", validate="many_to_one")
    fouls["FT_POINTS"] = fouls.FT_POINTS.fillna(0.0)
    # The description sits on the defending team's side of the feed.
    fouls["IS_HOME"] = fouls.VISITORDESCRIPTION.notna().astype(int)
    periods_left = np.maximum(4 - fouls.PERIOD.to_numpy(), 0)
    fouls["GAME_SECONDS_REMAINING"] = fouls.GAME_CLOCK + periods_left * 720
    return fouls.rename(
        columns={
            "PLAYER2_ID": "PLAYER_ID",
            "PLAYER2_NAME": "PLAYER_NAME",
            "PLAYER2_TEAM_ABBREVIATION": "TEAM_ABBREVIATION",
        }
    )


def foul_only_exercises(events: pd.DataFrame) -> pd.DataFrame:
    """Clocked shooting fouls that are not the free-throw tail of an and-one."""
    fouls = shooting_foul_events(events)
    return fouls[~fouls.AND_ONE].copy()


def historical_foul_premium(
    actions: pd.DataFrame,
    foul_events: pd.DataFrame,
    train_through: int = 2021,
    prior_strength: float = 200.0,
) -> pd.DataFrame:
    """Expected shooting-foul FT points per action from seasons before scoring.

    The denominator is every shooting action (FGA plus foul-only exercise); and-ones are already
    FGA and are not added twice.  Shrinkage is toward the historical league rate.  Nothing from
    the scored seasons enters the premium.
    """
    history = actions[actions.SEASON.le(train_through)]
    historical_fouls = foul_events[foul_events.SEASON.le(train_through)]
    attempts = history.groupby("PLAYER_ID").size().rename("PRIOR_ACTIONS")
    points = historical_fouls.groupby("PLAYER_ID").FT_POINTS.sum().rename("PRIOR_FT_POINTS")
    table = pd.concat([attempts, points], axis=1).fillna(0.0)
    league_rate = historical_fouls.FT_POINTS.sum() / len(history)
    table["FOUL_PREMIUM"] = (
        table.PRIOR_FT_POINTS + prior_strength * league_rate
    ) / (table.PRIOR_ACTIONS + prior_strength)
    table["LEAGUE_FOUL_PREMIUM"] = league_rate
    return table.reset_index()


def foul_repriced_actions(
    valued_fga: pd.DataFrame,
    foul_only: pd.DataFrame,
    premiums: pd.DataFrame,
) -> pd.DataFrame:
    """Score FGA and location-missing foul exercises in a common all-points unit.

    `valued_fga` must already use an all-points second-chance value.  Each FGA keeps its detailed
    location-aware xPTS and receives the player's historical unconditional foul premium.  A
    foul-only action receives a non-outcome base value imputed from that player's same-phase FGA,
    then player mean, team-phase mean, and league-phase mean.  The actual foul or FT result never
    enters the scored value.
    """
    fga = valued_fga.copy()
    fga = fga[fga.SECOND != RESET_INSTANT]
    fga["CLOCK_PHASE"] = pd.cut(
        fga.SECOND,
        [-1, 7, 15, 23],
        labels=["late", "middle", "early"],
        include_lowest=True,
    )
    premium = premiums.set_index("PLAYER_ID").FOUL_PREMIUM
    league_premium = float(premiums.LEAGUE_FOUL_PREMIUM.iloc[0])
    fga["FOUL_PREMIUM"] = fga.PLAYER_ID.map(premium).fillna(league_premium)
    fga["BASE_SHOT_VALUE"] = fga.SHOT_VALUE
    fga["SHOT_VALUE"] = fga.BASE_SHOT_VALUE + fga.FOUL_PREMIUM
    fga["ACTION_KIND"] = "official FGA"

    foul = foul_only.copy()
    foul["SECOND"] = foul.SHOT_CLOCK.round().clip(0, FULL_CLOCK).astype(int)
    foul = foul[foul.SECOND != RESET_INSTANT]
    foul["CLOCK_PHASE"] = pd.cut(
        foul.SECOND,
        [-1, 7, 15, 23],
        labels=["late", "middle", "early"],
        include_lowest=True,
    )
    player_phase = fga.groupby(["PLAYER_ID", "CLOCK_PHASE"], observed=True).BASE_SHOT_VALUE.mean()
    player = fga.groupby("PLAYER_ID").BASE_SHOT_VALUE.mean()
    team_phase = fga.groupby(
        ["TEAM_ABBREVIATION", "CLOCK_PHASE"], observed=True
    ).BASE_SHOT_VALUE.mean()
    league_phase = fga.groupby("CLOCK_PHASE", observed=True).BASE_SHOT_VALUE.mean()
    foul_index = pd.MultiIndex.from_frame(foul[["PLAYER_ID", "CLOCK_PHASE"]])
    foul["BASE_SHOT_VALUE"] = player_phase.reindex(foul_index).to_numpy()
    foul["BASE_SHOT_VALUE"] = foul.BASE_SHOT_VALUE.fillna(foul.PLAYER_ID.map(player))
    team_index = pd.MultiIndex.from_frame(foul[["TEAM_ABBREVIATION", "CLOCK_PHASE"]])
    foul["BASE_SHOT_VALUE"] = foul.BASE_SHOT_VALUE.fillna(
        pd.Series(team_phase.reindex(team_index).to_numpy(), index=foul.index)
    )
    foul["BASE_SHOT_VALUE"] = foul.BASE_SHOT_VALUE.fillna(
        foul.CLOCK_PHASE.map(league_phase).astype(float)
    )
    foul["FOUL_PREMIUM"] = foul.PLAYER_ID.map(premium).fillna(league_premium)
    foul["SHOT_VALUE"] = foul.BASE_SHOT_VALUE + foul.FOUL_PREMIUM
    foul["ACTION_KIND"] = "foul-only exercise"
    if "PERIOD_SECONDS_REMAINING" not in foul and "GAME_CLOCK" in foul:
        foul["PERIOD_SECONDS_REMAINING"] = foul.GAME_CLOCK
    if "GAME_CLOCK_EXPIRING" not in foul and "GAME_CLOCK" in foul:
        foul["GAME_CLOCK_EXPIRING"] = foul.GAME_CLOCK.lt(3).astype(int)

    # Keep the location and shot-family columns that exist only for official FGA.  Their
    # absence on foul-only exercises is the uncertainty this validation is meant to expose;
    # taking the column intersection would silently erase the information needed to bound it.
    return pd.concat([fga, foul], ignore_index=True, sort=False)


def exercise_actions(
    shots: pd.DataFrame,
    events: pd.DataFrame,
    chained_all_points: pd.DataFrame,
) -> pd.DataFrame:
    """Combine FGA and foul-only exercises with all-points possession outcomes."""
    keys = ["GAME_ID", "PERIOD", "CHANCE_ID"]
    outcomes = chained_all_points[
        [*keys, "POSSESSION_ID", "PTS_POSS"]
    ].drop_duplicates(keys)

    fga = shots.merge(outcomes, on=keys, how="inner", validate="many_to_one").copy()
    fga["ACTION_KIND"] = "official FGA"
    if "GAME_SECONDS_REMAINING" not in fga:
        periods_left = np.maximum(4 - fga.PERIOD.to_numpy(), 0)
        fga["GAME_SECONDS_REMAINING"] = (
            fga.PERIOD_SECONDS_REMAINING + periods_left * 720
        )

    fouls = foul_only_exercises(events).merge(
        outcomes, on=keys, how="inner", validate="many_to_one"
    )
    fouls["ACTION_KIND"] = "foul-only exercise"
    fouls["PERIOD_SECONDS_REMAINING"] = fouls.GAME_CLOCK
    fouls["GAME_CLOCK_EXPIRING"] = fouls.GAME_CLOCK.lt(3).astype(int)

    common = [
        "PLAYER_ID",
        "PLAYER_NAME",
        "TEAM_ABBREVIATION",
        "SEASON",
        "GAME_ID",
        "PERIOD",
        "CHANCE_ID",
        "POSSESSION_ID",
        "SHOT_CLOCK",
        "CHANCE_START_TYPE",
        "PERIOD_SECONDS_REMAINING",
        "GAME_SECONDS_REMAINING",
        "GAME_CLOCK_EXPIRING",
        "IS_HOME",
        "PTS_POSS",
        "ACTION_KIND",
    ]
    actions = pd.concat([fga[common], fouls[common]], ignore_index=True)
    actions = actions.dropna(
        subset=["PLAYER_ID", "TEAM_ABBREVIATION", "SHOT_CLOCK", "PTS_POSS"]
    )
    # Exactly one row per decision. An and-one remains represented by its official FGA; its
    # PTS_POSS target includes the following free throw because the offense has not changed.
    return actions.drop_duplicates(["GAME_ID", "PERIOD", "CHANCE_ID", "ACTION_KIND"])


def add_action_priors(actions: pd.DataFrame) -> pd.DataFrame:
    """Strictly-prior-season player action value, shrunk toward prior league results."""
    frame = actions.copy()
    season_player = (
        frame.groupby(["PLAYER_ID", "SEASON"])
        .agg(POINTS=("PTS_POSS", "sum"), N=("PTS_POSS", "size"))
        .reset_index()
        .sort_values(["PLAYER_ID", "SEASON"])
    )
    by_player = season_player.groupby("PLAYER_ID")
    season_player["PRIOR_POINTS"] = by_player.POINTS.cumsum() - season_player.POINTS
    season_player["PRIOR_ACTION_N"] = by_player.N.cumsum() - season_player.N

    by_season = frame.groupby("SEASON").PTS_POSS.agg(["sum", "size"]).sort_index()
    prior_sum = by_season["sum"].cumsum() - by_season["sum"]
    prior_n = by_season["size"].cumsum() - by_season["size"]
    league_prior = (prior_sum / prior_n.replace(0, np.nan)).fillna(1.0)
    season_player["LEAGUE_PRIOR"] = season_player.SEASON.map(league_prior)
    season_player["PRIOR_ACTION_VALUE"] = (
        season_player.PRIOR_POINTS + PRIOR_STRENGTH * season_player.LEAGUE_PRIOR
    ) / (season_player.PRIOR_ACTION_N + PRIOR_STRENGTH)
    priors = season_player[
        ["PLAYER_ID", "SEASON", "PRIOR_ACTION_VALUE", "PRIOR_ACTION_N"]
    ]
    return frame.merge(
        priors,
        on=["PLAYER_ID", "SEASON"],
        how="left",
        validate="many_to_one",
    )


def _design(frame: pd.DataFrame) -> pd.DataFrame:
    design = frame[ACTION_NUMERIC + ACTION_CATEGORICAL].copy()
    for column in ACTION_CATEGORICAL:
        design[column] = design[column].astype("category")
    return design


def fit_action_value(
    actions: pd.DataFrame,
    train_through: int = 2021,
    score_first: int = 2022,
    score_last: int = 2023,
    seed: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, HistGradientBoostingRegressor]:
    """Fit on past seasons and predict all-points value for later shooting actions."""
    frame = add_action_priors(actions)
    train = frame[frame.SEASON.le(train_through)]
    scored = frame[frame.SEASON.between(score_first, score_last)].copy()
    if train.empty or scored.empty or train.SEASON.max() >= scored.SEASON.min():
        raise ValueError("action-value split must be non-empty and chronological")
    model = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.06,
        max_leaf_nodes=31,
        min_samples_leaf=300,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=25,
        random_state=seed,
    )
    model.fit(_design(train), train.PTS_POSS.to_numpy(dtype=float))
    predicted = np.clip(model.predict(_design(scored)), 0.0, 3.0)
    scored["SHOT_VALUE"] = predicted
    scored["SECOND"] = scored.SHOT_CLOCK.round().clip(0, 24).astype(int)
    actual = scored.PTS_POSS.to_numpy(dtype=float)
    constant = np.full(len(scored), train.PTS_POSS.mean())
    metrics = pd.DataFrame(
        [
            {
                "MODEL": "past league mean",
                "N": len(scored),
                "MAE": mean_absolute_error(actual, constant),
                "RMSE": mean_squared_error(actual, constant) ** 0.5,
                "R2": r2_score(actual, constant),
                "BIAS": float((constant - actual).mean()),
            },
            {
                "MODEL": "common-feature action model",
                "N": len(scored),
                "MAE": mean_absolute_error(actual, predicted),
                "RMSE": mean_squared_error(actual, predicted) ** 0.5,
                "R2": r2_score(actual, predicted),
                "BIAS": float((predicted - actual).mean()),
            },
        ]
    )
    return scored, metrics, model
