"""Does a change in premature shooting predict what the same team does next?

This is the prospective check for the team profiles in :mod:`possval.models.value`.  The
published team result establishes that franchises differ in how often they shoot below their
own continuation curve.  Persistence is not the same as actionability, however.  A useful
decision measure should contain information about what happens *after* it is observed.

The chronology here is strict:

* a team's continuation curve, rebound lookup, and second-chance value use only the two seasons
  before the season being scored;
* current behaviour is measured in a non-overlapping 20-game block;
* the outcome is points per possession in the following 20-game block; and
* current efficiency and shot value are controls, so ordinary offensive persistence is not
  credited to clock management.

The analysis is exploratory.  It was designed and first run together on 6 August 2026, so its
historical result is not described as pre-registered or confirmatory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from possval.models.rebound import possession_panel
from possval.models.value import FULL_CLOCK, RESET_INSTANT, shot_value, team_curves


def game_blocks(chained: pd.DataFrame, games_per_block: int = 20) -> pd.DataFrame:
    """Map each team-game to a chronological, non-overlapping block within its season."""
    keys = (
        chained[["SEASON", "TEAM", "GAME_ID"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["SEASON", "TEAM", "GAME_ID"])
    )
    keys["GAME_NO"] = keys.groupby(["SEASON", "TEAM"]).cumcount()
    keys["BLOCK"] = (keys.GAME_NO // games_per_block).astype(int)
    return keys


def block_efficiency(chained: pd.DataFrame, blocks: pd.DataFrame) -> pd.DataFrame:
    """All-points offensive efficiency for every team block, one row per possession.

    `possession_panel` repeats the remaining possession value on every chance.  Efficiency must
    instead sum `PTS_ALL` over the chances belonging to one possession and then average those
    possession totals; otherwise offensive rebounds and retained-ball fouls receive extra weight.
    """
    joined = chained.merge(
        blocks[["SEASON", "TEAM", "GAME_ID", "BLOCK"]],
        on=["SEASON", "TEAM", "GAME_ID"],
        how="inner",
        validate="many_to_one",
    )
    possessions = (
        joined.groupby(
            ["SEASON", "TEAM", "GAME_ID", "BLOCK", "PERIOD", "POSSESSION_ID"],
            as_index=False,
        )
        .PTS_ALL.sum()
    )
    return (
        possessions.groupby(["SEASON", "TEAM", "BLOCK"])
        .agg(PPP=("PTS_ALL", "mean"), N_POSS=("PTS_ALL", "size"))
        .reset_index()
    )


def block_premature_share(
    valued: pd.DataFrame,
    curves: pd.DataFrame,
    blocks: pd.DataFrame,
) -> pd.DataFrame:
    """Score current shots against curves frozen before the current season."""
    frame = valued.merge(
        blocks[["SEASON", "TEAM", "GAME_ID", "BLOCK"]],
        left_on=["SEASON", "TEAM_ABBREVIATION", "GAME_ID"],
        right_on=["SEASON", "TEAM", "GAME_ID"],
        how="inner",
        validate="many_to_one",
    )
    order = curves.TEAM.to_numpy()
    grid = curves[[f"V{t}" for t in range(FULL_CLOCK + 1)]].to_numpy(dtype=float)
    position = pd.Index(order).get_indexer(frame.TEAM_ABBREVIATION.to_numpy())
    seconds = frame.SECOND.to_numpy()
    frame["REFERENCE"] = np.where(
        position >= 0, grid[np.clip(position, 0, None), seconds], np.nan
    )
    frame = frame[(frame.SECOND != RESET_INSTANT) & frame.REFERENCE.notna()].copy()
    frame["BELOW"] = frame.SHOT_VALUE < frame.REFERENCE
    return (
        frame.groupby(["SEASON", "TEAM", "BLOCK"])
        .agg(
            PREMATURE=("BELOW", "mean"),
            N_SHOTS=("BELOW", "size"),
            MEAN_SHOT_VALUE=("SHOT_VALUE", "mean"),
            MEAN_SECOND=("SECOND", "mean"),
        )
        .reset_index()
    )


def prospective_panel(
    panel: pd.DataFrame,
    shots: pd.DataFrame,
    outcomes: pd.DataFrame,
    first_season: int = 2017,
    last_season: int = 2024,
    history_seasons: int = 2,
    games_per_block: int = 20,
    min_history_possessions: int = 1_500,
    min_history_chances: int = 50,
    min_block_shots: int = 500,
    min_block_possessions: int = 1_000,
) -> pd.DataFrame:
    """Build the leakage-safe current-block → next-block team panel."""
    chained = possession_panel(panel)
    chained = chained[~chained.PERIOD_EXPIRED].copy()
    blocks = game_blocks(chained, games_per_block=games_per_block)
    efficiency = block_efficiency(chained, blocks)
    rows = []

    for season in range(first_season, last_season + 1):
        history = chained[chained.SEASON.between(season - history_seasons, season - 1)]
        curves = team_curves(
            history,
            min_chances=min_history_chances,
            min_possessions=min_history_possessions,
        )
        history_outcomes = outcomes[
            outcomes.SEASON.between(season - history_seasons, season - 1)
        ]
        second_chances = history[history.START_TYPE == "off_rebound"]
        if curves.empty or second_chances.empty:
            continue
        second_chance_value = float(second_chances.PTS_POSS.mean())
        current_shots = shots[
            (shots.SEASON == season) & (shots.GAME_CLOCK_EXPIRING == 0)
        ]
        valued = shot_value(current_shots, history_outcomes, second_chance_value)
        features = block_premature_share(valued, curves, blocks[blocks.SEASON == season])
        current = features.merge(
            efficiency[efficiency.SEASON == season], on=["SEASON", "TEAM", "BLOCK"]
        )
        current["NEXT_BLOCK"] = current.BLOCK + 1
        future = efficiency[efficiency.SEASON == season].rename(
            columns={"BLOCK": "NEXT_BLOCK", "PPP": "NEXT_PPP", "N_POSS": "NEXT_N_POSS"}
        )
        rows.append(current.merge(future, on=["SEASON", "TEAM", "NEXT_BLOCK"]))

    if not rows:
        return pd.DataFrame()
    result = pd.concat(rows, ignore_index=True)
    keep = (
        (result.N_SHOTS >= min_block_shots)
        & (result.N_POSS >= min_block_possessions)
        & (result.NEXT_N_POSS >= min_block_possessions)
    )
    return result[keep].sort_values(["SEASON", "TEAM", "BLOCK"]).reset_index(drop=True)


def fixed_effect_regression(
    panel: pd.DataFrame,
    controls: tuple[str, ...] = (),
    outcome: str = "NEXT_PPP",
) -> dict:
    """OLS with team/season fixed effects and team-clustered CR1 standard errors."""
    columns = ["PREMATURE", *controls]
    design = pd.concat(
        [
            pd.Series(1.0, index=panel.index, name="Intercept"),
            panel[columns],
            pd.get_dummies(panel.TEAM, prefix="team", drop_first=True, dtype=float),
            pd.get_dummies(panel.SEASON, prefix="season", drop_first=True, dtype=float),
        ],
        axis=1,
    ).astype(float)
    x = design.to_numpy()
    y = panel[outcome].to_numpy(dtype=float)
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    residual = y - x @ beta
    bread = np.linalg.pinv(x.T @ x)
    meat = np.zeros_like(bread)
    groups = panel.TEAM.to_numpy()
    unique = pd.unique(groups)
    for group in unique:
        score = x[groups == group].T @ residual[groups == group]
        meat += np.outer(score, score)
    n, k, g = len(y), len(beta), len(unique)
    correction = (g / (g - 1)) * ((n - 1) / (n - k))
    covariance = correction * bread @ meat @ bread
    at = design.columns.get_loc("PREMATURE")
    standard_error = float(np.sqrt(covariance[at, at]))
    estimate = float(beta[at])
    t_stat = estimate / standard_error
    p_value = float(2 * stats.t.sf(abs(t_stat), g - 1))
    total = float(np.sum((y - y.mean()) ** 2))
    return {
        "n": n,
        "teams": g,
        "estimate": estimate,
        "std_error": standard_error,
        "t": t_stat,
        "p": p_value,
        "effect_per_1pp": estimate * 0.01,
        "r2": 1 - float(residual @ residual) / total,
    }


def prospective_specifications(panel: pd.DataFrame) -> pd.DataFrame:
    """The nested specifications that distinguish persistence from incremental signal."""
    rows = []
    for name, controls in (
        ("team_and_season_fe", ()),
        ("plus_current_efficiency", ("PPP",)),
        ("plus_efficiency_shot_value_and_timing", ("PPP", "MEAN_SHOT_VALUE", "MEAN_SECOND")),
    ):
        rows.append(
            {
                "specification": name,
                "controls": "+".join(controls),
                **fixed_effect_regression(panel, controls),
            }
        )
    return pd.DataFrame(rows)
