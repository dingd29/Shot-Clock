"""Validate the reconstruction against NBA's own published shot-clock aggregates.

This is the project's go/no-go gate. The reconstruction invents a field that does not exist
in the source data, so it is only credible if it reproduces numbers NBA publishes
independently. `data/reference/official_shotclock_2024_25.csv` holds nba.com's official
2024-25 per-player, per-bucket splits (scraped Nov 2025).

Three axes, in increasing order of strictness:
  1. League-wide FGA share per bucket  - is the distribution of shots across the clock right?
  2. League-wide FG% / eFG% per bucket - do the efficiency splits line up?
  3. Per-player FGA and FG% agreement  - R^2 and MAE on ~3.2k player-bucket cells.

Caveat that matters for axis 3: the reference file is *per game*, so reconstructed totals
are divided by the player's games played before comparison.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.paths import OFFICIAL_SHOTCLOCK_2024_25

# The four possession starts that account for essentially all shots once the clock is high.
# Finding 3 reports shares *among these*, which matters: at 20 seconds they are 99% of
# attempts, but at 5 seconds only 75%, the rest being made free throws and defensive fouls.
# Comparing a 5-second share against a 20-second one is comparing different denominators
# unless that is said out loud.
MAIN_START_TYPES = ("after_made_fg", "after_turnover", "def_rebound", "off_rebound")

# "Early clock" for the transition argument in finding 3: at least this many seconds left.
HIGH_CLOCK_SECONDS = 20

# NBA's published buckets, in clock order. Upper bound exclusive, lower bound inclusive,
# except the final bucket which includes 0.
BUCKETS: list[tuple[str, float, float]] = [
    ("24-22", 22.0, 24.0),
    ("22-18", 18.0, 22.0),
    ("18-15", 15.0, 18.0),
    ("15-7", 7.0, 15.0),
    ("7-4", 4.0, 7.0),
    ("4-0", 0.0, 4.0),
]
BUCKET_ORDER = [b[0] for b in BUCKETS]


def assign_bucket(shot_clock: pd.Series) -> pd.Series:
    """Bin a continuous shot clock into NBA's six published ranges."""
    edges = [0.0, 4.0, 7.0, 15.0, 18.0, 22.0, np.inf]
    labels = ["4-0", "7-4", "15-7", "18-15", "22-18", "24-22"]
    binned = pd.cut(shot_clock, bins=edges, labels=labels, right=False, include_lowest=True)
    return binned.cat.reorder_categories(BUCKET_ORDER, ordered=True)


def load_official() -> pd.DataFrame:
    df = pd.read_csv(OFFICIAL_SHOTCLOCK_2024_25)
    df.columns = df.columns.str.strip()
    for col in ("FGM", "FGA", "FG3M", "FG3A", "FG2M", "FG2A", "GP"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["SHOT_CLOCK_RANGE"] = pd.Categorical(
        df["SHOT_CLOCK_RANGE"], categories=BUCKET_ORDER, ordered=True
    )
    return df


def build_reconstructed_shots(shots_with_clock: pd.DataFrame) -> pd.DataFrame:
    """Shot-level frame -> per (player, bucket) totals, mirroring the official schema."""
    df = shots_with_clock.copy()
    df["BUCKET"] = assign_bucket(df["SHOT_CLOCK"])
    df["IS_3"] = (df["SHOT_TYPE"].astype(str).str.startswith("3")).astype(int)
    df["FG3M"] = df["IS_3"] * df["SHOT_MADE_FLAG"]

    agg = (
        df.groupby(["PLAYER_ID", "BUCKET"], observed=True)
        .agg(
            FGA=("SHOT_ATTEMPTED_FLAG", "sum"),
            FGM=("SHOT_MADE_FLAG", "sum"),
            FG3A=("IS_3", "sum"),
            FG3M=("FG3M", "sum"),
        )
        .reset_index()
    )
    agg["EFG_PCT"] = (agg.FGM + 0.5 * agg.FG3M) / agg.FGA.replace(0, np.nan)
    agg["FG_PCT"] = agg.FGM / agg.FGA.replace(0, np.nan)
    return agg


def _league_table(fga, fgm, fg3m, labels) -> pd.DataFrame:
    total = float(np.sum(fga))
    return pd.DataFrame(
        {
            "BUCKET": labels,
            "FGA_SHARE": np.asarray(fga, dtype=float) / total,
            "FG_PCT": np.asarray(fgm, dtype=float) / np.asarray(fga, dtype=float),
            "EFG_PCT": (np.asarray(fgm, dtype=float) + 0.5 * np.asarray(fg3m, dtype=float))
            / np.asarray(fga, dtype=float),
        }
    )


def compare_league_wide(recon: pd.DataFrame, official: pd.DataFrame) -> pd.DataFrame:
    """Axis 1 + 2: bucket-level FGA share and shooting efficiency."""
    r = recon.groupby("BUCKET", observed=True)[["FGA", "FGM", "FG3M"]].sum().reindex(BUCKET_ORDER)
    o = (
        official.groupby("SHOT_CLOCK_RANGE", observed=True)[["FGA", "FGM", "FG3M"]]
        .sum()
        .reindex(BUCKET_ORDER)
    )

    rt = _league_table(r.FGA, r.FGM, r.FG3M, BUCKET_ORDER)
    ot = _league_table(o.FGA, o.FGM, o.FG3M, BUCKET_ORDER)

    out = rt.merge(ot, on="BUCKET", suffixes=("_recon", "_official"))
    out["SHARE_DIFF_PP"] = (out.FGA_SHARE_recon - out.FGA_SHARE_official) * 100
    out["FG_PCT_DIFF_PP"] = (out.FG_PCT_recon - out.FG_PCT_official) * 100
    out["EFG_DIFF_PP"] = (out.EFG_PCT_recon - out.EFG_PCT_official) * 100
    return out


def compare_per_player(recon: pd.DataFrame, official: pd.DataFrame) -> dict:
    """Axis 3: join on (player, bucket) and score agreement on per-game FGA and FG%."""
    off = official[["PLAYER_ID", "SHOT_CLOCK_RANGE", "FGA", "FG_PCT", "GP"]].rename(
        columns={"SHOT_CLOCK_RANGE": "BUCKET", "FGA": "FGA_PG_OFF", "FG_PCT": "FG_PCT_OFF"}
    )
    rec = recon[["PLAYER_ID", "BUCKET", "FGA", "FG_PCT"]].rename(
        columns={"FGA": "FGA_TOT_REC", "FG_PCT": "FG_PCT_REC"}
    )
    merged = off.merge(rec, on=["PLAYER_ID", "BUCKET"], how="inner")
    merged["FGA_PG_REC"] = merged.FGA_TOT_REC / merged.GP.replace(0, np.nan)
    merged = merged.dropna(subset=["FGA_PG_REC", "FGA_PG_OFF"])

    def r2(a, b):
        a, b = np.asarray(a, float), np.asarray(b, float)
        ss_res = np.sum((a - b) ** 2)
        ss_tot = np.sum((a - np.mean(a)) ** 2)
        return 1 - ss_res / ss_tot if ss_tot else np.nan

    fg = merged.dropna(subset=["FG_PCT_REC", "FG_PCT_OFF"])
    fg = fg[fg.FGA_TOT_REC >= 20]  # FG% is meaningless on tiny samples

    return {
        "n_cells": len(merged),
        "fga_r2": r2(merged.FGA_PG_OFF, merged.FGA_PG_REC),
        "fga_mae": float(np.mean(np.abs(merged.FGA_PG_OFF - merged.FGA_PG_REC))),
        "fga_corr": float(merged.FGA_PG_OFF.corr(merged.FGA_PG_REC)),
        "n_cells_fgpct": len(fg),
        "fgpct_r2": r2(fg.FG_PCT_OFF, fg.FG_PCT_REC),
        "fgpct_mae_pp": float(np.mean(np.abs(fg.FG_PCT_OFF - fg.FG_PCT_REC)) * 100),
        "fgpct_corr": float(fg.FG_PCT_OFF.corr(fg.FG_PCT_REC)),
    }


def report(shots_with_clock: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    official = load_official()
    recon = build_reconstructed_shots(shots_with_clock)
    return compare_league_wide(recon, official), compare_per_player(recon, official)


def low_confidence_sensitivity(season: int = 2024) -> pd.DataFrame:
    """Put the dropped low-confidence shots back and see whether finding 3 survives.

    The reconstruction sets the clock to NaN wherever a reset had to be invented, and those
    rows are dropped rather than imputed — the right default, since fabricating a 24 would
    corrupt the bucket distribution more than dropping does (METHODOLOGY §2).

    But the drop is **not random**: low-confidence rows concentrate in the high-clock region,
    which is precisely where finding 3 lives. So the finding is drawn from data missing
    disproportionately at its own end, and that deserves a test rather than an argument.

    Three bases are compared over the high-clock region:

    ``dropped``        the default — 4.2% of shots absent.
    ``imputed``        every dropped shot restored at its chance's start value (24, or 14 for
                       a frontcourt reset). 86% of them carry an ``inferred_*`` start type,
                       meaning the reconstruction could not classify how the chance began, so
                       they contribute no start type of their own.
    ``worst case``     the same restoration, but every unclassifiable shot is *counted as a
                       half-court start*. This is the most adverse assumption available:
                       finding 3 claims the early clock is dominated by transition, and this
                       hands every ambiguous attempt to the other side.

    If the conclusion holds under the third basis it cannot be an artifact of the missingness.
    """
    from possval.clock import rules as R
    from possval.ingest import load_season
    from possval.paths import PROCESSED

    recon = pd.read_parquet(
        PROCESSED / f"pbp_clock_{season}.parquet",
        columns=["GAME_ID", "EVENTNUM", "SHOT_CLOCK", "CHANCE_START_TYPE"],
    )
    shots = load_season("shotdetail", season)[["GAME_ID", "GAME_EVENT_ID"]]
    merged = shots.merge(
        recon.rename(columns={"EVENTNUM": "GAME_EVENT_ID"}),
        on=["GAME_ID", "GAME_EVENT_ID"],
        how="inner",
    )

    short = R.short_reset_value(season)
    fallback = np.where(merged.CHANCE_START_TYPE == "off_rebound", short, R.FULL_CLOCK)
    merged["IMPUTED"] = merged.SHOT_CLOCK.fillna(pd.Series(fallback, index=merged.index))
    merged["WAS_DROPPED"] = merged.SHOT_CLOCK.isna()

    worst = merged.CHANCE_START_TYPE.where(
        ~(merged.WAS_DROPPED & ~merged.CHANCE_START_TYPE.isin(MAIN_START_TYPES)),
        "after_made_fg",
    )

    bases = [
        ("dropped (default)", merged[~merged.WAS_DROPPED], "SHOT_CLOCK", None),
        ("imputed at chance start", merged, "IMPUTED", None),
        ("worst case: unclassified = half-court", merged, "IMPUTED", worst),
    ]

    rows = []
    for label, frame, column, override in bases:
        second = frame[column].round().clip(0, 24)
        starts = (override.loc[frame.index] if override is not None
                  else frame.CHANCE_START_TYPE)
        high = starts[second >= HIGH_CLOCK_SECONDS]
        main = high[high.isin(MAIN_START_TYPES)]
        share = main.value_counts(normalize=True) * 100
        transition = float(share.get("after_turnover", 0) + share.get("def_rebound", 0))
        rows.append(
            {
                "basis": label,
                "n_shots": len(high),
                "half_court_pct": round(float(share.get("after_made_fg", 0)), 1),
                "transition_pct": round(transition, 1),
            }
        )
    return pd.DataFrame(rows)
