"""Reconstruct shot-clock-remaining for every play-by-play event.

The NBA publishes no per-shot shot clock in any public feed. It is recoverable because
play-by-play records (a) the game clock at every event and (b) every event that resets the
shot clock. Walking a period in order while tracking "when did the current chance start and
with how many seconds" yields the clock at any event in between.

Terminology follows pbpstats: a *possession* ends when the ball changes teams, while a
*chance* is a single shot-clock interval. An offensive rebound starts a new chance inside
the same possession.

Known irreducible error sources, all of which push reconstructed clocks *higher* than
reality (we miss resets rather than inventing them):
  - Kicked balls and defensive deflections out of bounds reset the clock but are only
    sometimes logged as VIOLATION events.
  - Clock-operator corrections after a stoppage are never logged.
  - Game clock is recorded to whole seconds, so each event carries up to ~1s of quantisation.
Every event therefore carries a `CLOCK_CONFIDENCE` flag; the validation harness reports
agreement separately for high- and low-confidence rows.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from possval.clock import rules as R

_FT_SEQ = re.compile(r"(\d+) of (\d+)")
_TEAM_ID_FLOOR = 1_610_612_700  # team ids sit above this; player ids are far below


def _describe(row) -> str:
    for field in ("HOMEDESCRIPTION", "VISITORDESCRIPTION", "NEUTRALDESCRIPTION"):
        val = getattr(row, field, None)
        if isinstance(val, str) and val:
            return val
    return ""


def _is_last_free_throw(desc: str) -> bool:
    """True when this free throw is the final one of its set (clock restarts after it)."""
    match = _FT_SEQ.search(desc)
    if not match:
        return True  # technical FTs and unparsed cases: treat as terminal
    return match.group(1) == match.group(2)


def _rebound_team(row) -> float | None:
    """Team credited with a rebound. Team rebounds carry the team id in PLAYER1_ID."""
    team = row.PLAYER1_TEAM_ID
    if pd.notna(team) and team:
        return float(team)
    pid = row.PLAYER1_ID
    if pd.notna(pid) and pid >= _TEAM_ID_FLOOR:
        return float(pid)
    return None


def _next_live_events(
    etypes: list[int], actions: list[int]
) -> list[tuple[int | None, int | None]]:
    """For each event, the (type, action) of the next event that isn't inert.

    Two decisions need this lookahead, and neither is inferable from the current row:
      - Shooting foul vs. not: the action codes cannot distinguish a personal foul in the
        penalty (which sends the offense to the line) from one that isn't (which returns
        the ball with a frontcourt reset). Whether free throws actually follow can.
      - Live rebound vs. dead-ball bookkeeping: when the shot clock expires, the feed logs
        a team rebound to the offense immediately *before* the violation turnover. Granting
        that phantom rebound a 14-second reset was worth +16s of error at violation events.
    """
    nxt: list[tuple[int | None, int | None]] = [(None, None)] * len(etypes)
    upcoming: tuple[int | None, int | None] = (None, None)
    for i in range(len(etypes) - 1, -1, -1):
        nxt[i] = upcoming
        if etypes[i] not in R.INERT:
            upcoming = (etypes[i], actions[i])
    return nxt


#: Seconds between a dead-ball event's timestamp and the moment the shot clock actually
#: starts (the inbound touch). Live-ball starts — rebounds, steals — have no delay.
#: Calibrated against shot-clock violations by `possval.clock.calibrate`; see METHODOLOGY.md.
DEFAULT_INBOUND_DELAY: dict[str, float] = {
    # 2.0s: the only delay the violation calibration finds to be non-zero, from the largest
    # sample (725 violations, median error -2.0). Physically it is the time to retrieve the
    # ball and touch the inbound pass after a made basket.
    "after_made_fg": 2.0,
    "after_made_ft": 0.0,
    "after_turnover": 0.0,
    "after_def_foul": 0.0,
    "after_off_foul": 0.0,
    "after_kicked_ball": 0.0,
    "period_start": 0.0,
    "jump_ball": 0.0,
}


def reconstruct_game(
    events: pd.DataFrame,
    season: int,
    delays: dict[str, float] | None = None,
    disable_underflow_guard: bool = False,
) -> pd.DataFrame:
    """Reconstruct shot clock for one game. `events` must be a single GAME_ID, in event order.

    `delays` maps chance-start type -> seconds of dead time before the shot clock starts.
    `disable_underflow_guard` turns off the "clock ran below zero, restart it" rule; used
    only during calibration, where the uncensored negative values are the signal.

    Returns one row per input event with the chance-tracking columns attached.
    """
    delays = DEFAULT_INBOUND_DELAY if delays is None else delays
    events = events.sort_values("EVENTNUM")
    teams = [t for t in events.PLAYER1_TEAM_ID.dropna().unique() if t >= _TEAM_ID_FLOOR]
    next_event = _next_live_events(
        events.EVENTMSGTYPE.tolist(), events.EVENTMSGACTIONTYPE.tolist()
    )

    def other_team(team):
        if team is None:
            return None
        for candidate in teams:
            if candidate != team:
                return float(candidate)
        return None

    out_sc: list[float] = []
    out_raw: list[float] = []
    out_off: list[float | None] = []
    out_chance: list[int] = []
    out_start_type: list[str] = []
    out_conf: list[str] = []

    period = None
    off_team: float | None = None
    chance_start_gc = 0.0  # game clock (s remaining in period) when the chance began
    chance_start_sc = R.FULL_CLOCK  # shot clock value at that moment
    chance_id = -1
    start_type = "period_start"
    confidence = "high"
    last_shot_team: float | None = None
    # A rebound only restarts the clock if the ball was actually live. The placeholder
    # team rebounds logged between free throws of the same set are dead-ball bookkeeping.
    rebound_is_live = False
    # ~0.7% of stats.nba.com events carry a stale PCTIMESTRING — substitutions are the worst
    # offenders, sometimes logged minutes away from the surrounding play. The game clock
    # never increases within a period, so clamping to a running minimum repairs them.
    running_min_gc = float("inf")
    out_repaired: list[bool] = []

    def begin_chance(gc: float, sc: float, kind: str, team: float | None, conf: str = "high"):
        nonlocal chance_start_gc, chance_start_sc, chance_id, start_type, off_team, confidence
        # On a dead ball the clock does not start until the inbound is touched, which is
        # some seconds after the event that caused the stoppage.
        chance_start_gc = gc - delays.get(kind, 0.0)
        chance_start_sc = sc
        chance_id += 1
        start_type = kind
        confidence = conf
        if team is not None:
            off_team = team

    for idx, row in enumerate(events.itertuples(index=False)):
        etype = row.EVENTMSGTYPE
        action = row.EVENTMSGACTIONTYPE
        upcoming, upcoming_action = next_event[idx]
        raw_gc = R.parse_pctime(row.PCTIMESTRING)
        desc = _describe(row)
        p1_team = float(row.PLAYER1_TEAM_ID) if pd.notna(row.PLAYER1_TEAM_ID) else None

        if period != row.PERIOD:
            period = row.PERIOD
            off_team = None
            last_shot_team = None
            running_min_gc = R.period_length(period)
            begin_chance(R.period_length(period), R.FULL_CLOCK, "period_start", None)

        gc = min(raw_gc, running_min_gc) if raw_gc == raw_gc else running_min_gc
        out_repaired.append(gc != raw_gc)
        running_min_gc = gc

        # --- clock as of this event, before applying any reset this event causes ---
        elapsed = chance_start_gc - gc
        raw_remaining = chance_start_sc - elapsed
        # Two hard invariants: a chance's clock can never exceed the value it started at,
        # and the shot clock is switched off whenever the game clock is shorter.
        remaining = min(raw_remaining, chance_start_sc)
        remaining = R.cap_to_game_clock(remaining, gc)
        out_raw.append(raw_remaining)

        # A shot by the team we think is on defense means we silently missed a possession
        # change (unlogged deflection, clock correction). Restart the chance here rather
        # than emitting a clock that has run past zero, and mark it low confidence.
        shot_event = etype in (R.MADE_FG, R.MISSED_FG)
        if shot_event and off_team is not None and p1_team is not None and p1_team != off_team:
            begin_chance(gc, R.FULL_CLOCK, "inferred_change", p1_team, conf="low")
            remaining = R.cap_to_game_clock(R.FULL_CLOCK, gc)
        elif remaining < 0 and not disable_underflow_guard:
            # Clock ran past zero without a logged reset: same failure, different symptom.
            begin_chance(gc, R.FULL_CLOCK, "inferred_reset", off_team, conf="low")
            remaining = R.cap_to_game_clock(R.FULL_CLOCK, gc)

        out_sc.append(remaining)
        out_off.append(off_team)
        out_chance.append(chance_id)
        out_start_type.append(start_type)
        out_conf.append(confidence)

        # --- apply this event's effect on the following events ---
        if etype in R.INERT:
            continue

        if etype == R.JUMP_BALL:
            # PLAYER3 is the player the tip went to.
            winner = float(row.PLAYER3_TEAM_ID) if pd.notna(row.PLAYER3_TEAM_ID) else None
            begin_chance(gc, R.FULL_CLOCK, "jump_ball", winner)

        elif etype == R.MADE_FG:
            last_shot_team = p1_team
            begin_chance(gc, R.FULL_CLOCK, "after_made_fg", other_team(p1_team))

        elif etype == R.MISSED_FG:
            last_shot_team = p1_team  # no reset; the rebound decides
            rebound_is_live = True

        elif etype == R.FREE_THROW:
            made = "MISS" not in desc.upper()
            if _is_last_free_throw(desc):
                if made:
                    begin_chance(gc, R.FULL_CLOCK, "after_made_ft", other_team(p1_team))
                    rebound_is_live = False
                else:
                    last_shot_team = p1_team  # live rebound follows a missed final FT
                    rebound_is_live = True
            else:
                # Between free throws of a set the ball is dead; any rebound logged here
                # is bookkeeping, not a live board.
                rebound_is_live = False

        elif etype == R.REBOUND:
            reb_team = _rebound_team(row)
            # A team rebound logged immediately before a shot-clock violation is the feed's
            # bookkeeping for the dead ball, not a live board — granting it a reset would
            # hand the offense a fresh 14 seconds at the exact moment its clock expired.
            phantom = (
                upcoming == R.TURNOVER and upcoming_action == R.SHOT_CLOCK_VIOLATION_ACTION
            )
            if reb_team is None or not rebound_is_live or phantom:
                continue
            rebound_is_live = False
            if last_shot_team is not None and reb_team == last_shot_team:
                begin_chance(gc, R.apply_short_reset(remaining, season), "off_rebound", reb_team)
            else:
                begin_chance(gc, R.FULL_CLOCK, "def_rebound", reb_team)

        elif etype == R.TURNOVER:
            begin_chance(gc, R.FULL_CLOCK, "after_turnover", other_team(p1_team))
            rebound_is_live = False

        elif etype == R.FOUL:
            if action in R.TECHNICAL_FOUL_ACTIONS:
                continue  # no possession change, no reset
            if action in R.OFFENSIVE_FOUL_ACTIONS:
                begin_chance(gc, R.FULL_CLOCK, "after_off_foul", other_team(p1_team))
                rebound_is_live = False
            elif upcoming == R.FREE_THROW:
                # Shooting foul, or a common foul in the penalty. Free throws follow and
                # the shot clock is off until they finish; the FT branch handles the reset.
                # The action codes cannot distinguish these cases (a personal foul in the
                # bonus looks identical to one that isn't) — whether FTs actually follow can.
                rebound_is_live = False
            else:
                # Non-shooting defensive foul: offense keeps the ball with a frontcourt reset.
                # PLAYER1 committed the foul, so the offense is the other team.
                offense = other_team(p1_team)
                conf = "high" if offense is not None and offense == off_team else "low"
                begin_chance(gc, R.apply_short_reset(remaining, season), "after_def_foul",
                             offense, conf=conf)
                rebound_is_live = False

        elif etype == R.VIOLATION:
            # Kicked ball (action 1) is a defensive violation -> frontcourt reset.
            # Other violations are ambiguous in the feed; leave the clock running and
            # flag them rather than guessing.
            if action == 1:
                begin_chance(gc, R.apply_short_reset(remaining, season), "after_kicked_ball",
                             off_team)
            else:
                confidence = "low"

    result = events.copy()
    # Low-confidence rows are chances we had to invent a reset for; their clock is a guess
    # that piles up at 24. Emitting NaN loses ~5% of shots but keeps the rest trustworthy —
    # fabricating a value would corrupt the bucket distribution far more than dropping it.
    out_sc = [
        np.nan if conf == "low" else value for value, conf in zip(out_sc, out_conf, strict=True)
    ]
    result["SHOT_CLOCK"] = np.round(out_sc, 3)
    # Pre-clamp value, kept for diagnostics: shot-clock-violation events have a known true
    # clock of exactly 0, so the raw error there measures reconstruction bias directly.
    result["RAW_SHOT_CLOCK"] = np.round(out_raw, 3)
    result["OFF_TEAM_ID"] = out_off
    result["CHANCE_ID"] = out_chance
    result["CHANCE_START_TYPE"] = out_start_type
    result["CLOCK_CONFIDENCE"] = out_conf
    result["GAME_CLOCK_REPAIRED"] = out_repaired
    result["GAME_CLOCK"] = [R.parse_pctime(t) for t in events.PCTIMESTRING]
    return result


def reconstruct_season(
    pbp: pd.DataFrame,
    season: int,
    progress: bool = True,
    delays: dict[str, float] | None = None,
    disable_underflow_guard: bool = False,
) -> pd.DataFrame:
    """Run the reconstruction across every game in a season's play-by-play."""
    games = list(pbp.groupby("GAME_ID", sort=True))
    if progress:
        try:
            from tqdm import tqdm

            games = tqdm(games, desc=f"reconstructing {season}")
        except ImportError:
            pass
    return pd.concat(
        [reconstruct_game(g, season, delays, disable_underflow_guard) for _, g in games],
        ignore_index=True,
    )
