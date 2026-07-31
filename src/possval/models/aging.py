"""Aging curves fitted from the reconstructed shot data.

Layer 1 of the projection needs an answer to "how much of this player's production carries
into next season", and the answer is most uncertain exactly where this project needs it:
LeBron plays 2026-27 at 41/42, past the age at which any usable sample exists.

Method is the standard **delta (paired-change) approach**: for every player who appears in
consecutive seasons at ages a and a+1, take the change in his metric, then average those
changes by age. Fitting a level curve instead — mean performance by age — is dominated by
selection, since only good players are still in the league at 36.

**The delta method does not eliminate survivorship bias, it only reduces it.** A player who
falls off a cliff is released and never records the second season of the pair, so observed
declines at old ages are biased *toward zero*. Every curve below is therefore optimistic at
the tail, and the projection treats it as an upper bound rather than a point estimate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def player_seasons(shots: pd.DataFrame, min_attempts: int = 150) -> pd.DataFrame:
    """Per player-season efficiency and volume, the inputs to the paired change."""
    grouped = (
        shots.groupby(["PLAYER_ID", "PLAYER_NAME", "SEASON"], observed=True)
        .agg(FGA=("PTS", "size"), PTS=("PTS", "sum"), XPTS=("XPTS", "sum"))
        .reset_index()
    )
    grouped = grouped[min_attempts <= grouped.FGA]
    grouped["PTS_PER_FGA"] = grouped.PTS / grouped.FGA
    grouped["MAKING_PER_100"] = (grouped.PTS - grouped.XPTS) / grouped.FGA * 100
    grouped["SELECTION"] = grouped.XPTS / grouped.FGA
    return grouped


def attach_age(seasons: pd.DataFrame, ages: pd.DataFrame) -> pd.DataFrame:
    """Attach age, back-projecting from a single current-age snapshot.

    DARKO gives each player's age today; a player's age in season S is that value minus the
    number of seasons since. Good to within a year, which is the resolution an aging curve
    supports anyway.
    """
    current_season = int(seasons.SEASON.max())
    lookup = ages.set_index("PLAYER_ID").AGE
    out = seasons.copy()
    out["AGE"] = out.PLAYER_ID.map(lookup) - (current_season - out.SEASON)
    return out.dropna(subset=["AGE"])


def paired_changes(seasons_with_age: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Year-over-year change for players present in consecutive seasons."""
    df = seasons_with_age.sort_values(["PLAYER_ID", "SEASON"]).copy()
    grouped = df.groupby("PLAYER_ID", observed=True)

    df["NEXT_SEASON"] = grouped.SEASON.shift(-1)
    df["NEXT_VALUE"] = grouped[metric].shift(-1)
    df["NEXT_FGA"] = grouped.FGA.shift(-1)

    consecutive = df[df.NEXT_SEASON == df.SEASON + 1].copy()
    consecutive["DELTA"] = consecutive.NEXT_VALUE - consecutive[metric]
    # Weight by the smaller of the two samples: a pair is only as reliable as its thinner half.
    consecutive["WEIGHT"] = np.minimum(consecutive.FGA, consecutive.NEXT_FGA)
    consecutive["AGE_FROM"] = consecutive.AGE.round().astype(int)
    return consecutive


def aging_curve(
    seasons_with_age: pd.DataFrame, metric: str = "PTS_PER_FGA", min_pairs: int = 8
) -> pd.DataFrame:
    """Mean weighted change in `metric` from each age to the next, with standard errors."""
    pairs = paired_changes(seasons_with_age, metric)

    rows = []
    for age, group in pairs.groupby("AGE_FROM"):
        if len(group) < min_pairs:
            continue
        weights = group.WEIGHT.to_numpy(dtype=float)
        deltas = group.DELTA.to_numpy(dtype=float)
        mean = float(np.average(deltas, weights=weights))
        # Weighted standard error of the weighted mean.
        variance = np.average((deltas - mean) ** 2, weights=weights)
        rows.append(
            {
                "AGE_FROM": age,
                "AGE_TO": age + 1,
                "N_PAIRS": len(group),
                "MEAN_DELTA": mean,
                "SE": float(np.sqrt(variance / len(group))),
            }
        )

    curve = pd.DataFrame(rows).sort_values("AGE_FROM").reset_index(drop=True)
    curve["CUMULATIVE"] = curve.MEAN_DELTA.cumsum()
    return curve


def project_metric(
    curve: pd.DataFrame, current_value: float, age: float, seasons_ahead: int = 1
) -> dict:
    """Apply the curve to one player, returning the projection and its support.

    `n_pairs` is reported alongside the estimate because at the ages this project cares
    about it is small enough to be the headline caveat rather than a footnote.
    """
    total, support, se2 = 0.0, [], 0.0
    for step in range(seasons_ahead):
        target = int(round(age)) + step
        row = curve[target == curve.AGE_FROM]
        if row.empty:
            # Past the supported range: carry the oldest observed decline forward, and say so.
            row = curve.tail(1)
            support.append({"age": target, "n_pairs": 0, "extrapolated": True})
        else:
            support.append(
                {"age": target, "n_pairs": int(row.N_PAIRS.iloc[0]), "extrapolated": False}
            )
        total += float(row.MEAN_DELTA.iloc[0])
        se2 += float(row.SE.iloc[0]) ** 2

    return {
        "projected": current_value + total,
        "delta": total,
        "se": float(np.sqrt(se2)),
        "support": support,
        "extrapolated": any(s["extrapolated"] for s in support),
    }
