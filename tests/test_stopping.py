"""Tests for the optimal-stopping model.

The estimator has to recover a known exercise threshold from synthetic chances, and it has to
*fail* to find one when the data contains none. Both matter here more than usual, because the
headline claim is about the shape of a boundary rather than a coefficient with a standard
error.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.stopping import (
    continuation_value,
    exercise_boundary,
    exercise_gap,
    relaxation,
)


def synthetic_chances(n: int = 40_000, seed: int = 0) -> pd.DataFrame:
    """Chances that start at 24, end uniformly, and score more when they end early.

    Built so the continuation value must rise with time remaining: a chance with more clock
    left has more ways to finish well.
    """
    rng = np.random.default_rng(seed)
    start = np.full(n, 24.0)
    end = rng.integers(0, 24, n).astype(float)
    # Longer-lived chances are worse, which is what makes V(t) increasing in t.
    quality = 1.2 - 0.03 * (24 - end)
    points = rng.binomial(1, np.clip(quality / 2.4, 0.01, 0.99), n) * 2.0
    return pd.DataFrame(
        {
            "START_SC": start,
            "END_SC": end,
            "PTS_FG": points,
            "PTS_ALL": points,
            "START_TYPE": "def_rebound",
        }
    )


def test_continuation_value_rises_with_time_remaining():
    """More clock is worth more. If this inverts, the live/continued masks are wrong."""
    values = continuation_value(synthetic_chances(), min_chances=50)
    assert len(values) > 10
    correlation = np.corrcoef(values.SECOND, values.V_CONT)[0, 1]
    assert correlation > 0.8, f"V(t) should increase with t, got r={correlation:.2f}"


def test_continuation_value_excludes_chances_ending_now():
    """V(t) is the value of *declining*, so a chance ending exactly at t must not count."""
    panel = pd.DataFrame(
        {
            "START_SC": [24.0, 24.0, 24.0],
            "END_SC": [10.0, 10.0, 5.0],
            "PTS_FG": [0.0, 0.0, 3.0],
            "PTS_ALL": [0.0, 0.0, 3.0],
            "START_TYPE": "def_rebound",
        }
    )
    values = continuation_value(panel, min_chances=1).set_index("SECOND")
    # At t=10 two chances end and one continues; only the continuing one counts.
    assert values.loc[10, "V_CONT"] == pytest.approx(3.0)
    assert values.loc[10, "N_CONTINUED"] == 1


def test_boundary_recovers_a_known_threshold():
    """Shots generated under a hard rule should show that rule as the accepted floor."""
    rng = np.random.default_rng(3)
    threshold = 0.9
    quality = rng.uniform(0.2, 1.6, 30_000)
    taken = quality >= threshold
    shots = pd.DataFrame(
        {"XPTS": quality[taken], "SHOT_CLOCK": rng.integers(5, 20, taken.sum()).astype(float)}
    )
    values = pd.DataFrame({"SECOND": range(0, 25), "V_CONT": 0.7})

    boundary = exercise_boundary(shots, values, quantile=0.01, min_shots=50)
    assert boundary.BOUNDARY.min() >= threshold - 0.05
    assert boundary.BOUNDARY.max() <= threshold + 0.10


def test_premature_share_is_zero_when_every_shot_beats_continuation():
    shots = pd.DataFrame(
        {"XPTS": np.full(1000, 1.2), "SHOT_CLOCK": np.full(1000, 10.0)}
    )
    values = pd.DataFrame({"SECOND": [10], "V_CONT": [0.7]})
    gap = exercise_gap(shots, values, min_shots=10)
    assert gap.PREMATURE_SHARE.iloc[0] == 0.0
    assert gap.MEAN_SURPLUS.iloc[0] == pytest.approx(0.5)


def test_relaxation_ratio_is_one_when_the_boundary_tracks_value():
    """A team that lowers its standard exactly as fast as V falls scores a ratio near 1.

    This is the null the real result is measured against — the NBA figure is roughly 0.5, so
    the estimator has to be able to return 1 when the behaviour is actually optimal.
    """
    rng = np.random.default_rng(5)
    seconds, rows = np.arange(1, 24), []
    for second in seconds:
        value = 0.30 + 0.022 * second
        # Accept anything above V(t) exactly: the optimal rule.
        quality = value + rng.exponential(0.35, 4000)
        rows.append(pd.DataFrame({"XPTS": quality, "SHOT_CLOCK": float(second)}))
    shots = pd.concat(rows, ignore_index=True)
    values = pd.DataFrame({"SECOND": seconds, "V_CONT": 0.30 + 0.022 * seconds})

    ratios = relaxation(shots, values, quantiles=(0.05, 0.10))
    assert ratios.relaxation_ratio.min() > 0.85, ratios.to_string()
    assert ratios.excess_late_demand.abs().max() < 0.05
