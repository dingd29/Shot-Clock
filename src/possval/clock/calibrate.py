"""Calibrate inbound delays against shot-clock violations.

The shot clock does not start when a dead-ball event is logged; it starts when the inbound
pass is touched, some seconds later. Ignoring that makes every dead-ball possession look
longer than it was, which pushes reconstructed clocks too low.

The delay is estimated from an independent signal: at a shot-clock-violation turnover the
true clock is **exactly 0** by definition. Running the reconstruction with the underflow
guard disabled gives an uncensored error at those events, and the delay that zeroes the
median error is the estimate.

Why this matters methodologically: calibration never touches the official NBA aggregates,
so those remain a clean holdout for validation. Fitting the delay to the bucket
distribution we are trying to reproduce would make the validation circular.
"""

from __future__ import annotations

import pandas as pd

from possval.clock import rules as R
from possval.clock.reconstruct import DEFAULT_INBOUND_DELAY, reconstruct_season

# Chance types that begin on a dead ball, so an inbound must occur before the clock starts.
DEAD_BALL_STARTS = tuple(DEFAULT_INBOUND_DELAY.keys())

# Live-ball starts have no inbound and therefore no delay by construction.
LIVE_BALL_STARTS = ("def_rebound", "off_rebound")


def violation_errors(pbp_with_clock: pd.DataFrame) -> pd.DataFrame:
    """Reconstruction error at every shot-clock violation (truth = 0, so error = raw clock)."""
    mask = (pbp_with_clock.EVENTMSGTYPE == R.TURNOVER) & (
        pbp_with_clock.EVENTMSGACTIONTYPE == R.SHOT_CLOCK_VIOLATION_ACTION
    )
    return pbp_with_clock.loc[mask, ["CHANCE_START_TYPE", "RAW_SHOT_CLOCK", "GAME_ID"]]


def estimate_delays(
    pbp: pd.DataFrame,
    season: int,
    min_events: int = 30,
    max_delay: float = 6.0,
) -> tuple[dict[str, float], pd.DataFrame]:
    """Estimate per-start-type inbound delay, in seconds.

    Runs uncensored (underflow guard off) so violations that our clock overshot show up as
    negative error rather than being converted into an inferred reset.

    A negative median error means the clock hit zero early, i.e. we over-counted elapsed
    time, i.e. the chance started later than we assumed -> positive delay.
    """
    recon = reconstruct_season(
        pbp, season, progress=False, delays={}, disable_underflow_guard=True
    )
    errors = violation_errors(recon)

    stats = (
        errors.groupby("CHANCE_START_TYPE")
        .RAW_SHOT_CLOCK.agg(["count", "mean", "median"])
        .rename(columns={"median": "median_error", "mean": "mean_error"})
    )

    delays: dict[str, float] = {}
    for kind in DEAD_BALL_STARTS:
        if kind not in stats.index or stats.loc[kind, "count"] < min_events:
            continue
        delay = -float(stats.loc[kind, "median_error"])
        # A negative delay would mean the clock starts *before* the whistle, which is not
        # physical; clamp to a plausible inbound range.
        delays[kind] = float(min(max(delay, 0.0), max_delay))

    return delays, stats.reset_index()
