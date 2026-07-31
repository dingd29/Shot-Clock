"""Shot Quality Grade: separating shot selection from shot making.

A player's scoring efficiency confounds two different skills:

  * **Selection** - the quality of looks he generates or accepts, measured as mean xPTS per
    attempt. High means he takes rim shots and open threes; low means contested mid-range.
  * **Making**    - how much he beats the model, measured as (actual PTS - xPTS) per 100
    attempts. This is shot-making talent plus whatever the model cannot see.

They are close to orthogonal, and conflating them is why raw eFG% is a poor description of a
scorer. A high-volume mid-range shooter can be an excellent shot-maker and a poor shot
selector at the same time; the pair says something the single number cannot.

Because the model has no defender-proximity feature, "making" absorbs a player's ability to
score over tight contests. That is a real limitation and is stated in METHODOLOGY.md rather
than hidden.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.clock.validate import BUCKET_ORDER, assign_bucket


def grade_players(
    shots: pd.DataFrame, min_attempts: int = 200, by_season: bool = True
) -> pd.DataFrame:
    """Per-player selection and making. `shots` must carry an XPTS column."""
    keys = ["PLAYER_ID", "PLAYER_NAME"] + (["SEASON"] if by_season else [])
    grouped = shots.groupby(keys, observed=True).agg(
        FGA=("XPTS", "size"),
        XPTS_TOTAL=("XPTS", "sum"),
        PTS_TOTAL=("PTS", "sum"),
        TEAM=("TEAM_ABBREVIATION", "last") if "TEAM_ABBREVIATION" in shots else ("XPTS", "size"),
    )
    grouped = grouped[min_attempts <= grouped.FGA].reset_index()

    grouped["SELECTION"] = grouped.XPTS_TOTAL / grouped.FGA
    grouped["MAKING_PER_100"] = (grouped.PTS_TOTAL - grouped.XPTS_TOTAL) / grouped.FGA * 100
    grouped["PTS_PER_ATTEMPT"] = grouped.PTS_TOTAL / grouped.FGA

    # Standard error of the making component, for filtering noise from real signal.
    # Var(points per attempt) is dominated by make/miss variance; ~1.1 pts is a good
    # approximation of the per-shot SD across the league.
    grouped["MAKING_SE_PER_100"] = 1.1 / np.sqrt(grouped.FGA) * 100
    return grouped.sort_values("MAKING_PER_100", ascending=False).reset_index(drop=True)


def grade_by_clock(
    shots: pd.DataFrame, min_attempts: int = 40, by_season: bool = False
) -> pd.DataFrame:
    """Selection and making split by shot-clock bucket.

    This is the piece that needs the reconstruction: it identifies who holds up when a
    possession breaks down versus who only produces with time on the clock.
    """
    df = shots.copy()
    df["BUCKET"] = assign_bucket(df.SHOT_CLOCK)
    keys = ["PLAYER_ID", "PLAYER_NAME", "BUCKET"] + (["SEASON"] if by_season else [])

    grouped = (
        df.groupby(keys, observed=True)
        .agg(FGA=("XPTS", "size"), XPTS_TOTAL=("XPTS", "sum"), PTS_TOTAL=("PTS", "sum"))
        .reset_index()
    )
    grouped = grouped[min_attempts <= grouped.FGA]
    grouped["SELECTION"] = grouped.XPTS_TOTAL / grouped.FGA
    grouped["MAKING_PER_100"] = (grouped.PTS_TOTAL - grouped.XPTS_TOTAL) / grouped.FGA * 100
    grouped["BUCKET"] = pd.Categorical(grouped.BUCKET, categories=BUCKET_ORDER, ordered=True)
    return grouped.sort_values(["PLAYER_NAME", "BUCKET"]).reset_index(drop=True)


def late_clock_specialists(
    shots: pd.DataFrame, min_late: int = 60, min_early: int = 100
) -> pd.DataFrame:
    """Players ranked by how much better they make shots late in the clock than early.

    Late = 7 seconds or fewer (the region where league efficiency collapses); early = more
    than 15. A positive delta means the player's shot-making holds up under time pressure —
    the bail-out creator archetype teams pay for and box scores cannot identify.
    """
    df = shots.copy()
    df["LATE"] = df.SHOT_CLOCK <= 7
    df["EARLY"] = df.SHOT_CLOCK > 15

    def side(mask: pd.Series, label: str) -> pd.DataFrame:
        sub = df[mask]
        out = (
            sub.groupby(["PLAYER_ID", "PLAYER_NAME"], observed=True)
            .agg(FGA=("XPTS", "size"), XPTS_TOTAL=("XPTS", "sum"), PTS_TOTAL=("PTS", "sum"))
            .reset_index()
        )
        out[f"MAKING_{label}"] = (out.PTS_TOTAL - out.XPTS_TOTAL) / out.FGA * 100
        out[f"SELECTION_{label}"] = out.XPTS_TOTAL / out.FGA
        return out.rename(columns={"FGA": f"FGA_{label}"})[
            ["PLAYER_ID", "PLAYER_NAME", f"FGA_{label}", f"MAKING_{label}", f"SELECTION_{label}"]
        ]

    late, early = side(df.LATE, "LATE"), side(df.EARLY, "EARLY")
    merged = late.merge(early, on=["PLAYER_ID", "PLAYER_NAME"], how="inner")
    merged = merged[(min_late <= merged.FGA_LATE) & (min_early <= merged.FGA_EARLY)]
    merged["LATE_MINUS_EARLY"] = merged.MAKING_LATE - merged.MAKING_EARLY

    # Raw late-minus-early is almost pure noise at the top: a player with 60 late attempts
    # has a standard error near 14 points per 100, so the leaderboard would otherwise rank
    # small samples that regressed hard in one direction. Shrink toward zero by the ratio of
    # signal variance to total variance (James-Stein), and rank on the shrunk estimate.
    per_shot_sd = 1.1
    merged["SE_DIFF"] = per_shot_sd * np.sqrt(1 / merged.FGA_LATE + 1 / merged.FGA_EARLY) * 100

    observed_var = merged.LATE_MINUS_EARLY.var()
    noise_var = (merged.SE_DIFF**2).mean()
    signal_var = max(observed_var - noise_var, 0.0)

    merged["SHRUNK_LATE_MINUS_EARLY"] = merged.LATE_MINUS_EARLY * (
        signal_var / (signal_var + merged.SE_DIFF**2)
    )
    merged.attrs["signal_share"] = signal_var / observed_var if observed_var else 0.0
    return merged.sort_values("SHRUNK_LATE_MINUS_EARLY", ascending=False).reset_index(drop=True)
