"""Tests for the pre-registered situational analyses (H4 and H5).

The pre-registration commits to validating the band estimator "by recovering a known ratio on
synthetic data before it touches real shots". That is what most of this file is: a world where
the answer is known by construction, and an estimator that has to return it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.situational import (
    BANDS,
    _herfindahl,
    _weighted_slope,
    band_relaxation,
    concentration_panel,
    fit_concentration,
)

# ---------------------------------------------------------------------------------------
# H4: the band estimator
# ---------------------------------------------------------------------------------------


def test_weighted_slope_recovers_a_known_line():
    x = np.arange(10.0)
    assert _weighted_slope(x, 3.0 + 2.5 * x, np.ones(10)) == pytest.approx(2.5)


def test_weights_decide_which_points_the_slope_listens_to():
    """A second of the clock backed by 40,000 shots must outvote one backed by 300."""
    # The outlier sits off-centre on purpose: a point at the weighted mean of `x` has no
    # leverage on a slope at any weight, so an outlier placed there would test nothing.
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 1.0, 10.0, 3.0])  # a clean slope of 1, plus one wild reading at x = 2
    heavy = _weighted_slope(x, y, np.array([1000.0, 1000.0, 1.0, 1000.0]))
    even = _weighted_slope(x, y, np.ones(4))
    assert heavy == pytest.approx(1.0, abs=0.01)
    assert even == pytest.approx(1.8, abs=0.01)
    assert even > heavy


def _synthetic(boundary_slope: float, value_slope: float, seconds=range(0, 24)):
    """Shots whose 5th-percentile XPTS is an exact line, and a matching value curve.

    `offsets` is symmetric with an empirical 5th percentile of exactly -0.9, and the same
    offsets are used at every second, so the fitted boundary slope is the slope of `b(t)` with
    no sampling noise at all. That is the point: an estimator that cannot recover a ratio in a
    world with zero noise will not recover one in a world with plenty.
    """
    offsets = np.linspace(-1.0, 1.0, 201)
    rows, values = [], []
    for t in seconds:
        boundary = 1.0 + boundary_slope * t
        rows.append(pd.DataFrame({"SHOT_CLOCK": float(t), "XPTS": boundary + offsets}))
        values.append({"SECOND": t, "V_CONT": 0.3 + value_slope * t, "N_CONTINUED": 5_000})
    return pd.concat(rows, ignore_index=True), pd.DataFrame(values)


def test_band_relaxation_recovers_a_known_ratio():
    """Boundary moving at half the rate of value is a ratio of 0.5, in every band."""
    shots, values = _synthetic(boundary_slope=0.02, value_slope=0.04)
    out = band_relaxation(shots, values).set_index("BAND")

    assert set(out.index) == set(BANDS)
    for band in BANDS:
        assert out.loc[band, "relaxation_ratio"] == pytest.approx(0.5, abs=1e-6)
        assert out.loc[band, "boundary_slope"] == pytest.approx(0.02, abs=1e-6)


def test_band_relaxation_separates_bands_that_actually_differ():
    """The whole point of banding: one number per possession cannot see this.

    An offense that tracks value perfectly early and stops relaxing entirely late has an
    average ratio around 0.5 and two bands that are nowhere near it.
    """
    offsets = np.linspace(-1.0, 1.0, 201)
    rows, values = [], []
    for t in range(0, 24):
        # Boundary tracks value 1:1 above 8 seconds, then goes flat.
        boundary = 1.0 + 0.04 * max(t, 8)
        rows.append(pd.DataFrame({"SHOT_CLOCK": float(t), "XPTS": boundary + offsets}))
        values.append({"SECOND": t, "V_CONT": 0.3 + 0.04 * t, "N_CONTINUED": 5_000})

    out = band_relaxation(pd.concat(rows, ignore_index=True), pd.DataFrame(values)).set_index(
        "BAND"
    )
    assert out.loc["early", "relaxation_ratio"] == pytest.approx(1.0, abs=1e-6)
    assert out.loc["late", "relaxation_ratio"] == pytest.approx(0.0, abs=1e-6)


def test_a_flat_value_curve_is_refused_rather_than_divided_by():
    """The ratio's denominator is a fitted slope; near zero it produces noise, not effects."""
    shots, values = _synthetic(boundary_slope=0.02, value_slope=0.0)
    assert band_relaxation(shots, values).empty


def test_thin_seconds_do_not_silently_shrink_a_band():
    """A band that loses most of its seconds to the shot threshold is not the registered band."""
    shots, values = _synthetic(boundary_slope=0.02, value_slope=0.04)
    # Only 201 shots per second exist, so a 500-shot threshold empties every second.
    assert band_relaxation(shots, values, min_shots_per_second=500).empty


# ---------------------------------------------------------------------------------------
# H5: concentration
# ---------------------------------------------------------------------------------------


def test_herfindahl_endpoints():
    assert _herfindahl(pd.Series([100])) == pytest.approx(1.0)
    assert _herfindahl(pd.Series([25, 25, 25, 25])) == pytest.approx(0.25)
    assert _herfindahl(pd.Series([0])) != _herfindahl(pd.Series([0]))  # NaN, no attempts


def _usage_frames(late_shares: dict[str, list[int]], seed: int = 0):
    """Shots and chances for one season, with per-team late-clock usage set by hand."""
    rng = np.random.default_rng(seed)
    shots, chances = [], []
    for team, counts in late_shares.items():
        for player, n in enumerate(counts):
            shots.append(
                pd.DataFrame(
                    {
                        "SEASON": 2020,
                        "TEAM_ABBREVIATION": team,
                        "PLAYER_ID": player,
                        "SHOT_CLOCK": rng.integers(1, 8, n).astype(float),
                    }
                )
            )
        # Early-clock attempts, evenly spread, so HHI_ALL differs from HHI_LATE.
        for player in range(5):
            shots.append(
                pd.DataFrame(
                    {
                        "SEASON": 2020,
                        "TEAM_ABBREVIATION": team,
                        "PLAYER_ID": player,
                        "SHOT_CLOCK": rng.integers(12, 24, 400).astype(float),
                    }
                )
            )
        n_chances = 4_000
        end = rng.integers(0, 24, n_chances)
        chances.append(
            pd.DataFrame(
                {
                    "SEASON": 2020,
                    "TEAM": team,
                    "GAME_ID": rng.integers(0, 82, n_chances).astype(str),
                    "START_SC": 24.0,
                    "END_SC": end.astype(float),
                    "PTS_FG": rng.choice([0.0, 2.0, 3.0], n_chances),
                    "PERIOD_EXPIRED": False,
                }
            )
        )
    return pd.concat(shots, ignore_index=True), pd.concat(chances, ignore_index=True)


def test_concentration_ranks_teams_the_way_the_index_should():
    shots, chances = _usage_frames(
        {
            "AAA": [800, 0, 0, 0, 0],  # one player takes every late shot
            "BBB": [160, 160, 160, 160, 160],  # five players share evenly
        }
    )
    out = concentration_panel(shots, chances).set_index("TEAM")
    assert out.loc["AAA", "HHI_LATE"] == pytest.approx(1.0)
    assert out.loc["BBB", "HHI_LATE"] == pytest.approx(0.2)
    assert out.loc["AAA", "TOP_LATE_SHARE"] == pytest.approx(1.0)
    # Both teams spread their early offense evenly, so the funnel separates them even though
    # a raw HHI would partly be measuring the same thing twice.
    assert out.loc["AAA", "FUNNEL"] > out.loc["BBB", "FUNNEL"]


def test_the_outcome_and_the_control_use_disjoint_chances():
    """Registered in advance: a shared sample would manufacture the correlation being tested."""
    shots, chances = _usage_frames({"AAA": [400] * 2, "BBB": [200] * 4})
    out = concentration_panel(shots, chances).set_index("TEAM")
    live = chances[(chances.START_SC >= 7) & (chances.END_SC <= 7)]
    for team in ("AAA", "BBB"):
        assert out.loc[team, "N_LATE_CHANCES"] == (live.TEAM == team).sum()
        assert (
            out.loc[team, "N_LATE_CHANCES"] + out.loc[team, "N_EARLY_CHANCES"]
            == (chances.TEAM == team).sum()
        )


def test_teams_below_the_attempt_threshold_are_dropped_not_estimated():
    shots, chances = _usage_frames({"AAA": [400, 400], "BBB": [10, 10]})
    assert set(concentration_panel(shots, chances).TEAM) == {"AAA"}


def _regression_panel(effect: float, seed: int = 0, n_teams: int = 30, n_seasons: int = 7):
    """Team-seasons where the true concentration effect is `effect`, with a team random effect.

    The team effect is what makes clustering necessary: without it, clustered and plain
    standard errors would agree and the test would prove nothing.
    """
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(n_teams)]
    team_effect = dict(zip(teams, rng.normal(0, 0.08, n_teams), strict=True))
    rows = []
    for season in range(2015, 2015 + n_seasons):
        for team in teams:
            hhi = float(np.clip(rng.normal(0.2, 0.05), 0.05, 0.9))
            early = float(rng.normal(1.05, 0.05))
            rows.append(
                {
                    "SEASON": season,
                    "TEAM": team,
                    "HHI_LATE": hhi,
                    "PPC_EARLY": early,
                    "PPC_LATE": 0.6
                    + effect * hhi
                    + 0.5 * early
                    + team_effect[team]
                    + rng.normal(0, 0.03),
                }
            )
    return pd.DataFrame(rows)


def test_a_real_effect_is_recovered_and_a_null_is_not_invented():
    strong = fit_concentration(_regression_panel(effect=1.0), n_draws=499)
    assert strong["estimate"] == pytest.approx(1.0, abs=0.25)
    assert strong["p_wild"] < 0.05
    assert strong["n_teams"] == 30

    nothing = fit_concentration(_regression_panel(effect=0.0, seed=7), n_draws=499)
    assert nothing["p_wild"] > 0.10
    assert abs(nothing["estimate"]) < 0.25


def test_the_effect_is_reported_per_standard_deviation_of_concentration():
    """A coefficient per unit of Herfindahl index is not a number anyone can picture."""
    table = _regression_panel(effect=1.0)
    fit = fit_concentration(table, n_draws=99)
    assert fit["effect_per_sd"] == pytest.approx(fit["estimate"] * fit["treatment_sd"])
    assert 0.02 < fit["treatment_sd"] < 0.10
