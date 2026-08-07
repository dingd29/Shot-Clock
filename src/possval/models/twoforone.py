"""The 2-for-1, priced. Pre-registered in `reports/preregistration_twoforone.md`.

Late in a period an offense can shoot early — giving up continuation value — to get the ball
back before the buzzer. The benefit is public folklore. The cost is `V(t_early) − V(t_normal)`,
and pricing it needs a per-shot clock.

The identification is the reason this question was chosen over the team-level ones that failed:
**when an offense gains the ball is decided by the opponent's previous possession**, so whether
a 2-for-1 is even available is close to exogenous. Treatment is therefore *feasibility*, not the
team's decision to take it. Conditioning on teams that actually went fast would put the choice
back into the estimate and rebuild the selection problem the design exists to avoid.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Fixed in the pre-registration. The opponent can use 24 seconds and a deliberate play takes
# roughly 8, so a 2-for-1 needs about 32 on the clock. Chosen on mechanics before any data was
# looked at; the registered sweep in `threshold_sweep` reports 28 through 36 in full.
FEASIBLE_FROM = 32.0
WINDOW = (24.0, 45.0)
THRESHOLD_SWEEP = tuple(float(t) for t in range(28, 37))

# Overtime is five minutes and its end-of-period behaviour differs; excluded rather than pooled.
REGULATION_PERIODS = (1, 2, 3, 4)


def period_sides(frame: pd.DataFrame, keys: list[str], team: str = "TEAM") -> pd.Series:
    """Label each row 0 or 1 by which of a period's two teams owns it.

    The obvious version — `s != s.iloc[0]` — has a failure mode that destroys whole periods.
    When the first row's team is missing, `NaN != NaN` is True, so *every* row compares unequal
    to the reference and the entire period collapses onto one side. Its points then all
    accumulate to a single team and the net-points accounting comes out inverted. That hit 613
    periods and 25,889 possession pairs, and it was the residual bias left in the handover
    identity after the possession-boundary fix.

    Anchoring on the first **non-null** team removes the whole-period failure. Rows whose own
    team is unknown are returned as NaN rather than guessed at, so callers can drop them
    instead of silently attributing their points to whichever side sorts first.
    """

    def label(s: pd.Series) -> pd.Series:
        known = s.dropna()
        if known.empty:
            return pd.Series(np.nan, index=s.index)
        return s.ne(known.iloc[0]).astype(float).where(s.notna())

    return frame.groupby(keys, sort=False)[team].transform(label)


def net_points_to_period_end(panel: pd.DataFrame) -> pd.DataFrame:
    """Points the team in possession scores from here to the buzzer, minus the opponent's.

    A 2-for-1 trades shot quality for possession count, so only a net measure prices both
    sides. Anything one-sided rewards taking more possessions regardless of what they produce.
    """
    frame = panel.sort_values(["GAME_ID", "PERIOD", "CHANCE_ID"]).copy()
    keys = ["GAME_ID", "PERIOD"]

    # Each period has exactly two teams. Accumulate each side's points backwards from the
    # buzzer, then read off whichever side owns the chance.
    frame["SIDE"] = period_sides(frame, keys)
    for side in (0, 1):
        points = frame.PTS_FG.where(frame.SIDE == side, 0.0)
        grouped = points.groupby([frame.GAME_ID, frame.PERIOD], sort=False)
        # Reverse cumulative sum, inclusive of the current chance.
        frame[f"REST_{side}"] = grouped.transform("sum") - grouped.cumsum() + points

    own = np.where(frame.SIDE == 0, frame.REST_0, frame.REST_1)
    opponent = np.where(frame.SIDE == 0, frame.REST_1, frame.REST_0)
    frame["PTS_REST_OWN"] = np.where(frame.SIDE.isna(), np.nan, own)
    frame["PTS_REST_OPP"] = np.where(frame.SIDE.isna(), np.nan, opponent)
    frame["NET_REST"] = frame.PTS_REST_OWN - frame.PTS_REST_OPP
    return frame.drop(columns=["REST_0", "REST_1"])


def window(panel: pd.DataFrame, bounds: tuple[float, float] = WINDOW) -> pd.DataFrame:
    """End-of-period chances where a 2-for-1 is plausibly in play.

    `PREV_GC` — the game clock when the previous chance's last event was logged — is the moment
    this offense gained the ball. It is the running variable, and it is set by the opponent.
    """
    low, high = bounds
    frame = net_points_to_period_end(panel)
    frame = frame[
        frame.PREV_GC.between(low, high)
        & frame.PERIOD.isin(REGULATION_PERIODS)
        & frame.LAST_GC.notna()
    ].copy()
    frame["CLOCK_USED"] = frame.PREV_GC - frame.LAST_GC
    # A negative elapsed time is an ordering artefact in the feed, 0.28% of chances overall.
    # Dropped rather than clipped: a chance whose events cannot be ordered has no duration.
    # `NET_REST` is null where a period contains a chance with no identifiable offensive team,
    # so its points cannot be split between two sides; those periods are dropped rather than
    # half-attributed.
    return frame[(frame.CLOCK_USED >= 0) & frame.NET_REST.notna()]


def _clustered_covariance(
    design: np.ndarray, residual: np.ndarray, clusters: np.ndarray
) -> tuple[np.ndarray, int]:
    """Cluster-robust covariance, grouping by whole games.

    Boundaries come from an inequality rather than `np.diff`, which cannot subtract the string
    game ids the feed uses.
    """
    order = np.argsort(clusters, kind="stable")
    sorted_clusters = clusters[order]
    boundaries = np.flatnonzero(sorted_clusters[1:] != sorted_clusters[:-1]) + 1

    bread = np.linalg.pinv(design.T @ design)
    meat = np.zeros((design.shape[1], design.shape[1]))
    for block in np.split(order, boundaries):
        score = design[block].T @ residual[block]
        meat += np.outer(score, score)
    n_clusters = len(boundaries) + 1
    return (n_clusters / max(n_clusters - 1, 1)) * bread @ meat @ bread, n_clusters


def _clustered_difference(frame: pd.DataFrame, outcome: str, threshold: float) -> dict:
    """Mean outcome above the threshold minus below, with game-clustered standard errors.

    Chances within a game are not independent — the same two teams, the same night — and four
    period-ends per game land in this window.
    """
    above = frame.PREV_GC >= threshold
    y = frame[outcome].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(frame)), above.to_numpy(dtype=float)])
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ coefficients

    covariance, n_clusters = _clustered_covariance(
        design, residual, frame.GAME_ID.to_numpy()
    )
    error = float(np.sqrt(max(covariance[1, 1], 0.0)))

    return {
        "outcome": outcome,
        "threshold": threshold,
        "n_below": int((~above).sum()),
        "n_above": int(above.sum()),
        "mean_below": float(y[~above].mean()),
        "mean_above": float(y[above].mean()),
        "difference": float(coefficients[1]),
        "std_error": error,
        "t": float(coefficients[1] / error) if error else np.nan,
        "n_games": n_clusters,
    }


def _local_linear_difference(
    frame: pd.DataFrame, outcome: str, threshold: float, bandwidth: float = 6.0
) -> dict:
    """The same jump, net of the trend in `PREV_GC` on each side.

    Registered in advance because the raw difference is confounded by construction: net points
    to the end of a period rises with time left, for whoever happens to have the ball. Fitting a
    slope on each side of the threshold and reading the gap at the threshold removes the part of
    the difference that is just "more time remaining".
    """
    local = frame[(frame.PREV_GC - threshold).abs() <= bandwidth]
    centred = local.PREV_GC.to_numpy(dtype=float) - threshold
    above = (centred >= 0).astype(float)
    design = np.column_stack([np.ones(len(local)), above, centred, above * centred])
    y = local[outcome].to_numpy(dtype=float)
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ coefficients

    covariance, n_clusters = _clustered_covariance(
        design, residual, local.GAME_ID.to_numpy()
    )
    error = float(np.sqrt(max(covariance[1, 1], 0.0)))

    return {
        "outcome": outcome,
        "threshold": threshold,
        "bandwidth": bandwidth,
        "n": len(local),
        "jump": float(coefficients[1]),
        "std_error": error,
        "t": float(coefficients[1] / error) if error else np.nan,
        "n_games": n_clusters,
    }


def discontinuity(frame: pd.DataFrame, threshold: float = FEASIBLE_FROM) -> pd.DataFrame:
    """H6a and H6b at one threshold, raw and trend-adjusted."""
    rows = []
    for outcome in ("CLOCK_USED", "NET_REST"):
        raw = _clustered_difference(frame, outcome, threshold)
        rows.append({"estimator": "raw difference", **raw})
        local = _local_linear_difference(frame, outcome, threshold)
        rows.append(
            {
                "estimator": "local linear",
                "outcome": outcome,
                "threshold": threshold,
                "n_below": np.nan,
                "n_above": local["n"],
                "mean_below": np.nan,
                "mean_above": np.nan,
                "difference": local["jump"],
                "std_error": local["std_error"],
                "t": local["t"],
                "n_games": local["n_games"],
            }
        )
    return pd.DataFrame(rows)


def threshold_sweep(
    frame: pd.DataFrame, thresholds: tuple[float, ...] = THRESHOLD_SWEEP
) -> pd.DataFrame:
    """Every threshold from 28 to 36, reported in full.

    The registered threshold is 32, chosen on mechanics. This sweep exists so that a result
    holding at one cell and nowhere else is visible rather than concealed.
    """
    return pd.concat(
        [discontinuity(frame, threshold) for threshold in thresholds], ignore_index=True
    )


def profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Clock used and net points against `PREV_GC`, one-second bins.

    The picture behind the test. If teams run 2-for-1s at all, clock used has to fall as the
    running variable crosses into the feasible region.
    """
    binned = frame.assign(GC_BIN=frame.PREV_GC.round().astype(int))
    return (
        binned.groupby("GC_BIN")
        .agg(
            N=("CLOCK_USED", "size"),
            CLOCK_USED=("CLOCK_USED", "mean"),
            NET_REST=("NET_REST", "mean"),
            PTS_OWN=("PTS_REST_OWN", "mean"),
            PTS_OPP=("PTS_REST_OPP", "mean"),
            START_SC=("START_SC", "mean"),
        )
        .reset_index()
    )


def cost_of_shooting_early(
    frame: pd.DataFrame, values: pd.DataFrame, threshold: float = FEASIBLE_FROM
) -> dict:
    """H6c, descriptive: what the early shot gives up, in continuation value.

    Registered as a magnitude rather than a test. `END_SC` is where the chance finished on the
    shot clock, so `V(END_SC)` is what the offense held when it stopped; the difference between
    the feasible and infeasible sides is the option value handed over to buy the extra
    possession.
    """
    lookup = values.set_index("SECOND").V_CONT
    local = frame.assign(SECOND=frame.END_SC.round().clip(0, 24).astype(int))
    local = local.assign(V_AT_STOP=local.SECOND.map(lookup)).dropna(subset=["V_AT_STOP"])
    above = local[local.PREV_GC >= threshold]
    below = local[local.PREV_GC < threshold]
    return {
        "n_above": len(above),
        "n_below": len(below),
        "mean_end_sc_above": float(above.END_SC.mean()),
        "mean_end_sc_below": float(below.END_SC.mean()),
        "v_at_stop_above": float(above.V_AT_STOP.mean()),
        "v_at_stop_below": float(below.V_AT_STOP.mean()),
        "forgone_continuation_value": float(above.V_AT_STOP.mean() - below.V_AT_STOP.mean()),
    }
