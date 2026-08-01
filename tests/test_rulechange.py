"""Tests for the 2018-19 rule-change natural experiment."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.rulechange import (
    CONTROL,
    RULE_SEASON,
    TREATED,
    base_sensitivity,
    difference_in_differences,
    event_study,
)


def synthetic_chances(effect: float = -0.30, seed: int = 0, n: int = 4000) -> pd.DataFrame:
    """Chances where only the treated group shortens, and only after the rule season."""
    rng = np.random.default_rng(seed)
    rows = []
    for season in range(RULE_SEASON - 3, RULE_SEASON + 4):
        drift = 0.05 * (season - RULE_SEASON)  # a trend both groups share
        for start in (TREATED, CONTROL):
            treated = start == TREATED
            shift = effect if treated and season >= RULE_SEASON else 0.0
            base = 5.0 if treated else 10.0
            rows.append(
                pd.DataFrame(
                    {
                        "SEASON": season,
                        "START": start,
                        "DURATION": rng.normal(base + drift + shift, 3.0, n),
                        "PTS": rng.normal(0.9, 1.2, n),
                    }
                )
            )
    table = pd.concat(rows, ignore_index=True)
    table["TREATED"] = (table.START == TREATED).astype(float)
    table["POST"] = (table.SEASON >= RULE_SEASON).astype(float)
    return table


def test_recovers_a_known_effect():
    table = synthetic_chances(effect=-0.30)
    estimate = difference_in_differences(table, "DURATION")
    assert estimate["estimate"] == pytest.approx(-0.30, abs=0.12)
    assert estimate["t"] < -2


def test_shared_trend_does_not_create_an_effect():
    """A drift affecting both groups equally is what the design exists to remove."""
    table = synthetic_chances(effect=0.0)
    estimate = difference_in_differences(table, "DURATION")
    assert abs(estimate["t"]) < 2.5, f"found an effect where none was built: t={estimate['t']}"


def test_placebo_on_an_untouched_outcome():
    """Points were generated independently of treatment, so the DiD must find nothing."""
    table = synthetic_chances(effect=-0.30)
    assert abs(difference_in_differences(table, "PTS")["t"]) < 2.5


def test_event_study_is_flat_before_and_steps_after():
    table = synthetic_chances(effect=-0.30)
    study = event_study(table, "DURATION", base_season=RULE_SEASON - 1).set_index("SEASON")

    before = study.loc[: RULE_SEASON - 1, "relative_to_base"]
    after = study.loc[RULE_SEASON:, "relative_to_base"]
    assert before.abs().max() < 0.25, "pre-period should be flat"
    assert after.max() < -0.15, "every post-period season should sit below the baseline"


def test_baseline_sensitivity_covers_the_choices():
    table = synthetic_chances(effect=-0.30)
    sensitivity = base_sensitivity(table, "DURATION")
    assert set(sensitivity.baseline) == {
        "vs 2017-18 only",
        "vs 2015-16 and 2016-17",
        "vs all three pre-seasons",
    }
    # With a genuinely flat pre-period, the baseline choice should barely matter.
    assert sensitivity.change.max() - sensitivity.change.min() < 0.25
