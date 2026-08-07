"""Tests for the conditional rebound model and the possession-level re-pricing.

The claim these protect is arithmetic, not statistical: a shot's value must count the second
chance it can generate, and the continuation value it is compared against must count second
chances the same way. Getting one side and not the other is worse than getting neither, because
it looks like a correction while being a bias.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.rebound import (
    LOOKUP_KEYS,
    _band,
    attach_retention,
    possession_panel,
    published_comparison,
    reprice_shots,
    retention_lookup,
    second_chance_by_clock,
    second_chance_value,
    start_type_advantage,
)


def test_clock_bands_cover_every_second_exactly_once():
    bands = _band(pd.Series(np.arange(0, 25, dtype=float)))
    assert bands.notna().all()
    assert list(bands[:4].unique()) == ["0-3"]
    assert list(bands[4:8].unique()) == ["4-7"]
    assert list(bands[24:].unique()) == ["24-24"]


# ---------------------------------------------------------------------------------------
# Possession chaining
# ---------------------------------------------------------------------------------------


def _chances(rows) -> pd.DataFrame:
    """(START_TYPE, OFF_TEAM_ID, PTS_FG) in order within one game-period."""
    return pd.DataFrame(
        {
            "GAME_ID": "G1",
            "PERIOD": 1,
            "CHANCE_ID": range(len(rows)),
            "START_TYPE": [r[0] for r in rows],
            "OFF_TEAM_ID": [r[1] for r in rows],
            "PTS_FG": [float(r[2]) for r in rows],
        }
    )


def test_a_possession_ends_when_the_ball_changes_hands():
    panel = _chances(
        [
            ("def_rebound", 10, 0),      # miss, then...
            ("off_rebound", 10, 2),      # ...own rebound and a score. One possession, 2 points.
            ("after_made_fg", 20, 3),    # the other team scores; new possession here
            ("def_rebound", 10, 0),
        ]
    )
    out = possession_panel(panel)
    assert list(out.POSSESSION_ID) == [1, 1, 2, 3]
    assert list(out.CHANCES_IN_POSSESSION) == [2, 2, 1, 1]


def test_a_defensive_foul_does_not_end_a_possession():
    """The bug this rule replaced.

    Classifying start types treated everything but `off_rebound` as a new possession, which
    split 102,330 `after_def_foul` chances where the offense keeps the ball 99.7% of the time.
    Reading the offensive team directly needs no such list and cannot go stale when the
    reconstruction gains a start type.
    """
    panel = _chances(
        [
            ("def_rebound", 10, 0),
            ("after_def_foul", 10, 2),      # non-shooting foul: same team, clock resets
            ("after_kicked_ball", 10, 0),   # also the same team
            ("after_made_fg", 20, 2),
        ]
    )
    out = possession_panel(panel)
    assert list(out.POSSESSION_ID) == [1, 1, 1, 2]
    assert list(out.PTS_POSS) == [2.0, 2.0, 0.0, 2.0]


def test_points_run_forward_to_the_end_of_the_possession():
    """`PTS_POSS` is what declining to stop is actually worth, so it looks forward only."""
    panel = _chances(
        [("def_rebound", 10, 0), ("off_rebound", 10, 0), ("off_rebound", 10, 3)]
    )
    out = possession_panel(panel)
    # Every chance in this possession leads to the eventual 3; the last one contains only itself.
    assert list(out.PTS_POSS) == [3.0, 3.0, 3.0]

    panel = _chances([("def_rebound", 10, 2), ("after_made_fg", 20, 3)])
    out = possession_panel(panel)
    assert list(out.PTS_POSS) == [2.0, 3.0]  # separate possessions, no leakage between them


def test_possession_points_never_fall_below_chance_points():
    rng = np.random.default_rng(0)
    teams = rng.choice([10, 20], 500)
    starts = rng.choice(["def_rebound", "off_rebound", "after_made_fg"], 500)
    panel = _chances(list(zip(starts, teams, rng.choice([0, 2, 3], 500), strict=True)))
    out = possession_panel(panel)
    assert (out.PTS_POSS >= out.PTS_FG).all()
    # Total points are conserved: chaining redistributes credit, it does not create any.
    assert out.PTS_FG.sum() == pytest.approx(
        out.groupby("POSSESSION_ID").PTS_POSS.first().sum()
    )


def test_an_unknown_offensive_team_falls_back_to_the_start_type():
    panel = _chances([("def_rebound", 10, 0), ("off_rebound", np.nan, 2)])
    out = possession_panel(panel)
    assert list(out.POSSESSION_ID) == [1, 1]


def test_chaining_does_not_run_across_periods():
    panel = pd.concat(
        [
            _chances([("def_rebound", 10, 2)]),
            _chances([("off_rebound", 10, 3)]).assign(PERIOD=2),
        ]
    )
    out = possession_panel(panel)
    # The same team opening the next period is still a new possession, not a continuation.
    assert list(out.PTS_POSS) == [2.0, 3.0]


# ---------------------------------------------------------------------------------------
# Rates and re-pricing
# ---------------------------------------------------------------------------------------


def _outcomes(zone: str, band_clock: float, n: int, made: int, retained: int) -> pd.DataFrame:
    misses = n - made
    assert retained <= misses, "a made shot cannot be offensively rebounded"
    flags = np.array([1] * made + [0] * misses)
    # The retained flags must land on the *misses*, not the first `retained` rows — the code
    # forces retention false on made shots, so a misaligned fixture silently tests nothing.
    kept = np.array([False] * made + [True] * retained + [False] * (misses - retained))
    return pd.DataFrame(
        {
            "SEASON": 2020,
            "SHOT_ZONE_BASIC": zone,
            "SHOT_CLOCK": band_clock,
            "CLOCK_BAND": _band(pd.Series([band_clock] * n)),
            "SHOT_MADE_FLAG": flags,
            "RETAINED": kept,
            "PLAYER_REBOUND": True,
            "RESOLVED": True,
        }
    )


def test_the_two_rates_are_different_quantities_and_both_are_reported():
    """1000 shots, 600 made. Of the 400 misses, 200 are retained.

    Miss-conditional rate is 200/400 = 0.50. Unconditional retention is 200/1000 = 0.20.
    Confusing them is the mistake this whole module exists to avoid.
    """
    table = _outcomes("Restricted Area", 10.0, n=1000, made=600, retained=200)
    rates = retention_lookup(table)
    assert rates.iloc[0] == pytest.approx(0.20)

    published = published_comparison(table).set_index("measure")
    assert published.iloc[0]["rate"] == pytest.approx(0.50)
    assert published.iloc[0]["n"] == 400  # denominator is misses, not attempts


def test_retention_attaches_by_zone_and_band_and_falls_back_when_unseen():
    table = pd.concat(
        [
            _outcomes("Restricted Area", 10.0, n=1000, made=500, retained=400),
            _outcomes("Mid-Range", 10.0, n=1000, made=500, retained=100),
        ]
    )
    lookup = retention_lookup(table)
    shots = pd.DataFrame(
        {
            "SHOT_ZONE_BASIC": ["Restricted Area", "Mid-Range", "Left Corner 3"],
            "CLOCK_BAND": _band(pd.Series([10.0, 10.0, 10.0])),
        }
    )
    attached = attach_retention(shots, lookup)
    assert attached.iloc[0] == pytest.approx(0.40)
    assert attached.iloc[1] == pytest.approx(0.10)
    # A cell never observed falls back to the pooled rate rather than to NaN, which would
    # silently drop those shots out of every downstream quantile.
    assert attached.iloc[2] == pytest.approx(0.25)
    assert attached.notna().all()
    assert set(LOOKUP_KEYS) <= set(shots.columns)


def test_full_value_adds_the_rebound_option_and_never_subtracts():
    table = _outcomes("Restricted Area", 10.0, n=1000, made=500, retained=300)
    shots = pd.DataFrame(
        {
            "XPTS": [1.0, 0.8],
            "SHOT_CLOCK": [10.0, 10.0],
            "SHOT_ZONE_BASIC": ["Restricted Area", "Restricted Area"],
        }
    )
    priced = reprice_shots(shots, retention_lookup(table), second_chance=1.0)
    assert priced.RETAIN.iloc[0] == pytest.approx(0.30)
    assert priced.FULL_VALUE.iloc[0] == pytest.approx(1.0 + 0.30 * 1.0)
    assert (priced.FULL_VALUE >= priced.XPTS).all()


def _era_panel(era_season: int, off_start: float, off_pts, def_pts) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SEASON": era_season,
            "START_TYPE": ["off_rebound"] * len(off_pts) + ["def_rebound"] * len(def_pts),
            "START_SC": [off_start] * len(off_pts) + [24.0] * len(def_pts),
            "PTS_POSS": list(off_pts) + list(def_pts),
        }
    )


def test_the_advantage_is_only_reported_where_both_start_types_exist():
    """The rule makes the two start types nearly disjoint in start clock after 2018-19.

    A comparison at a clock value only one of them ever reaches is not a comparison, so those
    rows must not appear at all rather than appear with a one-sided count.
    """
    panel = _era_panel(2016, off_start=24.0, off_pts=[1.0] * 600, def_pts=[1.0] * 600)
    lonely = _era_panel(2020, off_start=14.0, off_pts=[2.0] * 600, def_pts=[])
    out = start_type_advantage(pd.concat([panel, lonely], ignore_index=True))
    assert list(out.S) == [24]
    assert out.ERA.iloc[0] == "pre-2018"
    assert out.advantage.iloc[0] == pytest.approx(0.0)


def test_the_advantage_is_measured_within_era_and_within_start_clock():
    panel = pd.concat(
        [
            _era_panel(2016, 24.0, [1.0] * 600, [0.8] * 600),   # pre: +0.2
            _era_panel(2020, 24.0, [1.0] * 600, [1.0] * 600),   # post: 0.0
        ],
        ignore_index=True,
    )
    out = start_type_advantage(panel).set_index("ERA")
    assert out.loc["pre-2018", "advantage"] == pytest.approx(0.2)
    assert out.loc["post-2018", "advantage"] == pytest.approx(0.0)


def test_the_fourteen_second_floor_is_flagged():
    panel = pd.concat(
        [
            _era_panel(2020, 14.0, [1.0] * 2000, []),
            _era_panel(2020, 17.0, [0.9] * 2000, []),
        ],
        ignore_index=True,
    )
    out = second_chance_by_clock(panel).set_index("S")
    assert bool(out.loc[14, "FLOOR_BOUND"]) is True
    assert bool(out.loc[17, "FLOOR_BOUND"]) is False
    assert out.loc[14, "VALUE"] == pytest.approx(1.0)


def test_second_chance_value_separates_rebound_chances_from_fresh_ones():
    panel = pd.DataFrame(
        {
            "START_TYPE": ["off_rebound"] * 3 + ["def_rebound"] * 3,
            "PTS_FG": [3.0, 0.0, 3.0, 2.0, 0.0, 0.0],
            "START_SC": [14.0] * 3 + [24.0] * 3,
            "PERIOD_EXPIRED": False,
        }
    )
    out = second_chance_value(panel)
    assert out["v_off_rebound"] == pytest.approx(2.0)
    assert out["v_fresh"] == pytest.approx(2 / 3)
    assert out["mean_start_sc_off_rebound"] == pytest.approx(14.0)
