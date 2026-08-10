"""Regression tests for validation comparisons and uncertainty bounds."""

import pandas as pd
import pytest

from possval.models.team_validation import (
    aligned_rank_correlation,
    location_exposure_bounds,
    team_game_bootstrap,
)


def test_rank_correlation_aligns_team_rows_before_comparing():
    left = pd.DataFrame(
        {"TEAM_ABBREVIATION": ["A", "B", "C"], "EXPOSURE": [1.0, 2.0, 3.0]}
    )
    right = pd.DataFrame(
        {"TEAM_ABBREVIATION": ["C", "A", "B"], "EXPOSURE": [3.0, 1.0, 2.0]}
    )
    result = aligned_rank_correlation(left, right, "EXPOSURE")
    assert result["N_TEAMS"] == 3
    assert result["SPEARMAN_RHO"] == pytest.approx(1.0)


def test_location_bounds_assign_unknown_exposure_to_neither_or_all():
    scored = pd.DataFrame(
        {
            "SHOT_ZONE_BASIC": ["In The Paint (Non-RA)", None, "Restricted Area"],
            "EXPOSURE": [2.0, 1.0, 1.0],
            "CHANCE_START_TYPE": ["def_rebound"] * 3,
        }
    )
    paint = location_exposure_bounds(scored).set_index("SHOT_FAMILY").loc["paint (non-RA)"]
    assert paint.SHARE_LOWER == pytest.approx(0.5)
    assert paint.SHARE_UPPER == pytest.approx(0.75)


def test_team_game_bootstrap_keeps_whole_games_and_returns_intervals():
    scored = pd.DataFrame(
        {
            "TEAM_ABBREVIATION": ["A"] * 4,
            "GAME_ID": [1, 1, 2, 2],
            "BELOW": [True, True, False, False],
            "EXPOSURE": [1.0, 1.0, 0.0, 0.0],
        }
    )
    out = team_game_bootstrap(scored, n_draws=200, seed=1).iloc[0]
    assert out.N_TEAM_GAMES == 2
    assert out.PREMATURE == pytest.approx(0.5)
    assert out.PREMATURE_LOW <= out.PREMATURE <= out.PREMATURE_HIGH
