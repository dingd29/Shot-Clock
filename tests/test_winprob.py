"""Tests for the win-probability discrimination test.

The result is a near-zero improvement, which is the easiest kind of result to produce by
accident — a mis-wired feature block would also give one. These check the machinery can find
a signal when one exists, so the measured nil is informative rather than a bug.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.winprob import BASE_FEATURES, CLOCK_FEATURES, compare, game_seconds_remaining


def synthetic_state(n_games: int = 900, seed: int = 0, clock_matters: bool = False):
    """Game states whose outcome depends on margin and time, optionally on shot clock too."""
    rng = np.random.default_rng(seed)
    rows = []
    for game in range(n_games):
        strength = rng.normal(0, 6)
        for event in range(60):
            remaining = 2880 * (1 - event / 60)
            margin = strength * (1 - remaining / 2880) + rng.normal(0, 4)
            shot_clock = float(rng.integers(0, 25))
            rows.append(
                {
                    "GAME_ID": f"G{game:04d}",
                    "SEASON": 2015 + game % 10,
                    "MARGIN": margin,
                    "GAME_SECONDS_REMAINING": remaining,
                    "MARGIN_PER_SQRT_TIME": margin / np.sqrt(max(remaining, 1)),
                    "IS_HOME_POSSESSION": float(rng.random() < 0.5),
                    "PERIOD": min(4, 1 + event // 15),
                    "SHOT_CLOCK": shot_clock,
                    "CHANCE_ELAPSED": 24.0 - shot_clock,
                    "IS_LATE_CLOCK": float(shot_clock <= 7),
                    "STRENGTH": strength,
                }
            )
    frame = pd.DataFrame(rows)
    logit = frame.STRENGTH * 0.4
    if clock_matters:
        # A deliberately strong, learnable dependence on the clock block.
        logit = logit + 3.0 * (frame.SHOT_CLOCK - 12) / 12
    if clock_matters:
        # Event-level label, so the clock block has something learnable to find.
        frame["HOME_WIN"] = (rng.random(len(frame)) < 1 / (1 + np.exp(-logit))).astype(int)
    else:
        # One label per game, as in the real data: every event in a game shares an outcome.
        by_game = frame.groupby("GAME_ID").STRENGTH.first()
        outcome = (rng.random(len(by_game)) < 1 / (1 + np.exp(-0.4 * by_game))).astype(int)
        frame["HOME_WIN"] = frame.GAME_ID.map(outcome)
    return frame.drop(columns=["STRENGTH"])


def test_finds_a_signal_that_is_really_there():
    """If the clock block genuinely drives the outcome, the comparison must show it.

    Without this, a near-zero result on real data cannot be distinguished from a feature
    block that was never wired into the model.
    """
    state = synthetic_state(clock_matters=True, seed=1)
    scores = compare(state, train_through=2022, valid=2023, test=2024).set_index("model")
    assert scores.loc["base + shot clock"].log_loss < scores.loc["base"].log_loss - 0.02


def test_finds_nothing_when_the_clock_is_noise():
    state = synthetic_state(clock_matters=False, seed=2)
    scores = compare(state, train_through=2022, valid=2023, test=2024).set_index("model")
    difference = scores.loc["base"].log_loss - scores.loc["base + shot clock"].log_loss
    assert abs(difference) < 0.02


def test_feature_blocks_are_disjoint():
    """A feature appearing in both blocks would make the ablation meaningless."""
    assert not set(BASE_FEATURES) & set(CLOCK_FEATURES)


def test_game_seconds_remaining_counts_periods():
    period = pd.Series([1, 2, 4])
    clock = pd.Series([720.0, 360.0, 60.0])
    out = game_seconds_remaining(period, clock)
    assert out.iloc[0] == pytest.approx(720 + 3 * 720)
    assert out.iloc[1] == pytest.approx(360 + 2 * 720)
    assert out.iloc[2] == pytest.approx(60.0)
