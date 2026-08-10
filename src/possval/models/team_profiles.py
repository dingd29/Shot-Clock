"""Nuanced team and player profiles against each team's continuation-value curve.

The purpose is diagnosis, not a verdict.  Four quantities are kept separate:

* offensive efficiency -- what the team ultimately scored per possession;
* timing style -- when its shots were taken;
* continuation capability -- what its own possessions historically produced after declining;
* below-curve exposure -- how often and by how much a taken shot fell below that curve.

Below-curve exposure is deliberately one-sided.  A shot leaves a record; a good look that was
passed up does not.  High exposure can therefore suggest possessions worth reviewing for more
patience.  Low exposure cannot establish that a team should shoot sooner.

Player rows identify who *ended* the possession.  They do not identify who called the action,
declined an earlier look, received the ball late, or was assigned the bailout role.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.models.value import FULL_CLOCK, RESET_INSTANT

CLOCK_PHASES = ("late (0–7)", "middle (8–15)", "early (16–23)")


def add_basketball_context(scored: pd.DataFrame) -> pd.DataFrame:
    """Collapse feed labels into basketball-readable possession and shot contexts."""
    frame = scored.copy()
    starts = frame.CHANCE_START_TYPE.astype("string").fillna("unknown")
    frame["POSSESSION_CONTEXT"] = np.select(
        [
            starts.eq("after_turnover"),
            starts.eq("def_rebound"),
            starts.eq("off_rebound"),
            starts.isin(["after_made_fg", "after_made_ft"]),
        ],
        ["turnover attack", "rebound push", "second chance", "after a score"],
        default="other dead ball",
    )
    zones = frame.SHOT_ZONE_BASIC.astype("string").fillna("Unknown")
    frame["SHOT_FAMILY"] = np.select(
        [
            zones.eq("Restricted Area"),
            zones.eq("In The Paint (Non-RA)"),
            zones.eq("Mid-Range"),
            zones.str.contains("3", regex=False),
        ],
        ["rim", "paint (non-RA)", "mid-range", "three"],
        default="other",
    )
    return frame


def team_context_decomposition(
    scored: pd.DataFrame,
    min_cell_shots: int = 100,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate context mix from within-context exposure.

    The standardization cells are shot family × clock phase × possession context.  A team's
    expected exposure uses its own cell frequencies and the league's exposure in those cells.
    The residual is descriptive: team curves still differ in level, and this is not a causal
    estimate of what changing the shot mix would do.
    """
    frame = add_basketball_context(scored).dropna(subset=["CLOCK_PHASE"])
    keys = ["SHOT_FAMILY", "CLOCK_PHASE", "POSSESSION_CONTEXT"]
    league = (
        frame.groupby(keys, observed=True)
        .agg(LEAGUE_N=("EXPOSURE", "size"), LEAGUE_EXPOSURE=("EXPOSURE", "mean"))
        .reset_index()
    )
    league.loc[league.LEAGUE_N < min_cell_shots, "LEAGUE_EXPOSURE"] = np.nan
    details = (
        frame.groupby(["TEAM_ABBREVIATION", *keys], observed=True)
        .agg(
            N_SHOTS=("EXPOSURE", "size"),
            PREMATURE=("BELOW", "mean"),
            EXPOSURE_PER_SHOT=("EXPOSURE", "mean"),
            TOTAL_EXPOSURE=("EXPOSURE", "sum"),
            MEAN_SHOT_VALUE=("SHOT_VALUE", "mean"),
        )
        .reset_index()
        .merge(league, on=keys, how="left", validate="many_to_one")
    )
    totals = details.groupby("TEAM_ABBREVIATION").agg(
        TEAM_SHOTS=("N_SHOTS", "sum"), TEAM_EXPOSURE=("TOTAL_EXPOSURE", "sum")
    )
    details = details.join(totals, on="TEAM_ABBREVIATION")
    details["SHOT_SHARE"] = details.N_SHOTS / details.TEAM_SHOTS
    details["EXPOSURE_SHARE"] = details.TOTAL_EXPOSURE / details.TEAM_EXPOSURE
    details["EXPECTED_TOTAL_EXPOSURE"] = details.N_SHOTS * details.LEAGUE_EXPOSURE

    summary = (
        details.groupby("TEAM_ABBREVIATION")
        .agg(
            N_SHOTS=("N_SHOTS", "sum"),
            OBSERVED_EXPOSURE=("TOTAL_EXPOSURE", "sum"),
            EXPECTED_EXPOSURE=("EXPECTED_TOTAL_EXPOSURE", "sum"),
        )
        .reset_index()
    )
    summary["OBSERVED_EXPOSURE_PER_SHOT"] = summary.OBSERVED_EXPOSURE / summary.N_SHOTS
    summary["MIX_EXPECTED_EXPOSURE_PER_SHOT"] = summary.EXPECTED_EXPOSURE / summary.N_SHOTS
    summary["WITHIN_CONTEXT_EXCESS"] = (
        summary.OBSERVED_EXPOSURE_PER_SHOT - summary.MIX_EXPECTED_EXPOSURE_PER_SHOT
    )
    summary["WITHIN_CONTEXT_RANK"] = summary.WITHIN_CONTEXT_EXCESS.rank(
        ascending=False, method="min"
    ).astype(int)
    return summary.sort_values("WITHIN_CONTEXT_RANK"), details


def score_against_team_curve(valued: pd.DataFrame, curves: pd.DataFrame) -> pd.DataFrame:
    """Attach the relevant team's `V(t)` and a non-causal shortfall to every taken shot."""
    frame = valued.dropna(
        subset=["TEAM_ABBREVIATION", "SHOT_VALUE", "SECOND"]
    ).copy()
    frame = frame[frame.SECOND != RESET_INSTANT]
    order = curves.TEAM.to_numpy()
    grid = curves[[f"V{second}" for second in range(FULL_CLOCK + 1)]].to_numpy(dtype=float)
    position = pd.Index(order).get_indexer(frame.TEAM_ABBREVIATION.to_numpy())
    seconds = frame.SECOND.to_numpy(dtype=int)
    frame["REFERENCE"] = np.where(
        position >= 0,
        grid[np.clip(position, 0, None), seconds],
        np.nan,
    )
    frame = frame.dropna(subset=["REFERENCE"])
    frame["GAP"] = frame.REFERENCE - frame.SHOT_VALUE
    frame["BELOW"] = frame.GAP > 0
    frame["EXPOSURE"] = frame.GAP.clip(lower=0)
    frame["CLOCK_PHASE"] = pd.cut(
        frame.SECOND,
        bins=[-1, 7, 15, 23],
        labels=CLOCK_PHASES,
        include_lowest=True,
    )
    return frame


def team_offensive_efficiency(chained: pd.DataFrame) -> pd.DataFrame:
    """All-points efficiency with each possession counted exactly once."""
    keys = ["GAME_ID", "PERIOD", "POSSESSION_ID"]
    possessions = (
        chained.dropna(subset=["TEAM"])
        .groupby(keys, sort=False)
        .agg(TEAM=("TEAM", "first"), PTS=("PTS_ALL", "sum"))
        .reset_index()
    )
    table = (
        possessions.groupby("TEAM")
        .agg(N_POSS=("PTS", "size"), PPP=("PTS", "mean"))
        .reset_index()
    )
    table["OFFENSE_RANK"] = table.PPP.rank(ascending=False, method="min").astype(int)
    return table


def team_diagnostics(
    valued: pd.DataFrame,
    curves: pd.DataFrame,
    chained: pd.DataFrame,
    min_shots: int = 2_000,
) -> pd.DataFrame:
    """One row per team, keeping outcome, style, and exposure distinct."""
    scored = score_against_team_curve(valued, curves)
    grouped = scored.groupby("TEAM_ABBREVIATION")
    table = pd.DataFrame(
        {
            "N_SHOTS": grouped.size(),
            "PREMATURE": grouped.BELOW.mean(),
            # Expected gap among the flagged shots: severity conditional on exposure.
            "SHORTFALL_WHEN_BELOW": grouped.apply(
                lambda frame: float(frame.loc[frame.BELOW, "GAP"].mean()),
                include_groups=False,
            ),
            # Mean positive gap over every shot: frequency and severity in one quantity.
            "EXPOSURE_PER_SHOT": grouped.EXPOSURE.mean(),
            "MEAN_SECOND": grouped.SECOND.mean(),
            "LATE_SHARE": grouped.SECOND.apply(lambda seconds: float((seconds <= 7).mean())),
            "EARLY_SHARE": grouped.SECOND.apply(lambda seconds: float((seconds >= 16).mean())),
            "MEAN_SHOT_VALUE": grouped.SHOT_VALUE.mean(),
        }
    ).reset_index()
    table = table[table.N_SHOTS >= min_shots]
    capability_seconds = [2, 6, 10, 14, 18, 22]
    capability_columns = [f"V{second}" for second in capability_seconds]
    capability = curves[["TEAM", *capability_columns]].copy()
    capability["CURVE_LEVEL"] = capability[capability_columns].mean(axis=1)
    capability["CURVE_DROP_22_TO_2"] = capability.V22 - capability.V2
    table = table.merge(
        capability[["TEAM", "CURVE_LEVEL", "CURVE_DROP_22_TO_2"]],
        left_on="TEAM_ABBREVIATION",
        right_on="TEAM",
        how="left",
        validate="one_to_one",
    ).drop(columns="TEAM")
    table = table.merge(
        team_offensive_efficiency(chained),
        left_on="TEAM_ABBREVIATION",
        right_on="TEAM",
        how="left",
        validate="one_to_one",
    ).drop(columns="TEAM")
    table["PREMATURE_RANK"] = table.PREMATURE.rank(ascending=False, method="min").astype(int)
    table["EXPOSURE_RANK"] = table.EXPOSURE_PER_SHOT.rank(
        ascending=False, method="min"
    ).astype(int)
    # A review queue, not a grade: bottom-third offense plus top-third exposure.
    cutoff = max(len(table) // 3, 1)
    table["REVIEW_FLAG"] = (
        (table.OFFENSE_RANK > len(table) - cutoff) & (table.EXPOSURE_RANK <= cutoff)
    )
    return table.sort_values("OFFENSE_RANK")


def team_clock_bands(scored: pd.DataFrame, min_shots: int = 300) -> pd.DataFrame:
    """Locate a team's exposure on the clock; early/middle exposure is more actionable."""
    grouped = scored.dropna(subset=["CLOCK_PHASE"]).groupby(
        ["TEAM_ABBREVIATION", "CLOCK_PHASE"], observed=True
    )
    table = grouped.agg(
        N_SHOTS=("BELOW", "size"),
        PREMATURE=("BELOW", "mean"),
        EXPOSURE_PER_SHOT=("EXPOSURE", "mean"),
        MEAN_GAP=("GAP", "mean"),
    ).reset_index()
    return table[table.N_SHOTS >= min_shots]


def player_diagnostics(scored: pd.DataFrame, min_shots: int = 300) -> pd.DataFrame:
    """Who ended below-curve possessions, contextualized by team rate and clock burden."""
    required = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"]
    frame = scored.dropna(subset=required)
    team_rate = frame.groupby("TEAM_ABBREVIATION").BELOW.mean().rename("TEAM_PREMATURE")
    grouped = frame.groupby(required)
    table = grouped.agg(
        N_SHOTS=("BELOW", "size"),
        PREMATURE=("BELOW", "mean"),
        EXPOSURE_PER_SHOT=("EXPOSURE", "mean"),
        SHORTFALL_WHEN_BELOW=(
            "GAP",
            lambda gap: float(gap[gap > 0].mean()),
        ),
        MEAN_SECOND=("SECOND", "mean"),
        LATE_SHARE=("SECOND", lambda seconds: float((seconds <= 7).mean())),
        MEAN_SHOT_VALUE=("SHOT_VALUE", "mean"),
    ).reset_index()
    table = table[table.N_SHOTS >= min_shots]
    table["TEAM_PREMATURE"] = table.TEAM_ABBREVIATION.map(team_rate)
    table["PREMATURE_MINUS_TEAM"] = table.PREMATURE - table.TEAM_PREMATURE
    return table.sort_values(["TEAM_ABBREVIATION", "PREMATURE"], ascending=[True, False])
