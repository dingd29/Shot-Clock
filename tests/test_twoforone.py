"""Tests for the 2-for-1 design.

The outcome is the fragile part. "Net points from here to the buzzer" has to look forward only,
respect period boundaries, and flip sign correctly depending on which team holds the ball — and
a sign error there would produce a clean, significant, backwards result.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.twoforone import (
    _clustered_difference,
    net_points_to_period_end,
    profile,
    threshold_sweep,
    window,
)


def _period(rows, game="G1", period=1) -> pd.DataFrame:
    """(TEAM, PTS_FG) in chance order within one period."""
    return pd.DataFrame(
        {
            "GAME_ID": game,
            "PERIOD": period,
            "CHANCE_ID": range(len(rows)),
            "TEAM": [r[0] for r in rows],
            "PTS_FG": [float(r[1]) for r in rows],
        }
    )


def test_net_points_looks_forward_and_flips_sign_per_team():
    panel = _period([("A", 2), ("B", 3), ("A", 0), ("B", 2)])
    out = net_points_to_period_end(panel)
    # From chance 0 (A's): A scores 2, B scores 5  -> net -3.
    # From chance 1 (B's): B scores 5, A scores 0  -> net +5.
    # From chance 2 (A's): A scores 0, B scores 2  -> net -2.
    # From chance 3 (B's): B scores 2, A scores 0  -> net +2.
    assert list(out.NET_REST) == [-3.0, 5.0, -2.0, 2.0]
    assert list(out.PTS_REST_OWN) == [2.0, 5.0, 0.0, 2.0]
    assert list(out.PTS_REST_OPP) == [5.0, 0.0, 2.0, 0.0]


def test_the_last_chance_of_a_period_sees_only_itself():
    out = net_points_to_period_end(_period([("A", 2), ("B", 3)]))
    assert out.NET_REST.iloc[-1] == pytest.approx(3.0)


def test_periods_do_not_leak_into_one_another():
    panel = pd.concat(
        [_period([("A", 2)]), _period([("B", 3)], period=2)], ignore_index=True
    )
    out = net_points_to_period_end(panel)
    # A's lone first-period chance must not see B's second-period basket.
    assert out.NET_REST.iloc[0] == pytest.approx(2.0)


def test_games_do_not_leak_into_one_another():
    panel = pd.concat(
        [_period([("A", 2)]), _period([("C", 3)], game="G2")], ignore_index=True
    )
    out = net_points_to_period_end(panel)
    assert out.NET_REST.iloc[0] == pytest.approx(2.0)


def _window_panel(n=4000, seed=0, true_jump=0.0, threshold=32.0) -> pd.DataFrame:
    """End-of-period chances with a known jump in net points at the threshold."""
    rng = np.random.default_rng(seed)
    prev_gc = rng.uniform(24, 45, n)
    used = rng.uniform(2, 18, n)
    frame = pd.DataFrame(
        {
            "GAME_ID": [f"G{i // 4:04d}" for i in range(n)],
            "PERIOD": rng.integers(1, 5, n),
            "CHANCE_ID": range(n),
            "TEAM": rng.choice(["A", "B"], n),
            "PTS_FG": 0.0,
            "PREV_GC": prev_gc,
            "LAST_GC": prev_gc - used,
            "START_SC": 24.0,
            "END_SC": rng.uniform(0, 24, n),
        }
    )
    built = window(frame)
    # Overwrite the outcome with a known signal plus the confound the design must survive:
    # net points rises with time left regardless of any 2-for-1.
    built["NET_REST"] = (
        0.05 * built.PREV_GC
        + true_jump * (built.PREV_GC >= threshold)
        + rng.normal(0, 1.0, len(built))
    )
    return built


def test_the_window_excludes_overtime_and_unorderable_chances():
    frame = _period([("A", 0)] * 4)
    frame["PREV_GC"] = [30.0, 30.0, 30.0, 30.0]
    frame["LAST_GC"] = [20.0, 35.0, 20.0, 20.0]  # second one ends before it starts
    frame["PERIOD"] = [1, 1, 5, 2]               # third is overtime
    frame["START_SC"], frame["END_SC"] = 24.0, 10.0
    out = window(frame)
    assert len(out) == 2
    assert set(out.PERIOD) == {1, 2}
    assert (out.CLOCK_USED >= 0).all()


def test_the_raw_difference_carries_the_trend_as_well_as_the_jump():
    """This is the estimator behaving correctly, not a defect.

    Net points trends with `PREV_GC` at 0.05/second by construction here, and the two sides of
    a threshold at 32 differ by about 10.5 seconds of mean running variable. So the raw
    difference must come back near jump + 0.5, and with no jump at all it must still be
    positive. That is precisely the confound the pre-registration named in advance, and the
    reason the local linear fit is registered alongside rather than instead.
    """
    real = _clustered_difference(_window_panel(true_jump=0.5), "NET_REST", 32.0)
    assert real["difference"] == pytest.approx(1.03, abs=0.25)
    assert abs(real["t"]) > 2

    none = _clustered_difference(_window_panel(true_jump=0.0, seed=3), "NET_REST", 32.0)
    assert none["difference"] == pytest.approx(0.53, abs=0.25)
    assert none["difference"] > 0.1


def test_the_local_linear_estimator_removes_the_trend_the_raw_one_cannot():
    """The registered defence against 'more time left means more scoring by someone'."""
    flat = _window_panel(true_jump=0.0, seed=5)
    sweep = threshold_sweep(flat, thresholds=(32.0,)).set_index(["outcome", "estimator"])
    raw = sweep.loc[("NET_REST", "raw difference"), "difference"]
    local = sweep.loc[("NET_REST", "local linear"), "difference"]
    assert abs(local) < abs(raw)
    assert abs(local) < 0.15  # trend removed, nothing left to find

    planted = _window_panel(true_jump=0.6, seed=6)
    sweep = threshold_sweep(planted, thresholds=(32.0,)).set_index(["outcome", "estimator"])
    assert sweep.loc[("NET_REST", "local linear"), "difference"] == pytest.approx(0.6, abs=0.3)


def test_the_sweep_reports_every_threshold():
    out = threshold_sweep(_window_panel())
    assert sorted(out.threshold.unique()) == [float(t) for t in range(28, 37)]
    assert set(out.outcome) == {"CLOCK_USED", "NET_REST"}


def test_profile_bins_by_second_and_is_ordered():
    out = profile(_window_panel())
    assert out.GC_BIN.is_monotonic_increasing
    assert out.N.sum() > 3000
