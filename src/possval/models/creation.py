"""Creation profiles and usage overlap.

The project's answer to "will these players fit together." A superteam's binding constraint
is possession scarcity: four high-usage creators, one ball, roughly 100 possessions. Value
is lost when players want the ball *at the same moments*, and that is measurable here in a
way it is not from public data, because we reconstructed when on the shot clock each shot
was taken.

A player's **creation profile** is the distribution of his shot attempts over
(shot-clock bucket × zone). Two players overlap when their profiles have the same shape:
both need the ball at 18-15 seconds in the same areas. A transition rim-runner and a
late-clock isolation scorer have low overlap and complement each other.

Overlap is measured with Jensen-Shannon divergence, which is symmetric, bounded in [0, 1],
and defined even when a player has zero attempts in a cell — none of which is true of KL
divergence, the obvious first choice.

**This is descriptive, not causal.** It says whether two players want the ball at the same
time, not how much value that costs. The cost is estimated separately in `synergy.py` by
fitting overlap against realised lineup efficiency across historical lineups.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.clock.validate import BUCKET_ORDER, assign_bucket

ZONES = ("Rim", "Mid-range", "Three")


def _zone(shots: pd.DataFrame) -> pd.Series:
    return pd.Series(
        np.where(
            shots.SHOT_ZONE_BASIC == "Restricted Area",
            "Rim",
            np.where(shots.IS_3 == 1, "Three", "Mid-range"),
        ),
        index=shots.index,
    )


def profile_cells() -> list[tuple[str, str]]:
    return [(b, z) for b in BUCKET_ORDER for z in ZONES]


def creation_profiles(
    shots: pd.DataFrame, min_attempts: int = 150, smoothing: float = 1.0
) -> pd.DataFrame:
    """One row per player, one column per (bucket, zone) cell, rows summing to 1.

    Laplace smoothing keeps every cell non-zero so divergences stay finite for players who
    simply never shoot from, say, the rim at 4 seconds.
    """
    df = shots.copy()
    df["BUCKET"] = assign_bucket(df.SHOT_CLOCK)
    df["ZONE"] = _zone(df)
    df = df.dropna(subset=["BUCKET"])

    counts = (
        df.groupby(["PLAYER_ID", "PLAYER_NAME", "BUCKET", "ZONE"], observed=True)
        .size()
        .rename("N")
        .reset_index()
    )
    wide = (
        counts.pivot_table(
            index=["PLAYER_ID", "PLAYER_NAME"], columns=["BUCKET", "ZONE"],
            values="N", fill_value=0, observed=True,
        )
        .reindex(columns=pd.MultiIndex.from_tuples(profile_cells()), fill_value=0)
    )
    totals = wide.sum(axis=1)
    wide = wide[totals >= min_attempts]
    totals = totals[totals >= min_attempts]

    smoothed = wide + smoothing
    profiles = smoothed.div(smoothed.sum(axis=1), axis=0)
    # FGA is stored under a two-level key so it cannot be mistaken for a distribution cell.
    # Assigning it as a bare "FGA" string silently became ('FGA', '') under these MultiIndex
    # columns, which let the raw attempt count leak into the divergence maths.
    profiles[("FGA", "")] = totals
    return profiles


def _cell_columns(profiles: pd.DataFrame) -> list[tuple[str, str]]:
    """The distribution columns only — never the FGA bookkeeping column."""
    return [c for c in profiles.columns if c[0] != "FGA"]


def _distribution(profiles: pd.DataFrame) -> np.ndarray:
    """Rows as probability vectors, re-normalised defensively."""
    values = profiles[_cell_columns(profiles)].to_numpy(dtype=float)
    sums = values.sum(axis=1, keepdims=True)
    if not np.allclose(sums, 1.0, atol=1e-6):
        values = values / sums
    return values


def _jensen_shannon(p: np.ndarray, q: np.ndarray) -> float:
    """JS divergence in bits, bounded [0, 1]. 0 = identical profiles, 1 = disjoint."""
    m = 0.5 * (p + q)
    def kl(a, b):
        return float(np.sum(a * np.log2(a / b)))
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def overlap_matrix(profiles: pd.DataFrame, player_ids: list[int] | None = None) -> pd.DataFrame:
    """Pairwise creation *similarity* (1 - JS divergence) among the given players.

    High similarity means the pair competes for the same possessions.
    """
    sub = profiles if player_ids is None else profiles[
        profiles.index.get_level_values("PLAYER_ID").isin(player_ids)
    ]
    names = sub.index.get_level_values("PLAYER_NAME")
    matrix = np.zeros((len(sub), len(sub)))
    values = _distribution(sub)

    for i in range(len(sub)):
        for j in range(i, len(sub)):
            sim = 1.0 - _jensen_shannon(values[i], values[j])
            matrix[i, j] = matrix[j, i] = sim
    return pd.DataFrame(matrix, index=names, columns=names)


def lineup_overlap(
    profiles: pd.DataFrame, player_ids: list[int], weight_by_volume: bool = True
) -> float:
    """A single overlap score for a group of players.

    Mean pairwise similarity, optionally weighted by the product of the pair's attempt
    volumes — because redundancy between two high-usage stars costs far more than the same
    redundancy between two bench players who rarely have the ball.
    """
    sub = profiles[profiles.index.get_level_values("PLAYER_ID").isin(player_ids)]
    if len(sub) < 2:
        return float("nan")

    values = _distribution(sub)
    volumes = sub[("FGA", "")].to_numpy(dtype=float)

    sims, weights = [], []
    for i in range(len(sub)):
        for j in range(i + 1, len(sub)):
            sims.append(1.0 - _jensen_shannon(values[i], values[j]))
            weights.append(volumes[i] * volumes[j] if weight_by_volume else 1.0)

    return float(np.average(sims, weights=weights))


def clock_share(shots: pd.DataFrame, player_ids: list[int]) -> pd.DataFrame:
    """Each player's share of attempts by shot-clock bucket — the readable view.

    Columns sum to 100% per player, so it answers "when does this player shoot?" rather
    than "how much does he shoot?".
    """
    df = shots[shots.PLAYER_ID.isin(player_ids)].copy()
    df["BUCKET"] = assign_bucket(df.SHOT_CLOCK)
    table = (
        df.groupby(["PLAYER_NAME", "BUCKET"], observed=True).size().rename("N").reset_index()
    )
    wide = table.pivot(index="PLAYER_NAME", columns="BUCKET", values="N").fillna(0)
    wide = wide.reindex(columns=BUCKET_ORDER, fill_value=0)
    return (wide.div(wide.sum(axis=1), axis=0) * 100).round(1)
