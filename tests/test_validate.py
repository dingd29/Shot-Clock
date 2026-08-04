"""Both validation axes have to weight the official file the same way.

The official reference is per-game. Axis 3 divided reconstructed totals by `GP`; axis 1/2
summed the per-game rates as though they were totals, which silently over-weighted low-minute
players and inflated the published eFG gap from 1.05pp to 1.78pp. These tests pin the
weighting so the two axes cannot drift apart again.
"""

from __future__ import annotations

import pandas as pd
import pytest

from possval.clock.validate import BUCKET_ORDER, compare_league_wide


def _official(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["SHOT_CLOCK_RANGE"] = pd.Categorical(
        df.SHOT_CLOCK_RANGE, categories=BUCKET_ORDER, ordered=True
    )
    return df


def test_official_side_is_weighted_by_games_played():
    """A 10-game and an 80-game player must not count equally.

    Both take 10 shots per game in the same bucket, but the 80-game player makes 60% and the
    10-game player 20%. The correct league FG% is (0.6*800 + 0.2*100) / 900 = 55.6%, not the
    unweighted 40% that summing the rates produces.
    """
    official = _official(
        [
            {"PLAYER_ID": 1, "GP": 80, "FGA": 10.0, "FGM": 6.0, "FG3M": 0.0,
             "SHOT_CLOCK_RANGE": "15-7"},
            {"PLAYER_ID": 2, "GP": 10, "FGA": 10.0, "FGM": 2.0, "FG3M": 0.0,
             "SHOT_CLOCK_RANGE": "15-7"},
        ]
    )
    # Reconstruction reproduces the GP-weighted truth exactly, so every diff should be zero.
    recon = pd.DataFrame(
        [{"BUCKET": "15-7", "FGA": 900.0, "FGM": 500.0, "FG3M": 0.0}]
    )
    recon["BUCKET"] = pd.Categorical(recon.BUCKET, categories=BUCKET_ORDER, ordered=True)

    out = compare_league_wide(recon, official).set_index("BUCKET").loc["15-7"]

    assert out.FG_PCT_official == pytest.approx(500 / 900, abs=1e-9)
    assert out.FG_PCT_DIFF_PP == pytest.approx(0.0, abs=1e-9)
    assert out.EFG_DIFF_PP == pytest.approx(0.0, abs=1e-9)


def test_share_is_insensitive_to_the_weighting_but_efg_is_not():
    """The bug that shipped: share barely moved, efficiency moved a lot.

    Equal per-game volume in both buckets, but the players differ in games played, so the true
    share is 8:1 while the unweighted sum says 1:1.
    """
    official = _official(
        [
            {"PLAYER_ID": 1, "GP": 80, "FGA": 5.0, "FGM": 3.0, "FG3M": 0.0,
             "SHOT_CLOCK_RANGE": "15-7"},
            {"PLAYER_ID": 2, "GP": 10, "FGA": 5.0, "FGM": 1.0, "FG3M": 0.0,
             "SHOT_CLOCK_RANGE": "7-4"},
        ]
    )
    recon = pd.DataFrame(
        [
            {"BUCKET": "15-7", "FGA": 400.0, "FGM": 240.0, "FG3M": 0.0},
            {"BUCKET": "7-4", "FGA": 50.0, "FGM": 10.0, "FG3M": 0.0},
        ]
    )
    recon["BUCKET"] = pd.Categorical(recon.BUCKET, categories=BUCKET_ORDER, ordered=True)

    out = compare_league_wide(recon, official).set_index("BUCKET")

    assert out.loc["15-7", "FGA_SHARE_official"] == pytest.approx(400 / 450)
    assert out.loc["7-4", "FGA_SHARE_official"] == pytest.approx(50 / 450)
    assert abs(out.SHARE_DIFF_PP.dropna()).max() == pytest.approx(0.0, abs=1e-9)
