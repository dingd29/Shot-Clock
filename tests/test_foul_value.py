"""Tests for all-points shooting-foul validation."""

import pandas as pd
import pytest

from possval.models.foul_value import (
    add_action_priors,
    exercise_actions,
    foul_only_exercises,
    historical_foul_premium,
    shooting_foul_events,
)


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "GAME_ID": [1, 1, 1, 1],
            "EVENTNUM": [1, 2, 3, 4],
            "EVENTMSGTYPE": [1, 6, 6, 3],
            "EVENTMSGACTIONTYPE": [1, 2, 2, 11],
            "PCTIMESTRING": ["10:00", "10:00", "9:00", "9:00"],
            "GAME_CLOCK": [600.0, 600.0, 540.0, 540.0],
            "SHOT_CLOCK": [10.0, 10.0, 8.0, 8.0],
            "PERIOD": [1] * 4,
            "CHANCE_ID": [1, 2, 3, 3],
            "CHANCE_START_TYPE": ["def_rebound"] * 4,
            "PLAYER1_ID": [7, 8, 9, 7],
            "PLAYER1_NAME": ["Shooter", "Defender", "Defender", "Shooter"],
            "PLAYER2_ID": [0, 7, 7, 0],
            "PLAYER2_NAME": [None, "Shooter", "Shooter", None],
            "PLAYER2_TEAM_ABBREVIATION": [None, "A", "A", None],
            "HOMEDESCRIPTION": ["MAKE", "S.FOUL", "S.FOUL", None],
            "VISITORDESCRIPTION": [None, None, None, "Free Throw"],
            "SEASON": [2022] * 4,
        }
    )


def test_foul_only_exercises_remove_and_one_tail():
    out = foul_only_exercises(_events())
    assert len(out) == 1
    assert out.PLAYER_ID.iloc[0] == 7
    assert out.CHANCE_ID.iloc[0] == 3


def test_shooting_foul_events_attach_free_throw_points_without_double_counting():
    out = shooting_foul_events(_events()).set_index("CHANCE_ID")
    assert bool(out.loc[2, "AND_ONE"])
    assert not bool(out.loc[3, "AND_ONE"])
    assert out.loc[3, "FT_POINTS"] == 1


def test_exercise_actions_keep_fga_and_add_only_foul_only_row():
    shots = pd.DataFrame(
        {
            "PLAYER_ID": [7],
            "PLAYER_NAME": ["Shooter"],
            "TEAM_ABBREVIATION": ["A"],
            "SEASON": [2022],
            "GAME_ID": [1],
            "PERIOD": [1],
            "CHANCE_ID": [1],
            "SHOT_CLOCK": [10.0],
            "CHANCE_START_TYPE": ["def_rebound"],
            "PERIOD_SECONDS_REMAINING": [600.0],
            "GAME_CLOCK_EXPIRING": [0],
            "IS_HOME": [1],
        }
    )
    chained = pd.DataFrame(
        {
            "GAME_ID": [1, 1, 1],
            "PERIOD": [1, 1, 1],
            "CHANCE_ID": [1, 2, 3],
            "POSSESSION_ID": [1, 1, 2],
            "PTS_POSS": [3.0, 1.0, 2.0],
        }
    )
    out = exercise_actions(shots, _events(), chained)
    assert set(out.ACTION_KIND) == {"official FGA", "foul-only exercise"}
    assert out.set_index("ACTION_KIND").PTS_POSS.to_dict() == {
        "official FGA": 3.0,
        "foul-only exercise": 2.0,
    }


def test_action_priors_use_strictly_earlier_seasons():
    actions = pd.DataFrame(
        {
            "PLAYER_ID": [1, 1, 1],
            "SEASON": [2020, 2021, 2022],
            "PTS_POSS": [0.0, 2.0, 1.0],
        }
    )
    out = add_action_priors(actions).set_index("SEASON")
    assert out.loc[2020, "PRIOR_ACTION_N"] == 0
    assert out.loc[2021, "PRIOR_ACTION_N"] == 1
    assert out.loc[2022, "PRIOR_ACTION_N"] == 2
    expected = (2.0 + 100 * 1.0) / 102
    assert out.loc[2022, "PRIOR_ACTION_VALUE"] == pytest.approx(expected)


def test_foul_premium_uses_only_training_seasons():
    actions = pd.DataFrame(
        {"PLAYER_ID": [1, 1, 1, 2], "SEASON": [2020, 2021, 2022, 2022]}
    )
    fouls = pd.DataFrame(
        {
            "PLAYER_ID": [1, 1],
            "SEASON": [2021, 2022],
            "FT_POINTS": [2.0, 100.0],
        }
    )
    out = historical_foul_premium(actions, fouls, train_through=2021, prior_strength=0)
    assert out.set_index("PLAYER_ID").loc[1, "FOUL_PREMIUM"] == pytest.approx(1.0)


def test_foul_repricing_preserves_known_fga_location_columns():
    from possval.models.foul_value import foul_repriced_actions

    valued = pd.DataFrame(
        {
            "PLAYER_ID": [7],
            "TEAM_ABBREVIATION": ["A"],
            "SECOND": [10],
            "SHOT_CLOCK": [10.0],
            "SHOT_VALUE": [1.0],
            "SHOT_ZONE_BASIC": ["Restricted Area"],
        }
    )
    foul = pd.DataFrame(
        {
            "PLAYER_ID": [7],
            "TEAM_ABBREVIATION": ["A"],
            "SHOT_CLOCK": [10.0],
        }
    )
    premiums = pd.DataFrame(
        {"PLAYER_ID": [7], "FOUL_PREMIUM": [0.1], "LEAGUE_FOUL_PREMIUM": [0.1]}
    )
    out = foul_repriced_actions(valued, foul, premiums)
    assert "SHOT_ZONE_BASIC" in out
    official_zone = out.loc[
        out.ACTION_KIND.eq("official FGA"), "SHOT_ZONE_BASIC"
    ].iloc[0]
    assert official_zone == "Restricted Area"
    assert out.loc[out.ACTION_KIND.eq("foul-only exercise"), "SHOT_ZONE_BASIC"].isna().all()
