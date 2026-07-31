"""NBA shot-clock rules, isolated from the parser so they can be unit-tested directly.

The reset semantics that matter most, and are the most commonly gotten wrong:

A "reset to 14" is NOT `min(remaining, 14)`. Per NBA Rule 7 §II, in frontcourt reset
situations the clock goes *up* to 14 only if fewer than 14 seconds remain; if 14 or more
remain it is left alone. A team that grabs an offensive rebound two seconds into a
possession keeps its ~22 seconds — it is not penalised down to 14. So the correct
operation is `max(remaining, 14)`.

The 14-second reset did not exist before 2018-19; prior seasons reset to a full 24.
"""

from __future__ import annotations

FULL_CLOCK = 24.0
SHORT_CLOCK = 14.0

# Season (start year) in which the 14s offensive-rebound reset was introduced.
FOURTEEN_SECOND_RULE_SEASON = 2018

# EVENTMSGTYPE codes used by stats.nba.com playbyplayv2.
MADE_FG = 1
MISSED_FG = 2
FREE_THROW = 3
REBOUND = 4
TURNOVER = 5
FOUL = 6
VIOLATION = 7
SUBSTITUTION = 8
TIMEOUT = 9
JUMP_BALL = 10
EJECTION = 11
PERIOD_BEGIN = 12
PERIOD_END = 13
REPLAY = 18

# Events during which no game time elapses and no possession logic applies.
INERT = frozenset({SUBSTITUTION, TIMEOUT, EJECTION, REPLAY})

# EVENTMSGACTIONTYPE codes for fouls that transfer possession to the defense.
OFFENSIVE_FOUL_ACTIONS = frozenset({4, 26})
# Technical / administrative fouls: no possession change, no shot-clock reset.
TECHNICAL_FOUL_ACTIONS = frozenset({11, 12, 13, 16, 17, 18, 19, 25})

# EVENTMSGACTIONTYPE for a shot-clock-violation turnover. The true shot clock at these
# events is exactly 0, which makes them an independent calibration target for the whole
# reconstruction — one that never touches the official aggregates used for validation.
SHOT_CLOCK_VIOLATION_ACTION = 11

REGULATION_PERIOD_SECONDS = 720.0
OVERTIME_PERIOD_SECONDS = 300.0


def period_length(period: int) -> float:
    return REGULATION_PERIOD_SECONDS if period <= 4 else OVERTIME_PERIOD_SECONDS


def short_reset_value(season: int) -> float:
    """The frontcourt reset value in force for a given season."""
    return SHORT_CLOCK if season >= FOURTEEN_SECOND_RULE_SEASON else FULL_CLOCK


def apply_short_reset(remaining: float, season: int) -> float:
    """Frontcourt reset (offensive rebound, defensive loose-ball foul, kicked ball).

    Goes *up* to the reset value; never reduces a clock that already has more time.
    """
    return max(remaining, short_reset_value(season))


def cap_to_game_clock(shot_clock: float, game_clock_remaining: float) -> float:
    """The shot clock is switched off when the game clock is shorter than it.

    Without this, end-of-period possessions produce impossible values like "18 seconds
    on the shot clock with 6 seconds left in the quarter".
    """
    return min(shot_clock, game_clock_remaining)


def parse_pctime(pctimestring: str) -> float:
    """'11:43' -> 703.0 seconds remaining in the period.

    Late in a period the NBA switches to tenths ('0:24.7'); both forms are handled.
    """
    text = str(pctimestring).strip()
    if ":" not in text:
        return float(text)
    minutes, _, seconds = text.partition(":")
    return int(minutes) * 60 + float(seconds)
