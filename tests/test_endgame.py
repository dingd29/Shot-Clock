"""Tests for the end-of-period value model.

The accounting is the fragile part again, and it is fragile in a specific way: `V_ball(S)` and
`NET_AFTER(S)` are the same handover seen from opposite sides, so a sign or offset error makes
them disagree in a way that looks like a finding.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.endgame import (
    ball_value,
    flatness,
    handover_identity,
    possession_level,
)


def _chances(rows, game="G1", period=1) -> pd.DataFrame:
    """(START_TYPE, TEAM, PTS_FG, PREV_GC, LAST_GC) in chance order."""
    return pd.DataFrame(
        {
            "GAME_ID": game,
            "PERIOD": period,
            "SEASON": 2020,
            "CHANCE_ID": range(len(rows)),
            "START_TYPE": [r[0] for r in rows],
            "TEAM": [r[1] for r in rows],
            "PTS_FG": [float(r[2]) for r in rows],
            "PREV_GC": [float(r[3]) for r in rows],
            "LAST_GC": [float(r[4]) for r in rows],
            "START_SC": 24.0,
            "END_SC": 5.0,
        }
    )


def test_an_offensive_rebound_does_not_hand_the_ball_over():
    """The whole reason this module works at possession level rather than chance level."""
    panel = _chances(
        [
            ("def_rebound", "A", 0, 40, 33),
            ("off_rebound", "A", 2, 33, 30),   # same possession, A keeps it
            ("after_made_fg", "B", 3, 30, 20),
            ("def_rebound", "A", 0, 20, 12),
        ]
    )
    poss = possession_level(panel)
    assert len(poss) == 3
    assert list(poss.TEAM) == ["A", "B", "A"]
    # A's first possession spans both chances: starts at 40, ends at 30, scores 2.
    assert poss.iloc[0].START_GC == pytest.approx(40.0)
    assert poss.iloc[0].END_GC == pytest.approx(30.0)
    assert poss.iloc[0].PTS == pytest.approx(2.0)
    assert poss.iloc[0].DURATION == pytest.approx(10.0)


def test_net_from_start_and_net_after_are_the_same_ledger():
    panel = _chances(
        [
            ("def_rebound", "A", 2, 40, 33),
            ("after_made_fg", "B", 3, 33, 24),
            ("def_rebound", "A", 0, 24, 15),
            ("after_made_fg", "B", 2, 15, 5),
        ]
    )
    poss = possession_level(panel)
    # From A's first possession: A scores 2, B scores 5 -> net -3. After it: -5.
    assert poss.iloc[0].NET_FROM_START == pytest.approx(-3.0)
    assert poss.iloc[0].NET_AFTER == pytest.approx(-5.0)
    # NET_AFTER of one possession is the negative of NET_FROM_START of the next.
    for i in range(len(poss) - 1):
        assert poss.iloc[i].NET_AFTER == pytest.approx(-poss.iloc[i + 1].NET_FROM_START)


def test_periods_and_games_stay_separate():
    panel = pd.concat(
        [
            _chances([("def_rebound", "A", 2, 40, 30)]),
            _chances([("def_rebound", "B", 3, 40, 30)], period=2),
            _chances([("def_rebound", "C", 5, 40, 30)], game="G2"),
        ],
        ignore_index=True,
    )
    poss = possession_level(panel)
    assert list(poss.NET_FROM_START) == [2.0, 3.0, 5.0]


def _synthetic_periods(n_games=4000, seed=0, sawtooth=0.0) -> pd.DataFrame:
    """Periods of strictly alternating possessions, optionally with planted periodic value.

    `sawtooth` adds a component to the scoring rate keyed on the start clock, which is the
    structure `flatness` is supposed to detect. At zero there is nothing but a smooth trend and
    sampling noise.
    """
    rng = np.random.default_rng(seed)
    frames = []
    for game in range(n_games):
        clock, team, rows = 45.0, 0, []
        while clock > 3:
            end = max(clock - float(rng.integers(4, 16)), 0.0)
            rate = 0.4 + sawtooth * np.sin(2 * np.pi * clock / 24.0)
            rows.append(
                ("def_rebound", f"T{team}", 2.0 * (rng.random() < rate), clock, end)
            )
            clock, team = end, 1 - team
        frames.append(_chances(rows, game=f"G{game:05d}"))
    return pd.concat(frames, ignore_index=True)


def test_ball_value_recovers_a_known_constant():
    """Symmetric alternating play with no structure: V_ball should be flat and near zero."""
    panel = _synthetic_periods(n_games=3000, seed=1)
    values = ball_value(possession_level(panel), clock_range=(8, 40), min_possessions=100)
    assert len(values) > 20
    # Both teams score at the same rate, so holding the ball is worth roughly one possession.
    assert 0.0 < values.V_BALL.mean() < 1.2
    assert values.SE.mean() < 0.15


def test_the_handover_identity_holds_on_synthetic_data():
    panel = _synthetic_periods(n_games=4000, seed=2)
    poss = possession_level(panel)
    values = ball_value(poss, clock_range=(8, 40), min_possessions=100)
    check = handover_identity(poss, values)
    assert check["correlation"] > 0.8
    assert abs(check["bias"]) < 0.15


def test_flatness_separates_planted_structure_from_noise():
    flat = ball_value(
        possession_level(_synthetic_periods(n_games=3000, seed=3)),
        clock_range=(8, 40),
        min_possessions=100,
    )
    wavy = ball_value(
        possession_level(_synthetic_periods(n_games=3000, seed=3, sawtooth=0.5)),
        clock_range=(8, 40),
        min_possessions=100,
    )
    assert flatness(wavy)["structure_amplitude"] > flatness(flat)["structure_amplitude"]


def test_flatness_reports_amplitude_not_only_significance():
    """A p-value at this sample size decides nothing; the amplitude decides everything."""
    values = ball_value(
        possession_level(_synthetic_periods(n_games=3000, seed=4)),
        clock_range=(8, 40),
        min_possessions=100,
    )
    out = flatness(values)
    assert {"chi_square", "dof", "structure_amplitude", "noise_floor", "range"} <= set(out)
    assert out["structure_amplitude"] >= 0.0
    assert out["noise_floor"] > 0.0
