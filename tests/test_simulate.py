"""Tests for ratings and simulation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.ratings import srs_ratings
from possval.models.simulate import (
    balanced_schedule,
    simulate_playoffs,
    simulate_season,
    win_probability,
)


class TestWinProbability:
    def test_even_teams_at_neutral_are_a_coinflip(self):
        assert win_probability(0.0, home=False, home_advantage=0.0) == pytest.approx(0.5)

    def test_home_advantage_helps(self):
        assert win_probability(0.0, home=True) > 0.5
        assert win_probability(0.0, home=False) < 0.5

    def test_bounded_and_monotonic(self):
        diffs = np.linspace(-40, 40, 81)
        p = win_probability(diffs)
        assert p.min() > 0.0 and p.max() < 1.0
        assert np.all(np.diff(p) > 0)

    def test_symmetric_about_neutral(self):
        up = win_probability(5.0, home=False, home_advantage=0.0)
        down = win_probability(-5.0, home=False, home_advantage=0.0)
        assert up + down == pytest.approx(1.0)


class TestSRS:
    def test_recovers_known_ratings(self):
        """Construct games from known strengths; SRS should recover them up to a constant."""
        truth = {"A": 6.0, "B": 2.0, "C": -2.0, "D": -6.0}
        rows = []
        for home in truth:
            for away in truth:
                if home == away:
                    continue
                # Noiseless margins, so recovery should be near-exact.
                rows.append(
                    {"HOME": home, "AWAY": away, "MARGIN": truth[home] - truth[away] + 3.0}
                )
        ratings, home_advantage = srs_ratings(pd.DataFrame(rows))
        assert home_advantage == pytest.approx(3.0, abs=1e-6)
        for team, value in truth.items():
            assert ratings[team] == pytest.approx(value, abs=1e-6)

    def test_ratings_sum_to_zero(self):
        rows = [
            {"HOME": "A", "AWAY": "B", "MARGIN": 10},
            {"HOME": "B", "AWAY": "C", "MARGIN": -4},
            {"HOME": "C", "AWAY": "A", "MARGIN": 2},
        ]
        ratings, _ = srs_ratings(pd.DataFrame(rows))
        assert ratings.sum() == pytest.approx(0.0, abs=1e-9)


class TestSeasonSimulation:
    def test_total_wins_equals_games_played(self):
        teams = [f"T{i}" for i in range(6)]
        schedule = balanced_schedule(teams, games_each=20)
        ratings = pd.Series(np.zeros(len(teams)), index=teams)
        wins = simulate_season(ratings, schedule, n_sims=50, seed=0)
        assert (wins.sum(axis=1) == len(schedule)).all()

    def test_stronger_team_wins_more(self):
        teams = [f"T{i}" for i in range(6)]
        schedule = balanced_schedule(teams, games_each=40)
        ratings = pd.Series([12.0] + [0.0] * 5, index=teams)
        wins = simulate_season(ratings, schedule, n_sims=200, seed=0)
        assert wins["T0"].mean() > wins["T1"].mean()

    def test_rating_uncertainty_widens_the_distribution(self):
        teams = [f"T{i}" for i in range(6)]
        schedule = balanced_schedule(teams, games_each=40)
        ratings = pd.Series(np.zeros(len(teams)), index=teams)
        tight = simulate_season(ratings, schedule, n_sims=300, rating_sd=0.0, seed=0)
        loose = simulate_season(ratings, schedule, n_sims=300, rating_sd=4.0, seed=0)
        assert loose["T0"].std() > tight["T0"].std()


class TestPlayoffs:
    def test_probabilities_sum_to_one(self):
        seeds = [f"S{i}" for i in range(8)]
        ratings = pd.Series(np.linspace(8, -8, 8), index=seeds)
        titles = simulate_playoffs(ratings, seeds, n_sims=400, seed=0)
        assert titles.sum() == pytest.approx(1.0)

    def test_top_seed_is_favoured(self):
        seeds = [f"S{i}" for i in range(8)]
        ratings = pd.Series(np.linspace(8, -8, 8), index=seeds)
        titles = simulate_playoffs(ratings, seeds, n_sims=600, seed=0)
        assert titles.idxmax() == "S0"

    def test_even_field_is_roughly_uniform(self):
        seeds = [f"S{i}" for i in range(8)]
        ratings = pd.Series(np.zeros(8), index=seeds)
        titles = simulate_playoffs(ratings, seeds, n_sims=4000, seed=0)
        # Home court still advantages higher seeds, so allow a wide band around 1/8.
        assert titles.max() < 0.30
        assert titles.min() > 0.03


def test_schedule_gives_every_team_the_same_number_of_games():
    """The bug this replaces produced a right total and nothing else right.

    Enumerating all ordered pairs and truncating to the correct game count kept whichever
    pairs sorted first, so teams played 70 to 99 games and hosted 29 to 58. Philadelphia drew
    a short schedule and finished on 34 wins with a rating worth 43.
    """
    teams = [f"T{i:02d}" for i in range(30)]
    schedule = balanced_schedule(teams, games_each=82)

    played = pd.concat([schedule.HOME, schedule.AWAY]).value_counts()
    assert set(played.index) == set(teams)
    assert played.min() == played.max() == 82
    assert len(schedule) == 82 * 30 // 2

    hosted = schedule.HOME.value_counts()
    assert hosted.max() - hosted.min() <= 2, "home/away split is lopsided"
    assert not (schedule.HOME == schedule.AWAY).any(), "a team is scheduled against itself"
    assert schedule.groupby("HOME").AWAY.nunique().min() == len(teams) - 1


def test_win_totals_match_the_historical_rating_scale():
    """A rating has to imply the win total teams with that rating actually posted.

    The contemporaneous logistic scale is 7.0. At the 10.5 that was previously the default,
    a +12.7 team projects to 60 wins — Oklahoma City won 68 at that rating in 2024-25.
    """
    expected = {12.7: 70, 10.0: 66, 5.0: 55, 0.0: 41, -10.0: 16}
    for rating, wins in expected.items():
        home = win_probability(rating, True)
        away = win_probability(rating, False)
        assert 82 * (home + away) / 2 == pytest.approx(wins, abs=1.5)


def test_simulated_wins_conserve_games():
    """Every game has exactly one winner, so simulated wins must total 1,230."""
    teams = [f"T{i:02d}" for i in range(30)]
    ratings = pd.Series(np.linspace(-8, 8, 30), index=teams)
    wins = simulate_season(ratings, balanced_schedule(teams), n_sims=50, seed=1)

    assert (wins.sum(axis=1) == 82 * 30 // 2).all()
    # Compared across the full spread rather than between neighbours: the top two differ by
    # 0.55 rating points and one home game, which 50 simulations cannot resolve.
    average = wins.mean()
    assert average[teams[-1]] > average[teams[0]] + 20
    assert average.mean() == pytest.approx(41.0, abs=0.5)
