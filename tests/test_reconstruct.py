"""Golden and property tests for the shot-clock state machine.

Golden tests are hand-computed from real 2024-25 sequences: the arithmetic is simple enough
to verify by eye, which is exactly what makes them useful as regression anchors.
"""

from __future__ import annotations

import pandas as pd
import pytest

from possval.clock import rules as R
from possval.clock.reconstruct import reconstruct_game

HOME, AWAY = 1610612738.0, 1610612737.0  # BOS, ATL

COLUMNS = [
    "GAME_ID", "EVENTNUM", "EVENTMSGTYPE", "EVENTMSGACTIONTYPE", "PERIOD", "PCTIMESTRING",
    "HOMEDESCRIPTION", "VISITORDESCRIPTION", "NEUTRALDESCRIPTION",
    "PLAYER1_ID", "PLAYER1_TEAM_ID", "PLAYER3_TEAM_ID",
]


def build(rows: list[tuple]) -> pd.DataFrame:
    """rows: (eventnum, msgtype, action, pctime, desc, p1_id, p1_team, p3_team)"""
    records = []
    for num, mtype, action, pctime, desc, p1, p1t, p3t in rows:
        records.append(
            {
                "GAME_ID": 1, "EVENTNUM": num, "EVENTMSGTYPE": mtype,
                "EVENTMSGACTIONTYPE": action, "PERIOD": 1, "PCTIMESTRING": pctime,
                "HOMEDESCRIPTION": desc, "VISITORDESCRIPTION": None,
                "NEUTRALDESCRIPTION": None, "PLAYER1_ID": p1,
                "PLAYER1_TEAM_ID": p1t, "PLAYER3_TEAM_ID": p3t,
            }
        )
    return pd.DataFrame(records, columns=COLUMNS)


def clocks(df: pd.DataFrame) -> list[float]:
    return reconstruct_game(df, season=2024).SHOT_CLOCK.tolist()


class TestGoldenSequences:
    def test_defensive_rebound_starts_full_clock(self):
        # DEF rebound at 11:37 -> 24. Shot at 11:24 is 13s later -> 11 remaining.
        df = build([
            (1, 12, 0, "12:00", "Start of 1st Period", None, None, None),
            (2, 2, 1, "11:42", "MISS Johnson Jump Shot", 1, AWAY, None),
            (3, 4, 0, "11:37", "Horford REBOUND", 2, HOME, None),
            (4, 2, 1, "11:24", "MISS White 3PT", 3, HOME, None),
        ])
        assert clocks(df)[-1] == pytest.approx(11.0)

    def test_offensive_rebound_gets_fourteen(self):
        # Miss at 11:42, OFF rebound at 11:37 with ~5s left -> raised to 14.
        # Putback at 11:33 is 4s later -> 10 remaining.
        df = build([
            (1, 12, 0, "12:00", "Start of 1st Period", None, None, None),
            (2, 2, 1, "11:42", "MISS Johnson Jump Shot", 1, AWAY, None),
            (3, 4, 0, "11:37", "Risacher REBOUND", 2, AWAY, None),
            (4, 2, 1, "11:33", "MISS Johnson Layup", 1, AWAY, None),
        ])
        assert clocks(df)[-1] == pytest.approx(10.0)

    def test_made_basket_applies_inbound_delay(self):
        # Made FG at 11:00. The next chance starts 2s later (inbound touch), so a shot at
        # 10:50 has used 8s of shot clock, not 10.
        df = build([
            (1, 12, 0, "12:00", "Start of 1st Period", None, None, None),
            (2, 1, 1, "11:00", "Brown 3PT (3 PTS)", 1, HOME, None),
            (3, 2, 1, "10:50", "MISS Johnson Jump Shot", 2, AWAY, None),
        ])
        assert clocks(df)[-1] == pytest.approx(16.0)

    def test_dead_ball_rebound_between_free_throws_is_ignored(self):
        # The team rebound between FT 1-of-2 and 2-of-2 must not restart the clock.
        df = build([
            (1, 12, 0, "12:00", "Start of 1st Period", None, None, None),
            (2, 1, 1, "11:00", "Brown Layup (2 PTS)", 1, HOME, None),
            (3, 6, 2, "10:40", "Horford S.FOUL", 2, HOME, None),
            (4, 3, 11, "10:40", "MISS Capela Free Throw 1 of 2", 3, AWAY, None),
            (5, 4, 1, "10:40", "Hawks Rebound", AWAY, None, None),
            (6, 3, 12, "10:40", "Capela Free Throw 2 of 2", 3, AWAY, None),
        ])
        # No time elapses during the sequence, so every event holds the same clock.
        assert len(set(clocks(df)[2:])) == 1

    def test_phantom_rebound_before_violation_is_ignored(self):
        # A team rebound logged immediately before a shot-clock violation must not grant a
        # fresh 14 seconds at the exact moment the clock expired.
        df = build([
            (1, 12, 0, "12:00", "Start of 1st Period", None, None, None),
            (2, 2, 1, "11:40", "MISS Johnson Jump Shot", 1, AWAY, None),
            (3, 4, 1, "11:38", "Hawks Rebound", AWAY, None, None),
            (4, 5, R.SHOT_CLOCK_VIOLATION_ACTION, "11:38", "Hawks Turnover: Shot Clock",
             AWAY, None, None),
        ])
        result = reconstruct_game(df, season=2024)
        assert "off_rebound" not in result.CHANCE_START_TYPE.tolist()

    def test_non_monotone_game_clock_is_repaired(self):
        # A substitution carrying a stale timestamp must not rewind the clock.
        df = build([
            (1, 12, 0, "12:00", "Start of 1st Period", None, None, None),
            (2, 2, 1, "11:40", "MISS Johnson Jump Shot", 1, AWAY, None),
            (3, 8, 0, "4:39", "SUB: Ware FOR Adebayo", 5, AWAY, None),
            (4, 4, 0, "11:38", "Horford REBOUND", 2, HOME, None),
        ])
        result = reconstruct_game(df, season=2024)
        assert result.GAME_CLOCK_REPAIRED.any()
        assert result.SHOT_CLOCK.max() <= R.FULL_CLOCK


@pytest.fixture(scope="module")
def real_game():
    from possval.ingest import load_season

    pbp = load_season("nbastats", 2024)
    game_id = pbp.GAME_ID.iloc[0]
    return reconstruct_game(pbp[game_id == pbp.GAME_ID], season=2024)


class TestInvariants:
    """Properties that must hold on every real game, not just constructed ones."""

    def test_clock_within_bounds(self, real_game):
        clock = real_game.SHOT_CLOCK.dropna()
        assert clock.between(0.0, R.FULL_CLOCK).all()

    def test_clock_never_exceeds_game_clock(self, real_game):
        valid = real_game.dropna(subset=["SHOT_CLOCK"])
        assert (valid.SHOT_CLOCK <= valid.GAME_CLOCK + 1e-9).all()

    def test_clock_decreases_within_a_chance(self, real_game):
        """Inside one chance the clock only runs down — it never gains time."""
        valid = real_game.dropna(subset=["SHOT_CLOCK"])
        deltas = valid.groupby(["PERIOD", "CHANCE_ID"]).SHOT_CLOCK.diff().dropna()
        assert (deltas <= 1e-9).all()

    def test_low_confidence_rows_have_no_clock(self, real_game):
        assert real_game.loc[real_game.CLOCK_CONFIDENCE == "low", "SHOT_CLOCK"].isna().all()
