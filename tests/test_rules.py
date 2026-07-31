"""Unit tests for the shot-clock rules, independent of any play-by-play parsing."""

from __future__ import annotations

import pytest

from possval.clock import rules as R


class TestShortReset:
    """The 14-second reset raises the clock; it never lowers one that has more time."""

    def test_raises_clock_below_fourteen(self):
        assert R.apply_short_reset(5.0, season=2024) == 14.0

    def test_leaves_clock_above_fourteen_untouched(self):
        # A team rebounding two seconds in keeps its ~22s. Implementing this as min()
        # would wrongly penalise them down to 14 — the classic way to get this wrong.
        assert R.apply_short_reset(22.0, season=2024) == 22.0

    def test_boundary_is_idempotent(self):
        assert R.apply_short_reset(14.0, season=2024) == 14.0

    def test_pre_2018_seasons_reset_to_full_clock(self):
        assert R.apply_short_reset(5.0, season=2017) == 24.0
        assert R.short_reset_value(2017) == 24.0
        assert R.short_reset_value(2018) == 14.0


class TestGameClockCap:
    def test_truncates_at_end_of_period(self):
        # 18 seconds on the shot clock with 6 left in the quarter is impossible.
        assert R.cap_to_game_clock(18.0, 6.0) == 6.0

    def test_no_effect_mid_period(self):
        assert R.cap_to_game_clock(18.0, 400.0) == 18.0


class TestParsePctime:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [("11:43", 703.0), ("12:00", 720.0), ("0:00", 0.0), ("5:00", 300.0)],
    )
    def test_mmss(self, text, expected):
        assert R.parse_pctime(text) == expected

    def test_tenths_late_in_period(self):
        assert R.parse_pctime("0:24.7") == pytest.approx(24.7)


class TestPeriodLength:
    def test_regulation(self):
        assert R.period_length(1) == 720.0
        assert R.period_length(4) == 720.0

    def test_overtime(self):
        assert R.period_length(5) == 300.0
