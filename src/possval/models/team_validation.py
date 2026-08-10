"""Reproducible diagnostics for the preregistered team-profile validation sprint.

The helpers here are intentionally small and table-oriented.  The validation compares several
accounting specifications, and every comparison must join on team identity before computing a
rank correlation.  Comparing two independently sorted arrays was the source of a false negative
during development; :func:`aligned_rank_correlation` makes that error difficult to repeat.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from possval.models.team_profiles import add_basketball_context, score_against_team_curve
from possval.models.value import premature_share, team_curves


def team_accounting_profile(
    name: str,
    valued: pd.DataFrame,
    curves: pd.DataFrame,
) -> pd.DataFrame:
    """Team frequency and severity under one shot/continuation accounting choice."""
    scored = score_against_team_curve(valued, curves)
    grouped = scored.groupby("TEAM_ABBREVIATION")
    table = grouped.agg(
        N_ACTIONS=("BELOW", "size"),
        PREMATURE=("BELOW", "mean"),
        EXPOSURE_PER_ACTION=("EXPOSURE", "mean"),
        TOTAL_EXPOSURE=("EXPOSURE", "sum"),
        MEAN_ACTION_VALUE=("SHOT_VALUE", "mean"),
        MEAN_REFERENCE=("REFERENCE", "mean"),
    ).reset_index()
    table.insert(0, "SPECIFICATION", name)
    table["EXPOSURE_RANK"] = table.EXPOSURE_PER_ACTION.rank(
        ascending=False, method="min"
    ).astype(int)
    return table.sort_values("EXPOSURE_RANK")


def aligned_rank_correlation(
    left: pd.DataFrame,
    right: pd.DataFrame,
    metric: str,
) -> dict[str, float | int]:
    """Spearman correlation after an explicit one-to-one team join."""
    keys = ["TEAM_ABBREVIATION", metric]
    joined = left[keys].merge(
        right[keys],
        on="TEAM_ABBREVIATION",
        how="inner",
        suffixes=("_LEFT", "_RIGHT"),
        validate="one_to_one",
    ).dropna()
    rho, p_value = stats.spearmanr(joined[f"{metric}_LEFT"], joined[f"{metric}_RIGHT"])
    return {"N_TEAMS": len(joined), "SPEARMAN_RHO": float(rho), "P_VALUE": float(p_value)}


def accounting_comparisons(specifications: pd.DataFrame) -> pd.DataFrame:
    """Compare every accounting specification with the registered FG-only baseline."""
    names = specifications.SPECIFICATION.drop_duplicates().tolist()
    baseline_name = names[0]
    baseline = specifications[specifications.SPECIFICATION.eq(baseline_name)]
    rows = []
    for name in names:
        current = specifications[specifications.SPECIFICATION.eq(name)]
        for metric in ("PREMATURE", "EXPOSURE_PER_ACTION"):
            rows.append(
                {
                    "BASELINE": baseline_name,
                    "SPECIFICATION": name,
                    "METRIC": metric,
                    **aligned_rank_correlation(baseline, current, metric),
                }
            )
    return pd.DataFrame(rows)


def location_exposure_bounds(scored: pd.DataFrame) -> pd.DataFrame:
    """Bound shot-family exposure when foul-only actions have no public shot location.

    The lower bound assigns every location-missing action outside the family; the upper bound
    assigns all of its positive exposure to the family.  These are deliberately mechanical
    bounds rather than an imputation presented as observed location.
    """
    frame = add_basketball_context(scored)
    unknown = frame.SHOT_ZONE_BASIC.isna()
    total = float(frame.EXPOSURE.sum())
    unknown_exposure = float(frame.loc[unknown, "EXPOSURE"].sum())
    rows = []
    for family in ("rim", "paint (non-RA)", "mid-range", "three"):
        known = float(frame.loc[~unknown & frame.SHOT_FAMILY.eq(family), "EXPOSURE"].sum())
        rows.append(
            {
                "SHOT_FAMILY": family,
                "KNOWN_EXPOSURE": known,
                "UNKNOWN_LOCATION_EXPOSURE": unknown_exposure,
                "TOTAL_EXPOSURE": total,
                "SHARE_LOWER": known / total if total else np.nan,
                "SHARE_UPPER": (known + unknown_exposure) / total if total else np.nan,
            }
        )
    return pd.DataFrame(rows)


def foul_counts(fouls: pd.DataFrame, official_fga: pd.DataFrame) -> pd.DataFrame:
    """Shooting-foul exercise counts and rates by season, team, and clock phase."""
    foul = fouls.copy()
    foul["CLOCK_PHASE"] = pd.cut(
        foul.SHOT_CLOCK.round(),
        [-1, 7, 15, 24],
        labels=["late", "middle", "early"],
        include_lowest=True,
    )
    fga = official_fga.copy()
    fga["CLOCK_PHASE"] = pd.cut(
        fga.SHOT_CLOCK.round(),
        [-1, 7, 15, 24],
        labels=["late", "middle", "early"],
        include_lowest=True,
    )
    foul_group = foul.groupby(
        ["SEASON", "TEAM_ABBREVIATION", "CLOCK_PHASE"], observed=True
    ).agg(
        SHOOTING_FOULS=("AND_ONE", "size"),
        AND_ONES=("AND_ONE", "sum"),
        FOUL_ONLY=("AND_ONE", lambda value: int((~value).sum())),
    )
    fga_group = fga.groupby(
        ["SEASON", "TEAM_ABBREVIATION", "CLOCK_PHASE"], observed=True
    ).size().rename("OFFICIAL_FGA")
    table = foul_group.join(fga_group, how="outer").fillna(0).reset_index()
    for column in ("SHOOTING_FOULS", "AND_ONES", "FOUL_ONLY", "OFFICIAL_FGA"):
        table[column] = table[column].astype(int)
    table["FOUL_ONLY_ACTION_SHARE"] = table.FOUL_ONLY / (
        table.FOUL_ONLY + table.OFFICIAL_FGA
    ).replace(0, np.nan)
    return table


def temporal_team_game_null(
    valued: pd.DataFrame,
    train_chained: pd.DataFrame,
    n_draws: int = 50,
    seed: int = 0,
    min_possessions: int = 5_000,
    min_shots: int = 5_000,
) -> dict[str, float | int]:
    """Estimator-matched null for a frozen, one-season-ahead team profile.

    Whole team-games are relabelled on both the historical fitting side and the future scoring
    side. Curves are refit using only relabelled historical possessions, then applied to the
    relabelled future actions. Future outcomes therefore never enter a reference curve.
    """
    panel = train_chained.dropna(subset=["TEAM"])
    actions = valued.dropna(subset=["TEAM_ABBREVIATION"])
    panel_key = panel.GAME_ID.astype(str) + "|" + panel.TEAM.astype(str)
    action_key = actions.GAME_ID.astype(str) + "|" + actions.TEAM_ABBREVIATION.astype(str)
    codes, _ = pd.factorize(pd.concat([panel_key, action_key], ignore_index=True))
    panel_at, action_at = codes[: len(panel)], codes[len(panel) :]
    labels = (
        pd.concat([panel.TEAM, actions.TEAM_ABBREVIATION], ignore_index=True)
        .astype(str)
        .groupby(codes)
        .first()
        .to_numpy()
    )
    spreads = []
    for draw in range(n_draws):
        fake = np.random.default_rng(seed + draw).permutation(labels)
        curves = team_curves(
            panel,
            labels=fake[panel_at],
            min_possessions=min_possessions,
        )
        profile = premature_share(
            actions.assign(TEAM_ABBREVIATION=fake[action_at]),
            curves,
            min_shots=min_shots,
        )
        if len(profile) > 1:
            spreads.append(float(profile.PREMATURE.std(ddof=1)))
    if not spreads:
        raise ValueError("no temporal permutation draw produced enough teams")
    values = np.asarray(spreads)
    return {
        "null_mean": float(values.mean()),
        "null_sd": float(values.std(ddof=1)),
        "null_p95": float(np.percentile(values, 95)),
        "n_draws": len(values),
    }


def team_game_bootstrap(
    scored: pd.DataFrame,
    n_draws: int = 1_000,
    seed: int = 0,
) -> pd.DataFrame:
    """Team-game cluster intervals for frequency and positive exposure per action."""
    game = (
        scored.groupby(["TEAM_ABBREVIATION", "GAME_ID"])
        .agg(N=("BELOW", "size"), BELOW=("BELOW", "sum"), EXPOSURE=("EXPOSURE", "sum"))
        .reset_index()
    )
    rows = []
    for team, frame in game.groupby("TEAM_ABBREVIATION"):
        values = frame[["N", "BELOW", "EXPOSURE"]].to_numpy(dtype=float)
        rng = np.random.default_rng(seed)
        indices = rng.integers(0, len(values), size=(n_draws, len(values)))
        sampled = values[indices].sum(axis=1)
        premature = sampled[:, 1] / sampled[:, 0]
        exposure = sampled[:, 2] / sampled[:, 0]
        rows.append(
            {
                "TEAM_ABBREVIATION": team,
                "N_TEAM_GAMES": len(values),
                "PREMATURE": frame.BELOW.sum() / frame.N.sum(),
                "PREMATURE_LOW": np.quantile(premature, 0.025),
                "PREMATURE_HIGH": np.quantile(premature, 0.975),
                "EXPOSURE_PER_ACTION": frame.EXPOSURE.sum() / frame.N.sum(),
                "EXPOSURE_LOW": np.quantile(exposure, 0.025),
                "EXPOSURE_HIGH": np.quantile(exposure, 0.975),
            }
        )
    return pd.DataFrame(rows)
