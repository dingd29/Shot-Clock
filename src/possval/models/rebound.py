"""What happens to a shot after it misses, conditioned on what kind of shot it was.

Everything in `stopping.py` compares a shot's value against the value of continuing. Both
sides of that comparison omit the same thing: **a missed shot can come back.** An offensive
rebound starts a *new* chance, so its points are attributed to that chance and appear in
neither `XPTS` nor `V(t)`.

That omission would be harmless if the rebound probability were constant. It is not, and the
spread is first-order — a missed shot in the restricted area is retained about 41% of the time
against about 24% for a mid-range miss. So the full value of taking a shot is

    XPTS + P(retain | shot) * V(second chance)

and the correction is larger for exactly the shots offenses take when the clock is dying.

Two different rates are computed here and they must not be confused:

  `ORB_RATE`      share of *missed* field goals the offense recovers. Comparable in spirit to
                  published offensive-rebound percentage, and reported for validation.
  `RETAIN_RATE`   share of *all* attempts after which the offense still has the ball. This is
                  the quantity the valuation needs, and it is the one that multiplies into the
                  boundary correction.

Possession is decided from which description column the event was logged in, not from team
ids. A rebound logged in `HOMEDESCRIPTION` following a shot logged in `HOMEDESCRIPTION` is an
offensive rebound. That rule costs nothing and handles the 15.6% of rebounds credited to a
team rather than a player, which carry no `PLAYER1_TEAM_ID` at all and which a team-id join
would silently drop — and dropping them would bias the rate, since a ball knocked out of
bounds off the defense is exactly a retained possession.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.paths import PROCESSED

MISSED_FG, REBOUND = 2, 4
FULL_CLOCK_SECONDS = 24

# Backcourt attempts are buzzer heaves. They are recovered 98% of the time because the period
# ends and the feed logs a bookkeeping team rebound, which is not a basketball event and would
# put a spurious 0.98 retention on the longest shots in the data.
EXCLUDED_ZONES = ("Backcourt",)

# Clock bands, matching `situational.BANDS` plus the reset instant, so the rebound table and
# the boundary tables are cut the same way.
CLOCK_BANDS = [(0, 3), (4, 7), (8, 15), (16, 23), (24, 24)]


def _band(clock: pd.Series) -> pd.Series:
    seconds = clock.round().clip(0, 24)
    labels = [f"{low}-{high}" for low, high in CLOCK_BANDS]
    edges = [-0.5] + [high + 0.5 for _, high in CLOCK_BANDS]
    return pd.cut(seconds, bins=edges, labels=labels, ordered=True)


def shot_outcomes(first: int = 2015, last: int = 2024) -> pd.DataFrame:
    """One row per field-goal attempt: did it go in, and did the offense keep the ball.

    `RETAINED` is false for a made shot by construction, which is what makes the unconditional
    rate directly usable as `P(retain | shot)`.
    """
    frames = []
    for season in range(first, last + 1):
        pbp_path = PROCESSED / f"pbp_clock_{season}.parquet"
        shot_path = PROCESSED / f"shots_clock_{season}.parquet"
        if not (pbp_path.exists() and shot_path.exists()):
            continue
        events = pd.read_parquet(
            pbp_path,
            columns=[
                "GAME_ID", "EVENTNUM", "EVENTMSGTYPE",
                "HOMEDESCRIPTION", "VISITORDESCRIPTION", "PLAYER1_TEAM_ID",
            ],
        ).sort_values(["GAME_ID", "EVENTNUM"]).reset_index(drop=True)

        side = np.where(
            events.HOMEDESCRIPTION.notna(), "H",
            np.where(events.VISITORDESCRIPTION.notna(), "V", None),
        )
        events["SIDE"] = side
        following = events.shift(-1)
        is_rebound = (
            (events.EVENTMSGTYPE == MISSED_FG)
            & (following.EVENTMSGTYPE == REBOUND)
            & (events.GAME_ID == following.GAME_ID)
            & events.SIDE.notna()
            & following.SIDE.notna()
        )
        recovered = events.loc[is_rebound, ["GAME_ID", "EVENTNUM"]].assign(
            RETAINED=(events.SIDE[is_rebound] == following.SIDE[is_rebound]).to_numpy(),
            # A team rebound carries no player, and box-score offensive-rebound totals do not
            # count it. Kept, but flagged, so the published-comparison rate can exclude it.
            PLAYER_REBOUND=following.PLAYER1_TEAM_ID[is_rebound].notna().to_numpy(),
        )

        shots = pd.read_parquet(shot_path)
        shots = shots[~shots.SHOT_ZONE_BASIC.isin(EXCLUDED_ZONES)]
        merged = shots.merge(
            recovered, left_on=["GAME_ID", "GAME_EVENT_ID"], right_on=["GAME_ID", "EVENTNUM"],
            how="left",
        )
        # A made shot is never retained; a miss with no locatable rebound event (0.3%, almost
        # all period-ending) is unknown rather than false and is dropped from rate denominators.
        made = merged.SHOT_MADE_FLAG == 1
        merged["RETAINED"] = np.where(made, False, merged.RETAINED)
        merged["RESOLVED"] = made | merged.RETAINED.notna()
        merged["IS_3"] = merged.SHOT_TYPE.astype(str).str.contains("3").astype(int)
        merged["CLOCK_BAND"] = _band(merged.SHOT_CLOCK)
        frames.append(
            merged[
                # TEAM_ID rather than TEAM_ABBREVIATION: `shotdetail` carries the id and the
                # name but not the abbreviation, which is the same absence that once left
                # `synergy.ORTG_FG` silently all-null.
                ["GAME_ID", "GAME_EVENT_ID", "SEASON", "PLAYER_ID", "TEAM_ID",
                 "SHOT_CLOCK", "CLOCK_BAND", "SHOT_ZONE_BASIC", "SHOT_DISTANCE", "IS_3",
                 "SHOT_MADE_FLAG", "RETAINED", "PLAYER_REBOUND", "RESOLVED"]
            ]
        )
    if not frames:
        raise SystemExit("no reconstructed seasons found — run `make clock` first")
    out = pd.concat(frames, ignore_index=True)
    # `RESOLVED` already records which rows this is guessing at, and rate denominators use it,
    # so filling the unresolved 0.7% with False is bookkeeping rather than an assumption.
    out["RETAINED"] = np.where(out.RETAINED.isna(), False, out.RETAINED).astype(bool)
    return out


def published_comparison(table: pd.DataFrame) -> pd.DataFrame:
    """The rate a reader can check against public offensive-rebound percentage.

    The two numbers are not the same quantity and the difference is not a defect:

      - Box-score offensive-rebound percentage counts only rebounds credited to a *player*.
        A ball knocked out of bounds off the defense is a team rebound; the offense keeps the
        ball and the box score records nothing.
      - It also pools missed free throws, which are recovered far less often, dragging the
        pooled figure down relative to a field-goal-only rate.

    Restricting to player rebounds off missed field goals gives about 26.6%, against a
    published league figure near 24% for 2022-23. **A gap of roughly 1.6pp remains and is not
    explained here.** It is small relative to the 17pp spread across zones that the valuation
    actually rests on, but it is a level disagreement and is reported as one rather than
    described as a match.
    """
    misses = table[(table.SHOT_MADE_FLAG == 0) & table.RESOLVED]
    rows = []
    for label, frame in [
        ("all rebounds off missed FG (retention, used for valuation)", misses),
        ("player rebounds only (box-score comparable)", misses[misses.PLAYER_REBOUND]),
    ]:
        rows.append(
            {
                "measure": label,
                "n": len(frame),
                "rate": float(frame.RETAINED.mean()),
            }
        )
    return pd.DataFrame(rows)


def rebound_rates(table: pd.DataFrame, by: list[str], min_shots: int = 500) -> pd.DataFrame:
    """Conditional rebound rates, both the miss-conditional and the unconditional form."""
    resolved = table[table.RESOLVED]
    grouped = resolved.groupby(by, observed=True)
    out = pd.DataFrame(
        {
            "N_ATTEMPTS": grouped.size(),
            "RETAIN_RATE": grouped.RETAINED.mean(),
            "MISS_RATE": 1 - grouped.SHOT_MADE_FLAG.mean(),
        }
    )
    misses = resolved[resolved.SHOT_MADE_FLAG == 0].groupby(by, observed=True)
    out["N_MISSES"] = misses.size()
    out["ORB_RATE"] = misses.RETAINED.mean()
    out = out[out.N_ATTEMPTS >= min_shots]
    return out.reset_index().sort_values("RETAIN_RATE")


# The lookup used to attach `P(retain)` to individual shots. Zone crossed with clock band is
# deliberately coarse: with ~2M attempts every cell is enormous, the structure is monotone and
# interpretable, and a fitted model would buy little while adding a way to overfit. The
# stability check below is what justifies the choice rather than an assertion that it is fine.
LOOKUP_KEYS = ["SHOT_ZONE_BASIC", "CLOCK_BAND"]


def retention_lookup(table: pd.DataFrame, min_shots: int = 500) -> pd.Series:
    rates = rebound_rates(table, LOOKUP_KEYS, min_shots=min_shots)
    return rates.set_index(LOOKUP_KEYS).RETAIN_RATE


def attach_retention(
    shots: pd.DataFrame, lookup: pd.Series, fallback: float | None = None
) -> pd.Series:
    """`P(retain | shot)` per row, from the lookup, falling back to the pooled rate."""
    keys = pd.MultiIndex.from_arrays([shots[k] for k in LOOKUP_KEYS])
    attached = pd.Series(lookup.reindex(keys).to_numpy(), index=shots.index)
    return attached.fillna(lookup.mean() if fallback is None else fallback)


def reprice_shots(
    shots: pd.DataFrame, lookup: pd.Series, second_chance: float
) -> pd.DataFrame:
    """Add `RETAIN` and `FULL_VALUE = XPTS + P(retain) * V(second chance)` to scored shots.

    `second_chance` must be the possession-level value of an offensive-rebound chance — that
    chance plus anything it goes on to generate — so that a shot's value and the continuation
    value it is compared against count second chances the same way.
    """
    frame = shots.copy()
    if "CLOCK_BAND" not in frame:
        frame["CLOCK_BAND"] = _band(frame.SHOT_CLOCK)
    frame["RETAIN"] = attach_retention(frame, lookup)
    frame["FULL_VALUE"] = frame.XPTS + frame.RETAIN * second_chance
    return frame


def lookup_stability(table: pd.DataFrame, holdout_seasons: tuple[int, ...] = (2023, 2024)) -> dict:
    """Does a lookup fitted on early seasons still hold on later ones?

    The argument for a table over a model is that the structure is stable enough not to need
    one. That is a claim, so it is tested: fit on everything before the holdout, score on the
    holdout, and report the mean absolute cell error and the correlation across cells.
    """
    train = table[~table.SEASON.isin(holdout_seasons)]
    test = table[table.SEASON.isin(holdout_seasons)]
    fitted = retention_lookup(train)
    actual = retention_lookup(test)
    shared = fitted.index.intersection(actual.index)
    difference = (fitted.loc[shared] - actual.loc[shared]).abs()
    return {
        "n_cells": len(shared),
        "mean_abs_error_pp": float(100 * difference.mean()),
        "max_abs_error_pp": float(100 * difference.max()),
        "correlation": float(np.corrcoef(fitted.loc[shared], actual.loc[shared])[0, 1]),
    }


RULE_SEASON = 2018
SHORT_RESET = 14


def start_type_advantage(panel: pd.DataFrame, min_chances: int = 500) -> pd.DataFrame:
    """Is a second chance worth more than a fresh possession *at the same start clock*?

    The raw comparison says yes and the raw comparison is composition. Offensive-rebound
    chances average a 15.4-second start against 23.9 for a fresh possession, so any pooled gap
    mixes the scrambled-defense story with a clock difference running the other way.

    The two start types barely overlap in start clock — which is what the rule guarantees — so
    the only window where both are well populated is a full 24. **Before 2018-19 that window is
    the whole sample**, because an offensive rebound then reset to 24 exactly as a defensive one
    did. That era is therefore the clean test, and it needs no adjustment at all.
    """
    frame = panel.copy()
    frame["S"] = frame.START_SC.round().clip(0, FULL_CLOCK_SECONDS).astype(int)
    frame["ERA"] = np.where(frame.SEASON >= RULE_SEASON, "post-2018", "pre-2018")
    both = frame[frame.START_TYPE.isin(["off_rebound", "def_rebound"])]
    grouped = both.groupby(["ERA", "S", "START_TYPE"], observed=True).PTS_POSS.agg(
        ["size", "mean"]
    )
    wide = grouped.unstack("START_TYPE")
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.dropna()
    wide = wide[
        (wide.size_off_rebound >= min_chances) & (wide.size_def_rebound >= min_chances)
    ]
    wide["advantage"] = wide.mean_off_rebound - wide.mean_def_rebound
    return wide.reset_index()


def second_chance_by_clock(
    panel: pd.DataFrame, era: str = "post-2018", min_chances: int = 1_000
) -> pd.DataFrame:
    """What a second chance is worth as a function of the clock it is given.

    The 14-second floor binds on about 70% of post-2018 offensive rebounds, which piles them on
    a single start value and leaves the 15-23 range populated only by rebounds that arrived
    early enough to keep more time.

    **This curve is not a causal schedule of what a second of reset is worth.** Start clock is
    decided by when the rebound happened, which is decided by what kind of shot preceded it, so
    moving along the curve changes the population as well as the clock. It answers "what are
    second chances with `s` seconds worth", not "what would this second chance be worth with one
    more second".
    """
    frame = panel.copy()
    frame["S"] = frame.START_SC.round().clip(0, FULL_CLOCK_SECONDS).astype(int)
    frame = frame[frame.SEASON >= RULE_SEASON] if era == "post-2018" else frame[
        frame.SEASON < RULE_SEASON
    ]
    rebounds = frame[frame.START_TYPE == "off_rebound"]
    table = rebounds.groupby("S").PTS_POSS.agg(N="size", VALUE="mean")
    table["FLOOR_BOUND"] = table.index == SHORT_RESET
    return table[table.N >= min_chances].reset_index()


def possession_panel(
    panel: pd.DataFrame,
    points_column: str = "PTS_FG",
) -> pd.DataFrame:
    """Chain chances into possessions and add points from each chance to the possession's end.

    A "chance" is one shot-clock interval; a "possession" runs until the defense gets the ball.
    An offensive rebound ends a chance and not a possession, which is the distinction the whole
    repo rests on — and it is also the reason `V(t)` was understated. `V(t)` was built from
    `PTS_FG` of the current *chance*, so the points an offense goes on to score after rebounding
    its own miss were credited to a different row and counted on neither side of the
    shoot-or-hold comparison.

    `PTS_POSS` is points from this chance to the end of its possession, which is the correct
    outcome for a continuation value: it is what the offense actually gets by not stopping.
    The default keeps the historical field-goal-only unit. Passing `PTS_ALL` is the explicit
    all-points specification used to audit shooting-foul accounting; callers must never change
    units implicitly.
    """
    if points_column not in panel:
        raise KeyError(f"panel has no points column {points_column!r}")
    ordered = panel.sort_values(["GAME_ID", "PERIOD", "CHANCE_ID"]).copy()

    # A possession ends when the ball changes hands, so read that directly off the offensive
    # team rather than trying to classify start types. Classifying them was wrong: an earlier
    # version treated everything but `off_rebound` as a new possession, which silently split
    # 102,330 `after_def_foul` chances (the offense keeps the ball 99.7% of the time) and 3,057
    # `after_kicked_ball` chances (95.5%). It found 10.5% of chances to be continuations where
    # the truth is 20.8%, and it broke the accounting identity that ending a possession at `S`
    # is worth exactly minus the value of starting one there.
    team = ordered.OFF_TEAM_ID if "OFF_TEAM_ID" in ordered else ordered.TEAM
    previous = team.groupby([ordered.GAME_ID, ordered.PERIOD], sort=False).shift()
    opens = np.where(
        previous.isna(),  # first chance of a period always opens one
        True,
        np.where(
            team.notna(),
            team.ne(previous),
            # 0.03% of chances carry no offensive team; fall back to the start type there.
            ordered.START_TYPE.ne("off_rebound"),
        ),
    ).astype(int)
    ordered["POSSESSION_ID"] = (
        pd.Series(opens, index=ordered.index)
        .groupby([ordered.GAME_ID, ordered.PERIOD], sort=False)
        .cumsum()
    )

    grouped = ordered.groupby(["GAME_ID", "PERIOD", "POSSESSION_ID"], sort=False)[points_column]
    # Reverse cumulative sum, vectorised: total minus the exclusive running sum. A per-group
    # lambda over 600k groups is minutes; this is seconds.
    ordered["PTS_POSS"] = (
        grouped.transform("sum") - grouped.cumsum() + ordered[points_column]
    )
    ordered["CHANCES_IN_POSSESSION"] = grouped.transform("size")
    return ordered


def second_chance_value(panel: pd.DataFrame, drop_period_expiry: bool = True) -> dict:
    """What a chance started by an offensive rebound is actually worth.

    This is the `V(second chance)` that multiplies the retention probability. It is measured
    directly from chances the reconstruction labels `off_rebound`, rather than assumed equal
    to a fresh possession — which it is not, because the reset is 14 seconds rather than 24.
    """
    if drop_period_expiry and "PERIOD_EXPIRED" in panel.columns:
        panel = panel[~panel.PERIOD_EXPIRED]
    off_rebound = panel[panel.START_TYPE == "off_rebound"]
    fresh = panel[panel.START_TYPE.isin(["def_rebound", "after_made_fg", "after_turnover"])]
    return {
        "n_off_rebound": len(off_rebound),
        "v_off_rebound": float(off_rebound.PTS_FG.mean()),
        "n_fresh": len(fresh),
        "v_fresh": float(fresh.PTS_FG.mean()),
        "mean_start_sc_off_rebound": float(off_rebound.START_SC.mean()),
        "mean_start_sc_fresh": float(fresh.START_SC.mean()),
    }
