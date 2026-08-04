"""Tests for the pre-registration scoring harness.

Written before the season starts, which is the only time they can be written honestly: a
scoring rule authored after seeing results is not a scoring rule, it is a choice of the
flattering one. These pin the arithmetic and the plumbing so that whatever the season does,
the grading does not move.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.scorecard import (
    BASE_HOME_WIN_RATE,
    calibration,
    score_games,
    win_total_error,
)


def synthetic_games(n: int = 2000, seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    """Games generated from known ratings, so a perfect model's score is knowable."""
    from possval.models.simulate import win_probability

    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(10)]
    ratings = pd.Series(np.linspace(-8, 8, 10), index=teams)

    home = rng.choice(teams, n)
    away = np.array([rng.choice([t for t in teams if t != h]) for h in home])
    probability = win_probability(ratings[home].to_numpy() - ratings[away].to_numpy(), True)
    won = (rng.random(n) < probability).astype(int)
    games = pd.DataFrame({"HOME": home, "AWAY": away, "HOME_WIN": won})
    return games, ratings


def test_true_ratings_beat_both_baselines():
    games, ratings = synthetic_games()
    scored = score_games(games, ratings, baseline=ratings * 0.0).set_index("model")

    truth = scored.loc["pre-registered projection"]
    assert truth.brier < scored.loc["prior-season SRS"].brier
    assert truth.brier < scored.loc["home team always"].brier
    assert truth.log_loss < scored.loc["home team always"].log_loss


def test_scoring_the_baseline_against_itself_is_a_tie():
    """The identity check that catches a mis-wired baseline.

    Feeding the baseline in as the projection must reproduce the baseline's own numbers
    exactly. Any difference means the two paths are not scoring the same games the same way.
    """
    games, _ = synthetic_games(seed=2)
    baseline = pd.Series(
        np.linspace(-3, 3, 10), index=[f"T{i:02d}" for i in range(10)]
    )
    scored = score_games(games, baseline, baseline).set_index("model")
    assert scored.loc["pre-registered projection"].brier == pytest.approx(
        scored.loc["prior-season SRS"].brier
    )
    assert scored.loc["pre-registered projection"].log_loss == pytest.approx(
        scored.loc["prior-season SRS"].log_loss
    )


def test_trivial_baseline_is_the_league_home_rate():
    games, ratings = synthetic_games(seed=4)
    scored = score_games(games, ratings, ratings).set_index("model")
    rate = games.HOME_WIN.mean()
    expected = (BASE_HOME_WIN_RATE - rate) ** 2 + rate * (1 - rate)
    assert scored.loc["home team always"].brier == pytest.approx(expected, abs=1e-6)


def test_empty_season_scores_without_raising():
    """The harness has to run before opening night, or it will not be ready on it."""
    empty = pd.DataFrame(columns=["HOME", "AWAY", "HOME_WIN"])
    ratings = pd.Series([1.0], index=["T00"])
    assert score_games(empty, ratings, ratings).empty
    assert calibration(empty, ratings).empty
    assert win_total_error(empty, pd.DataFrame(columns=["WINS"])).empty


def test_calibration_tracks_the_diagonal_for_a_true_model():
    games, ratings = synthetic_games(n=20_000, seed=6)
    table = calibration(games, ratings, bins=5)
    populated = table[table.n >= 200]
    assert len(populated) >= 3
    assert (populated.predicted - populated.actual).abs().max() < 0.06


def test_win_total_error_extrapolates_to_82():
    games = pd.DataFrame(
        {
            "HOME": ["A"] * 10 + ["B"] * 10,
            "AWAY": ["B"] * 10 + ["A"] * 10,
            "HOME_WIN": [1] * 10 + [0] * 10,
        }
    )
    projection = pd.DataFrame({"WINS": [82.0, 0.0]}, index=["A", "B"])
    out = win_total_error(games, projection).set_index("TEAM")
    # A won all 20; B lost all 20.
    assert out.loc["A", "pace_82"] == pytest.approx(82.0)
    assert out.loc["B", "pace_82"] == pytest.approx(0.0)
    assert out.loc["A", "error"] == pytest.approx(0.0)
