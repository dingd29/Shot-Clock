"""Tests for the unified possession valuation curve and the team decomposition.

The thing worth protecting here is the separation of three questions that look alike: where a
team sits on the curve, whether its curve differs, and whether it sits below its own curve. Only
the third is a claim that anybody is doing anything wrong, and conflating them is how a style
difference gets published as a mistake.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.value import (
    calibration_summary,
    curve_shape,
    possession_curve,
    premature_share,
    shot_value,
    start_group,
    team_curves,
    team_shot_timing,
)


def _panel(rows, game="G1", period=1) -> pd.DataFrame:
    """(START_TYPE, TEAM, START_SC, END_SC, PTS_FG)."""
    return pd.DataFrame(
        {
            "GAME_ID": game,
            "PERIOD": period,
            "SEASON": 2020,
            "CHANCE_ID": range(len(rows)),
            "START_TYPE": [r[0] for r in rows],
            "OFF_TEAM_ID": [r[1] for r in rows],
            "TEAM": [f"T{r[1]}" for r in rows],
            "START_SC": [float(r[2]) for r in rows],
            "END_SC": [float(r[3]) for r in rows],
            "PTS_FG": [float(r[4]) for r in rows],
            "PERIOD_EXPIRED": False,
        }
    )


def test_start_groups_collapse_to_three_and_default_safely():
    types = pd.Series(["off_rebound", "after_turnover", "def_rebound", "something_new"])
    assert list(start_group(types)) == [
        "second_chance",
        "live_ball",
        "half_court",
        "half_court",
    ]


def test_the_curve_recovers_a_known_continuation_value():
    """Every possession starts at 24 and ends at 10, scoring 1 point.

    Anything still alive above 10 seconds continued, so `V(t)` must be exactly 1.0 there and
    undefined at or below 10 where nothing continued.
    """
    rows = [("def_rebound", i % 2, 24, 10, 1.0) for i in range(4000)]
    curve = possession_curve(_panel(rows), min_chances=100).set_index("SECOND")
    assert curve.loc[11, "V"] == pytest.approx(1.0)
    assert curve.loc[24, "V"] == pytest.approx(1.0)
    assert 10 not in curve.index  # nothing continued at or below the end


def test_second_chances_get_their_own_curve():
    rows = [("def_rebound", 0, 24, 5, 0.0) for _ in range(2000)]
    rows += [("off_rebound", 0, 14, 5, 2.0) for _ in range(2000)]
    curve = possession_curve(_panel(rows), min_chances=100)
    assert set(curve.GROUP) == {"half_court", "second_chance"}
    second = curve[curve.GROUP == "second_chance"]
    # An offensive rebound continues the same possession, so its points roll into the earlier
    # chance too; what matters here is that the group is estimated separately at all.
    assert second.SECOND.max() <= 14


def test_calibration_summary_separates_a_level_shift_from_shape_error():
    """A curve that is uniformly 0.05 low is right about shape and wrong about level."""
    table = pd.DataFrame(
        {
            "N": [1000] * 5,
            "SE": [0.01] * 5,
            "PREDICTED": [0.5, 0.6, 0.7, 0.8, 0.9],
            "REALISED": [0.55, 0.65, 0.75, 0.85, 0.95],
        }
    )
    table["ERROR"] = table.REALISED - table.PREDICTED

    raw = calibration_summary(table)
    shifted = calibration_summary(table, level_shift=True)
    assert raw["mean_abs_error"] == pytest.approx(0.05)
    assert shifted["level_shift"] == pytest.approx(0.05)
    assert shifted["mean_abs_error"] == pytest.approx(0.0, abs=1e-9)
    assert shifted["dof"] == raw["dof"] - 1


def _valued(rows) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "GAME_ID": [r[0] for r in rows],
            "TEAM_ABBREVIATION": [r[1] for r in rows],
            "SECOND": [r[2] for r in rows],
            "SHOT_VALUE": [float(r[3]) for r in rows],
        }
    )


def test_shot_timing_is_style_and_says_nothing_about_quality():
    early = [(f"G{i}", "FAST", 20, 1.0) for i in range(6000)]
    late = [(f"G{i}", "SLOW", 4, 1.0) for i in range(6000)]
    out = team_shot_timing(_valued(early + late), min_shots=1000).set_index(
        "TEAM_ABBREVIATION"
    )
    assert out.loc["FAST", "MEAN_SECOND"] > out.loc["SLOW", "MEAN_SECOND"]
    assert out.loc["FAST", "EARLY_SHARE"] == pytest.approx(1.0)
    assert out.loc["SLOW", "LATE_SHARE"] == pytest.approx(1.0)


def test_curve_shape_removes_the_level_so_only_decay_is_compared():
    """A team of better shooters has a higher curve everywhere. That is capability, not style."""
    curves = pd.DataFrame(
        {
            "TEAM": ["GOOD", "BAD"],
            "V2": [0.7, 0.5],
            "V6": [0.8, 0.6],
            "V10": [0.9, 0.7],
            "V14": [1.0, 0.8],
            "V18": [1.1, 0.9],
            "V22": [1.2, 1.0],
        }
    )
    shape = curve_shape(curves).set_index("TEAM")
    # Identical shapes, different levels: after centring the two rows must agree exactly.
    assert shape.loc["GOOD"].to_numpy() == pytest.approx(shape.loc["BAD"].to_numpy())


def test_premature_share_scores_each_team_against_its_own_curve():
    """The point of the measure: an identical shot is premature for one team and not the other."""
    curves = pd.DataFrame(
        {"TEAM": ["HIGH", "LOW"], **{f"V{t}": [1.0, 0.5] for t in range(25)}}
    )
    shots = _valued(
        [(f"G{i}", "HIGH", 10, 0.8) for i in range(3000)]
        + [(f"G{i}", "LOW", 10, 0.8) for i in range(3000)]
    )
    out = premature_share(shots, curves, min_shots=1000).set_index("TEAM_ABBREVIATION")
    assert out.loc["HIGH", "PREMATURE"] == pytest.approx(1.0)
    assert out.loc["LOW", "PREMATURE"] == pytest.approx(0.0)


def test_premature_share_is_a_proportion_with_a_binomial_error():
    curves = pd.DataFrame({"TEAM": ["A"], **{f"V{t}": [1.0] for t in range(25)}})
    values = [0.5] * 2000 + [1.5] * 2000
    shots = _valued([(f"G{i}", "A", 10, v) for i, v in enumerate(values)])
    out = premature_share(shots, curves, min_shots=100).iloc[0]
    assert out.PREMATURE == pytest.approx(0.5)
    assert out.SE == pytest.approx(np.sqrt(0.25 / 4000))
    # Far better conditioned than a ratio of fitted slopes — that is the whole reason for it.
    assert out.SE < 0.01


def test_reset_instant_shots_are_excluded_from_the_boundary_comparisons():
    curves = pd.DataFrame({"TEAM": ["A"], **{f"V{t}": [1.0] for t in range(25)}})
    shots = _valued(
        [(f"G{i}", "A", 24, 0.1) for i in range(3000)]  # tips at the reset, not decisions
        + [(f"G{i}", "A", 10, 1.5) for i in range(3000)]
    )
    out = premature_share(shots, curves, min_shots=100).iloc[0]
    assert out.N_SHOTS == 3000
    assert out.PREMATURE == pytest.approx(0.0)


def test_team_curves_can_be_relabelled_without_rechaining():
    """The permutation null relabels teams; the chained panel must not need rebuilding."""
    rows = [("def_rebound", i % 2, 24, 5, float(i % 3)) for i in range(8000)]
    chained = _panel(rows)
    chained["PTS_POSS"] = chained.PTS_FG
    real = team_curves(chained, min_chances=100, min_possessions=100)
    fake = team_curves(
        chained,
        labels=np.array(["X", "Y"] * 4000),
        min_chances=100,
        min_possessions=100,
    )
    assert set(real.TEAM) == {"T0", "T1"}
    assert set(fake.TEAM) == {"X", "Y"}
    assert len(real) == len(fake) == 2


def test_shot_value_never_falls_below_expected_points():
    outcomes = pd.DataFrame(
        {
            "SEASON": 2020,
            "SHOT_ZONE_BASIC": "Mid-Range",
            "SHOT_CLOCK": 10.0,
            "CLOCK_BAND": pd.Categorical(["8-15"] * 2000),
            "SHOT_MADE_FLAG": [1] * 1000 + [0] * 1000,
            "RETAINED": [False] * 1000 + [True] * 400 + [False] * 600,
            "PLAYER_REBOUND": True,
            "RESOLVED": True,
        }
    )
    shots = pd.DataFrame(
        {"XPTS": [1.0, 0.8], "SHOT_CLOCK": [10.0, 10.0], "SHOT_ZONE_BASIC": ["Mid-Range"] * 2}
    )
    out = shot_value(shots, outcomes, second_chance=1.0)
    assert (out.SHOT_VALUE >= out.XPTS).all()
    assert out.RETAIN.iloc[0] == pytest.approx(0.2)
