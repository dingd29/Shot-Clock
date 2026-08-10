"""Possession-review sampling tests."""

import pandas as pd

from possval.models.review import select_review_sample


def test_review_sample_is_reproducible_balanced_and_context_matched():
    rows = []
    at = 0
    for team in ("HOU", "ORL", "BOS", "DAL"):
        for season in (2022, 2023):
            for n in range(160):
                at += 1
                rows.append(
                    {
                        "TEAM_ABBREVIATION": team,
                        "SEASON": season,
                        "GAME_ID": at // 10,
                        "GAME_EVENT_ID": at,
                        "PLAYER_ID": at,
                        "PLAYER_NAME": str(at),
                        "PERIOD": 1,
                        "SECOND": 10,
                        "EXPOSURE": (n + 1) / 1000 if team != "DAL" else 0.0,
                        "SHOT_VALUE": 1.0,
                        "REFERENCE": 1.1,
                        "GAP": 0.1,
                        "SHOT_ZONE_BASIC": "Mid-Range",
                        "CHANCE_START_TYPE": "def_rebound",
                        "SCORE_MARGIN": 0.0,
                    }
                )
    # Give every exact case cell abundant zero-exposure controls.
    frame = pd.DataFrame(rows)
    worksheet, key = select_review_sample(frame, n_per_case_team=10, n_controls=10, seed=2)
    assert len(worksheet) == len(key) == 40
    assert key.SAMPLE_GROUP.value_counts().to_dict() == {
        "case: HOU": 10,
        "case: ORL": 10,
        "case: BOS": 10,
        "matched low-exposure control": 10,
    }
    assert worksheet.REVIEW_ID.is_unique
    assert not any(column in worksheet for column in ("TEAM_ABBREVIATION", "GAP", "SAMPLE_GROUP"))
