"""Tests for the optimal-stopping model.

The estimator has to recover a known exercise threshold from synthetic chances, and it has to
*fail* to find one when the data contains none. Both matter here more than usual, because the
headline claim is about the shape of a boundary rather than a coefficient with a standard
error.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.stopping import (
    continuation_value,
    exercise_boundary,
    exercise_gap,
    relaxation,
)


def synthetic_chances(n: int = 40_000, seed: int = 0) -> pd.DataFrame:
    """Chances that start at 24, end uniformly, and score more when they end early.

    Built so the continuation value must rise with time remaining: a chance with more clock
    left has more ways to finish well.
    """
    rng = np.random.default_rng(seed)
    start = np.full(n, 24.0)
    end = rng.integers(0, 24, n).astype(float)
    # Longer-lived chances are worse, which is what makes V(t) increasing in t.
    quality = 1.2 - 0.03 * (24 - end)
    points = rng.binomial(1, np.clip(quality / 2.4, 0.01, 0.99), n) * 2.0
    return pd.DataFrame(
        {
            "START_SC": start,
            "END_SC": end,
            "PTS_FG": points,
            "PTS_ALL": points,
            "START_TYPE": "def_rebound",
        }
    )


def test_continuation_value_rises_with_time_remaining():
    """More clock is worth more. If this inverts, the live/continued masks are wrong."""
    values = continuation_value(synthetic_chances(), min_chances=50)
    assert len(values) > 10
    correlation = np.corrcoef(values.SECOND, values.V_CONT)[0, 1]
    assert correlation > 0.8, f"V(t) should increase with t, got r={correlation:.2f}"


def test_continuation_value_excludes_chances_ending_now():
    """V(t) is the value of *declining*, so a chance ending exactly at t must not count."""
    panel = pd.DataFrame(
        {
            "START_SC": [24.0, 24.0, 24.0],
            "END_SC": [10.0, 10.0, 5.0],
            "PTS_FG": [0.0, 0.0, 3.0],
            "PTS_ALL": [0.0, 0.0, 3.0],
            "START_TYPE": "def_rebound",
        }
    )
    values = continuation_value(panel, min_chances=1).set_index("SECOND")
    # At t=10 two chances end and one continues; only the continuing one counts.
    assert values.loc[10, "V_CONT"] == pytest.approx(3.0)
    assert values.loc[10, "N_CONTINUED"] == 1


def test_boundary_recovers_a_known_threshold():
    """Shots generated under a hard rule should show that rule as the accepted floor."""
    rng = np.random.default_rng(3)
    threshold = 0.9
    quality = rng.uniform(0.2, 1.6, 30_000)
    taken = quality >= threshold
    shots = pd.DataFrame(
        {"XPTS": quality[taken], "SHOT_CLOCK": rng.integers(5, 20, taken.sum()).astype(float)}
    )
    values = pd.DataFrame({"SECOND": range(0, 25), "V_CONT": 0.7})

    boundary = exercise_boundary(shots, values, quantile=0.01, min_shots=50)
    assert boundary.BOUNDARY.min() >= threshold - 0.05
    assert boundary.BOUNDARY.max() <= threshold + 0.10


def test_premature_share_is_zero_when_every_shot_beats_continuation():
    shots = pd.DataFrame(
        {"XPTS": np.full(1000, 1.2), "SHOT_CLOCK": np.full(1000, 10.0)}
    )
    values = pd.DataFrame({"SECOND": [10], "V_CONT": [0.7]})
    gap = exercise_gap(shots, values, min_shots=10)
    assert gap.PREMATURE_SHARE.iloc[0] == 0.0
    assert gap.MEAN_SURPLUS.iloc[0] == pytest.approx(0.5)


def test_relaxation_ratio_is_one_when_the_boundary_tracks_value():
    """A team that lowers its standard exactly as fast as V falls scores a ratio near 1.

    This is the null the real result is measured against — the NBA figure is roughly 0.5, so
    the estimator has to be able to return 1 when the behaviour is actually optimal.
    """
    rng = np.random.default_rng(5)
    seconds, rows = np.arange(1, 24), []
    for second in seconds:
        value = 0.30 + 0.022 * second
        # Accept anything above V(t) exactly: the optimal rule.
        quality = value + rng.exponential(0.35, 4000)
        rows.append(pd.DataFrame({"XPTS": quality, "SHOT_CLOCK": float(second)}))
    shots = pd.concat(rows, ignore_index=True)
    values = pd.DataFrame({"SECOND": seconds, "V_CONT": 0.30 + 0.022 * seconds})

    ratios = relaxation(shots, values, quantiles=(0.05, 0.10))
    assert ratios.relaxation_ratio.min() > 0.85, ratios.to_string()
    assert ratios.excess_late_demand.abs().max() < 0.05


def test_player_noise_scale_is_measured_not_assumed():
    """The shrinkage denominator must come from the quantity being shrunk.

    `SURPLUS` is built from model predictions, whose shot-to-shot spread is about 0.3 — not
    the ~1.1 of realised 0/2/3 outcomes that the *making* leaderboard correctly uses. Hard-
    coding the outcome figure inflates assumed noise threefold and drives the signal share to
    exactly zero, hiding real heterogeneity behind an arithmetic error.
    """
    from possval.models.stopping import player_exercise

    rng = np.random.default_rng(9)
    players = np.repeat(np.arange(60), 120)
    skill = np.repeat(rng.normal(0, 0.12, 60), 120)
    shots = pd.DataFrame(
        {
            "PLAYER_ID": players,
            "PLAYER_NAME": [f"P{p}" for p in players],
            "XPTS": 0.9 + skill + rng.normal(0, 0.28, len(players)),
            "SHOT_CLOCK": rng.integers(1, 8, len(players)).astype(float),
        }
    )
    values = pd.DataFrame({"SECOND": range(0, 25), "V_CONT": 0.5})

    result = player_exercise(shots, values, min_late=50)
    assert result.attrs["per_shot_sd"] == pytest.approx(0.28, abs=0.05)
    # Real between-player spread was built in, so it must survive.
    assert result.attrs["signal_share"] > 0.5


def test_player_surplus_is_shot_quality_by_another_name():
    """Guards the negative result, which is easy to lose in a later refactor.

    Subtracting `V(t)` removes almost nothing at player level, because a player's late-clock
    shots spread over roughly the same seconds and `V` enters as a near-constant. If someone
    later "improves" this into a skill ranking, this test should fail first.
    """
    from possval.models.stopping import player_exercise

    rng = np.random.default_rng(12)
    players = np.repeat(np.arange(40), 200)
    quality = np.repeat(rng.uniform(0.7, 1.3, 40), 200)
    shots = pd.DataFrame(
        {
            "PLAYER_ID": players,
            "PLAYER_NAME": [f"P{p}" for p in players],
            "XPTS": quality + rng.normal(0, 0.3, len(players)),
            "SHOT_CLOCK": rng.integers(1, 8, len(players)).astype(float),
        }
    )
    values = pd.DataFrame({"SECOND": range(0, 25), "V_CONT": np.linspace(0.30, 0.62, 25)})

    result = player_exercise(shots, values, min_late=50)
    mean_quality = shots.groupby("PLAYER_ID").XPTS.mean().rename("Q")
    joined = result.merge(mean_quality, on="PLAYER_ID")
    assert joined.SURPLUS.corr(joined.Q) > 0.95


def test_team_relaxation_spread_needs_a_null():
    """Splitting a fixed dataset thirty ways produces spread with or without a team effect.

    The null has to be near the observed spread for the real result to be reported honestly —
    on the real data it is 0.078 against 0.098 observed, so most of the apparent team-to-team
    variation is estimation noise. This checks the null machinery finds spread where teams are
    meaningless by construction.
    """
    from possval.models.stopping import team_relaxation, team_relaxation_null


    shots, panel, teams = _random_team_fixture()

    observed = team_relaxation(shots, panel, min_shots=1000, min_chances=20)
    assert len(observed) == len(teams)
    null = team_relaxation_null(shots, panel, n_draws=3)
    # Teams are random here, so the observed spread should not stand out from the null.
    assert observed.relaxation_ratio.std(ddof=1) < 3 * null["null_mean"]


def _random_team_fixture(seed: int = 21):
    """Chances and shots with team labels that carry no signal, blocked into team-games.

    Shaped like the real thing: two teams per game, a round-robin schedule, and one contiguous
    run of chances per team-game.
    """
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(6)]
    per_block = 50

    rows = []
    for game, (home, away) in enumerate(
        [(h, a) for h in teams for a in teams if h != a] * 20
    ):
        for team in (home, away):
            rows.append(pd.DataFrame({"GAME_ID": game, "TEAM": team}, index=range(per_block)))
    panel = pd.concat(rows, ignore_index=True)

    n = len(panel)
    panel["START_SC"] = 24.0
    panel["END_SC"] = rng.integers(0, 24, n).astype(float)
    # Chances that end with more clock left score better, so V(t) has a genuine slope and the
    # relaxation ratio is well conditioned. On pure noise both drops are ~0 and the ratio
    # explodes, which tests nothing. The relationship is identical for every team.
    scoring = 0.35 + 0.012 * panel.END_SC
    panel["PTS_FG"] = np.where(rng.random(n) < scoring, 2.0, 0.0)
    panel["PTS_ALL"] = panel.PTS_FG
    panel["START_TYPE"] = "def_rebound"

    shot_clock = rng.integers(1, 24, n).astype(float)
    shots = pd.DataFrame(
        {
            "GAME_ID": panel.GAME_ID.to_numpy(),
            "XPTS": 0.7 + 0.012 * shot_clock + rng.normal(0, 0.25, n),
            "SHOT_CLOCK": shot_clock,
            "TEAM_ABBREVIATION": panel.TEAM.to_numpy(),
        }
    )
    return shots, panel, teams


def test_null_permutes_team_games_rather_than_resampling_rows():
    """The three properties an earlier `rng.choice` version got wrong.

    Resampling with replacement equalised group sizes and scattered a team's chances across
    unrelated games, and panel and shots were drawn independently so a fake team's continuation
    value was paired with somebody else's shots. All three make the null too tight, which
    overstates how much real team signal survives.
    """
    from possval.models import stopping

    shots, panel, _ = _random_team_fixture()
    seen = []

    real_team_relaxation = stopping.team_relaxation

    def capture(fake_shots, fake_panel, **kwargs):
        seen.append((fake_shots, fake_panel))
        return real_team_relaxation(fake_shots, fake_panel, **kwargs)

    stopping.team_relaxation = capture
    try:
        stopping.team_relaxation_null(shots, panel, n_draws=2, min_shots=1000, min_chances=20)
    finally:
        stopping.team_relaxation = real_team_relaxation

    assert seen, "the null never called team_relaxation"
    real_game = panel.GAME_ID.to_numpy()
    real_team = panel.TEAM.to_numpy()

    for fake_shots, fake_panel in seen:
        fake = fake_panel.TEAM.to_numpy()
        blocks = pd.DataFrame(
            {"game": real_game, "real": real_team, "fake": fake}
        ).drop_duplicates()

        # Whole team-games move together: one real block never splits across fake labels.
        assert len(blocks) == blocks[["game", "real"]].drop_duplicates().shape[0]

        # Permutation, not resampling: each label ends up with exactly as many team-games as
        # it really had. Drawing with replacement instead pulls every group toward n/30, which
        # tightens the null and overstates the surviving signal.
        pd.testing.assert_series_equal(
            blocks.fake.value_counts().sort_index(),
            blocks.real.value_counts().sort_index(),
            check_names=False,
        )

        # One mapping drives both frames, so a fake team's chances and its shots come from the
        # same team-games rather than from unrelated draws.
        assert (fake == fake_shots.TEAM_ABBREVIATION.to_numpy()).all()
