"""Synthetic release-frame and closest-defender extraction tests."""

import pandas as pd
import pytest

from possval.models.defender import (
    defender_at_release,
    join_tracking_shots,
    open_shot_case_control,
    release_frame,
)


def _moment(clock, shooter_x=10.0):
    return [
        1,
        1000,
        clock,
        12.0,
        None,
        [
            [-1, -1, 10.0, 11.0, 7.0],
            [1, 7, shooter_x, 10.0, 0.0],
            [1, 8, 20.0, 20.0, 0.0],
            [2, 9, 13.0, 14.0, 0.0],
            [2, 10, 20.0, 10.0, 0.0],
        ],
    ]


def test_release_frame_searches_event_and_predecessor_for_nearest_time():
    moments = []
    for at in range(8):
        moment = _moment(103.0 - at * 0.04)
        # Ball starts in the shooter's hands, then rises and separates.
        moment[5][0][2] = 10.0 + max(at - 2, 0) * 0.8
        moment[5][0][4] = 6.0 + max(at - 2, 0) * 0.8
        moments.append(moment)
    events = {4: {"moments": moments[:3]}, 5: {"moments": moments[3:]}}
    out = release_frame(events, 5, event_clock=100.0, shooter_id=7)
    assert out is not None
    assert out[2] > 102.0


def test_defender_distance_uses_opposing_players_only():
    out = defender_at_release(_moment(100.0), shooter_id=7, shooter_team_id=1)
    assert out["CLOSE_DEFENDER_ID"] == 9
    assert out["CLOSE_DEFENDER_DISTANCE"] == pytest.approx(5.0)
    assert out["N_DEFENDERS"] == 2


def test_tracking_join_reports_all_eligible_shots_and_missing_frames():
    shots = pd.DataFrame(
        {
            "GAME_ID": [1, 1, 2],
            "GAME_EVENT_ID": [10, 11, 10],
            "PLAYER_ID": [7, 8, 7],
        }
    )
    tracking = pd.DataFrame(
        {
            "GAME_ID": ["0000000001", "0000000001"],
            "GAME_EVENT_ID": [10, 11],
            "PLAYER_ID": [7, 8],
            "TRACKING_MATCHED": [True, False],
        }
    )
    joined, metrics = join_tracking_shots(shots, tracking)
    assert len(joined) == 2
    assert metrics["UNIQUE_KEY_JOIN_RATE"] == 1.0
    assert metrics["TRACKING_MATCH_RATE"] == 0.5
    assert metrics["N_AMBIGUOUS"] == 0


def test_tracking_join_counts_ambiguous_reconstructed_keys_as_unmatched():
    shots = pd.DataFrame(
        {
            "GAME_ID": [1, 1],
            "GAME_EVENT_ID": [10, 10],
            "PLAYER_ID": [7, 7],
        }
    )
    tracking = pd.DataFrame(
        {
            "GAME_ID": ["0000000001"],
            "GAME_EVENT_ID": [10],
            "PLAYER_ID": [7],
            "TRACKING_MATCHED": [True],
        }
    )
    joined, metrics = join_tracking_shots(shots, tracking)
    assert len(joined) == 2
    assert joined.AMBIGUOUS.all()
    assert metrics["N_AMBIGUOUS_RECONSTRUCTED"] == 2
    assert metrics["TRACKING_MATCH_RATE"] == 0.0


def test_open_case_control_balances_flags_inside_context():
    baseline = pd.DataFrame(
        {
            "GAME_ID": [1, 1, 1, 1],
            "GAME_EVENT_ID": [1, 2, 3, 4],
            "PLAYER_ID": [7, 8, 9, 10],
            "TEAM_ABBREVIATION": ["A"] * 4,
            "CLOSE_DEFENDER_DISTANCE": [5.0] * 4,
            "SECOND": [10] * 4,
            "SHOT_ZONE_BASIC": ["Mid-Range"] * 4,
            "BELOW": [True, True, False, False],
        }
    )
    aware = baseline[["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID"]].copy()
    aware["BELOW"] = [True, False, False, False]
    aware["EXPOSURE"] = [0.2, 0.0, 0.0, 0.0]
    out = open_shot_case_control(baseline, aware)
    assert out.groupby("BASELINE_CASE").N.sum().to_dict() == {False: 2, True: 2}
