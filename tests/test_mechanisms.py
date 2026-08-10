"""Tests for exploratory team-profile mechanism decompositions."""

import pandas as pd
import pytest

from possval.models.mechanisms import (
    game_state_profiles,
    mover_pairs,
    possession_sequence_profiles,
)


def test_game_state_margin_is_from_offenses_perspective():
    rows = []
    for team, home, margin in (("HOME", 1, 8), ("AWAY", 0, 8)):
        for _ in range(120):
            rows.append(
                {
                    "TEAM_ABBREVIATION": team,
                    "IS_HOME": home,
                    "SCORE_MARGIN": margin,
                    "PERIOD": 4,
                    "EXPOSURE": 0.1,
                    "BELOW": True,
                    "SECOND": 10,
                    "SHOT_VALUE": 1.0,
                }
            )
    out = game_state_profiles(pd.DataFrame(rows), min_shots=100)
    state = out.set_index("TEAM_ABBREVIATION").SCORE_STATE.astype(str)
    assert state["HOME"] == "leading 4–9"
    assert state["AWAY"] == "trailing 4–9"


def test_mover_pairs_use_primary_team_and_adjacent_seasons_only():
    teams = pd.DataFrame(
        {
            "TEAM_ABBREVIATION": ["A", "B", "C"],
            "SEASON": [2022, 2023, 2023],
            "EXPOSURE_PER_SHOT": [0.01, 0.03, 0.02],
        }
    )
    players = pd.DataFrame(
        {
            "PLAYER_ID": [1, 1, 1],
            "PLAYER_NAME": ["Mover"] * 3,
            "TEAM_ABBREVIATION": ["A", "B", "C"],
            "SEASON": [2022, 2023, 2023],
            "N_SHOTS": [200, 300, 100],
            "EXPOSURE_PER_SHOT": [0.02, 0.04, 0.08],
            "PREMATURE": [0.1, 0.2, 0.3],
            "MEAN_SECOND": [10, 11, 12],
        }
    )
    out = mover_pairs(teams, players).iloc[0]
    assert out.TEAM_ABBREVIATION_FROM == "A"
    assert out.TEAM_ABBREVIATION_TO == "B"
    assert out.PLAYER_EXPOSURE_CHANGE == pytest.approx(0.02)
    assert out.TEAM_EXPOSURE_CHANGE == pytest.approx(0.02)


def test_sequence_profiles_compare_next_first_shot_within_period():
    chained = pd.DataFrame(
        {
            "GAME_ID": [1, 1, 1, 1],
            "PERIOD": [1, 1, 1, 1],
            "CHANCE_ID": [1, 2, 3, 4],
            "POSSESSION_ID": [1, 2, 3, 4],
            "TEAM": ["A", "B", "A", "B"],
            "PTS_POSS": [0.0, 0.0, 2.0, 0.0],
            "FGA": [1, 1, 1, 1],
            "START_TYPE": ["period_start", "def_rebound", "def_rebound", "after_made_fg"],
        }
    )
    shots = pd.DataFrame(
        {
            "GAME_ID": [1, 1, 1, 1],
            "PERIOD": [1, 1, 1, 1],
            "CHANCE_ID": [1, 2, 3, 4],
            "GAME_EVENT_ID": [1, 2, 3, 4],
            "SHOT_CLOCK": [12.0, 11.0, 10.0, 9.0],
            "XPTS": [1.0, 1.0, 1.0, 1.0],
        }
    )
    league, teams = possession_sequence_profiles(chained, shots)
    assert set(league.PREVIOUS_RESULT) == {"empty shooting possession"}
    assert league.N.sum() == 2
    assert set(teams.TEAM) == {"A", "B"}
