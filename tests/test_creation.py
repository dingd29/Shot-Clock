"""Tests for creation profiles and overlap.

The bounds test exists because of a real bug: `profiles["FGA"] = totals` silently became
`('FGA', '')` under MultiIndex columns, so the "exclude FGA" filter never matched and a raw
attempt count was fed into the divergence maths. Similarity came out at -212 instead of a
number in [0, 1]. Any measure with known bounds should assert them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possval.models.creation import (
    creation_profiles,
    lineup_overlap,
    overlap_matrix,
    profile_cells,
)


def synthetic_shots(n_players: int = 6, per_player: int = 400, seed: int = 0) -> pd.DataFrame:
    """Shots with deliberately different clock/zone tendencies per player."""
    rng = np.random.default_rng(seed)
    rows = []
    for pid in range(n_players):
        # Alternate players between early-clock rim finishing and late-clock jumpers.
        early = pid % 2 == 0
        clocks = rng.normal(18 if early else 6, 3, per_player).clip(0, 24)
        zones = rng.choice(
            ["Restricted Area", "Mid-Range"],
            per_player,
            p=[0.7, 0.3] if early else [0.2, 0.8],
        )
        for clock, zone in zip(clocks, zones, strict=True):
            rows.append(
                {
                    "PLAYER_ID": pid,
                    "PLAYER_NAME": f"Player {pid}",
                    "SHOT_CLOCK": float(clock),
                    "SHOT_ZONE_BASIC": zone,
                    "IS_3": 0,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def profiles():
    return creation_profiles(synthetic_shots(), min_attempts=50)


class TestProfiles:
    def test_rows_are_probability_distributions(self, profiles):
        cells = [c for c in profiles.columns if c[0] != "FGA"]
        sums = profiles[cells].sum(axis=1)
        assert np.allclose(sums, 1.0), "profile rows must sum to 1"

    def test_fga_is_not_a_distribution_cell(self, profiles):
        assert ("FGA", "") in profiles.columns
        assert ("FGA", "") not in profile_cells()

    def test_every_cell_present_and_non_zero(self, profiles):
        cells = [c for c in profiles.columns if c[0] != "FGA"]
        assert len(cells) == len(profile_cells())
        assert (profiles[cells] > 0).all().all(), "smoothing must keep cells non-zero"


class TestOverlap:
    def test_similarity_is_bounded(self, profiles):
        matrix = overlap_matrix(profiles)
        assert matrix.to_numpy().min() >= 0.0
        assert matrix.to_numpy().max() <= 1.0 + 1e-9

    def test_self_similarity_is_one(self, profiles):
        matrix = overlap_matrix(profiles)
        assert np.allclose(np.diag(matrix.to_numpy()), 1.0)

    def test_symmetric(self, profiles):
        matrix = overlap_matrix(profiles).to_numpy()
        assert np.allclose(matrix, matrix.T)

    def test_similar_players_score_higher_than_dissimilar(self, profiles):
        """Players 0 and 2 share a style; 0 and 1 were built to differ."""
        matrix = overlap_matrix(profiles)
        same_style = matrix.loc["Player 0", "Player 2"]
        cross_style = matrix.loc["Player 0", "Player 1"]
        assert same_style > cross_style

    def test_lineup_overlap_bounded(self, profiles):
        ids = profiles.index.get_level_values("PLAYER_ID").tolist()
        assert 0.0 <= lineup_overlap(profiles, ids[:4]) <= 1.0

    def test_lineup_overlap_needs_two_players(self, profiles):
        ids = profiles.index.get_level_values("PLAYER_ID").tolist()
        assert np.isnan(lineup_overlap(profiles, ids[:1]))
