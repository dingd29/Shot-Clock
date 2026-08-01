"""Tests for lineup-level scoring and the overlap estimator.

Two of these guard mistakes that were actually made. `event_points` used to be reachable
with its shot-value and free-throw columns absent, in which case every make scored 2 and
every free throw counted as good — wrong, and wrong in a way that still produced a
believable points-per-chance. And the estimator originally treated 4,233 lineups drawn from
300 team-seasons as independent, which inflated the t-statistic from 2.9 to 5.0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.lineup_synergy import event_points, fit_lineup_overlap


def test_event_points_reads_shot_value_and_free_throw_result():
    events = pd.DataFrame(
        {
            "EVENTMSGTYPE": [1, 1, 2, 3, 3, 5],
            "HOMEDESCRIPTION": [
                "Maxey 26' 3PT Jump Shot (3 PTS)",
                None,
                "MISS Embiid 18' Jump Shot",
                "Embiid Free Throw 1 of 2 (1 PTS)",
                None,
                None,
            ],
            "VISITORDESCRIPTION": [
                None,
                "Brown 2' Layup (2 PTS)",
                None,
                None,
                "MISS Brown Free Throw 2 of 2",
                "Brown Bad Pass Turnover",
            ],
        }
    )
    assert event_points(events).tolist() == [3.0, 2.0, 0.0, 1.0, 0.0, 0.0]


def test_event_points_refuses_to_guess_without_descriptions():
    """The old `.get(..., 2)` default scored threes as twos in silence."""
    events = pd.DataFrame({"EVENTMSGTYPE": [1, 3]})
    with pytest.raises(KeyError):
        event_points(events)


def synthetic_panel(n_teams: int = 40, per_team: int = 12, seed: int = 0) -> pd.DataFrame:
    """Lineups whose efficiency depends on team quality but never on overlap.

    A correct estimator must return a coefficient near zero here, whatever it does to the
    standard errors.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for team in range(n_teams):
        team_effect = rng.normal(0, 0.06)
        for _ in range(per_team):
            chances = int(rng.integers(100, 900))
            rows.append(
                {
                    "SEASON": 2020 + team % 3,
                    "TEAM_SEASON": f"{team}:2020",
                    "LINEUP_KEY": f"{team}-{rng.integers(1e9)}",
                    "CHANCES": chances,
                    "OVERLAP": float(rng.normal(0.89, 0.046)),
                    "PRIOR_QUALITY": float(rng.normal(1.07, 0.04)),
                    "PTS_PER_CHANCE": 0.86 + team_effect + rng.normal(0, 0.09),
                }
            )
    return pd.DataFrame(rows)


def test_no_effect_when_none_exists():
    panel = synthetic_panel()
    fit = fit_lineup_overlap(panel, fixed_effects="team_season")
    overlap = fit["coefficients"].set_index("term").loc["overlap"]
    assert abs(overlap.t) < 2.5, f"found an effect in data built without one: t={overlap.t}"


def test_clustering_does_not_shrink_standard_errors():
    """Clustering on correlated groups should widen intervals, never tighten them.

    This is the whole reason to cluster: lineups from one team share players wholesale, so
    the unclustered standard error is an understatement.
    """
    panel = synthetic_panel()
    naive = fit_lineup_overlap(panel, fixed_effects="season", cluster=None)
    clustered = fit_lineup_overlap(panel, fixed_effects="season", cluster="TEAM_SEASON")

    def stderr(fit):
        return fit["coefficients"].set_index("term").loc["overlap", "std_error"]

    assert clustered["n_clusters"] == panel.TEAM_SEASON.nunique()
    assert stderr(clustered) >= 0.95 * stderr(naive)


def test_weights_favour_lineups_that_actually_played():
    """A 900-chance lineup must move the fit more than a 100-chance one."""
    panel = synthetic_panel(seed=3)
    heavy = panel.CHANCES >= panel.CHANCES.median()

    shifted = panel.copy()
    shifted.loc[heavy, "PTS_PER_CHANCE"] += 0.5 * shifted.loc[heavy, "OVERLAP"]
    strong = fit_lineup_overlap(shifted, fixed_effects="team_season")

    shifted_light = panel.copy()
    shifted_light.loc[~heavy, "PTS_PER_CHANCE"] += 0.5 * shifted_light.loc[~heavy, "OVERLAP"]
    weak = fit_lineup_overlap(shifted_light, fixed_effects="team_season")

    coefficient = lambda fit: fit["coefficients"].set_index("term").loc["overlap", "estimate"]  # noqa: E731
    assert coefficient(strong) > coefficient(weak)
