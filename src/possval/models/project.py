"""Roster -> team rating -> season projection.

Converts a set of players and projected minutes into a team rating, then hands it to the
simulator. DPM is an on-court impact estimate in points per 100 possessions, so a team's
rating is the minutes-weighted sum of its players' DPM:

    team_rating = sum_i (DPM_i * minutes_i) / 48

because the five on-court slots supply 240 player-minutes per 48-minute game.

**Calibration gap, stated plainly.** This mapping is theoretical, not fitted. Validating it
would require comparing DPM-implied ratings against observed team ratings in the same season,
and the DARKO snapshot available here (July 2026) reflects 2025-26 form while the game data
stops at 2024-25. Ingesting 2025-26 results via `nbastatsv3` would close the loop; until then
the level of any projection from this module carries more uncertainty than its interval
suggests, and it should be read as a relative ordering rather than an absolute forecast.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

GAME_MINUTES = 48.0
LINEUP_SIZE = 5
TEAM_MINUTES = GAME_MINUTES * LINEUP_SIZE


def allocate_minutes(depth_chart: list[str], starters: int = 5) -> pd.Series:
    """A plausible minutes distribution, normalised to 240 team-minutes.

    Deliberately simple: starters ~32, rotation ~22, deep bench ~12, then scaled to fit.
    A real projection would model minutes explicitly; this makes the assumption visible
    rather than burying it in a fitted parameter.
    """
    base = []
    for i in range(len(depth_chart)):
        if i < starters:
            base.append(32.0)
        elif i < starters + 4:
            base.append(20.0)
        else:
            base.append(10.0)
    minutes = pd.Series(base, index=depth_chart)
    return minutes / minutes.sum() * TEAM_MINUTES


def team_rating(
    dpm: pd.Series, minutes: pd.Series, o_dpm: pd.Series | None = None,
    d_dpm: pd.Series | None = None,
) -> dict:
    """Minutes-weighted team rating from player impact estimates."""
    shared = dpm.index.intersection(minutes.index)
    weights = minutes.loc[shared]
    rating = float((dpm.loc[shared] * weights).sum() / GAME_MINUTES)

    out = {"rating": rating, "minutes_covered": float(weights.sum()), "n_players": len(shared)}
    if o_dpm is not None:
        out["offense"] = float((o_dpm.loc[shared] * weights).sum() / GAME_MINUTES)
    if d_dpm is not None:
        out["defense"] = float((d_dpm.loc[shared] * weights).sum() / GAME_MINUTES)
    return out


def rating_uncertainty(
    dpm: pd.Series,
    minutes: pd.Series,
    dpm_se: float = 0.8,
    availability_sd: float = 0.15,
    n_draws: int = 20_000,
    seed: int = 0,
) -> np.ndarray:
    """Distribution of the team rating, propagating two sources of uncertainty.

    `dpm_se`          how wrong each player's impact estimate might be
    `availability_sd` how much each player's minutes might move (injury, rotation)

    Availability is the larger term for a team whose value concentrates in a few players,
    which is exactly the Philadelphia case.
    """
    rng = np.random.default_rng(seed)
    shared = dpm.index.intersection(minutes.index)
    values = dpm.loc[shared].to_numpy(dtype=float)
    base_minutes = minutes.loc[shared].to_numpy(dtype=float)

    impact = values + rng.normal(0.0, dpm_se, (n_draws, len(values)))
    available = base_minutes * np.clip(
        rng.normal(1.0, availability_sd, (n_draws, len(base_minutes))), 0.0, None
    )
    # Minutes lost by one player are absorbed by the rest, so renormalise to 240.
    available = available / available.sum(axis=1, keepdims=True) * TEAM_MINUTES
    return (impact * available).sum(axis=1) / GAME_MINUTES


def league_baseline(darko: pd.DataFrame, rotation_size: int) -> float:
    """The team rating this mapping assigns to an *average* team.

    A plus-minus metric must average zero over the minutes actually played, so a correct
    mapping puts the league-average team at 0. It does not, and the size of the error
    depends entirely on how many players are assumed to carry rotation minutes:

        300 players -> mean DPM +0.50 -> average team +2.49
        400 players -> mean DPM +0.04 -> average team +0.18

    DARKO carries no minutes column, so the rotation size cannot be read off the data and
    the baseline is genuinely ambiguous. Every projection must be reported net of an
    explicit choice here, and the spread between choices is part of the uncertainty rather
    than something to be averaged away.
    """
    rotation = darko.nlargest(rotation_size, "DPM")
    return float(rotation.DPM.mean() * LINEUP_SIZE)


def project_team(
    darko: pd.DataFrame, depth_chart: list[str], starters: int = 5, **kwargs
) -> dict:
    """End-to-end: named roster -> rating, components, and an uncertainty interval."""
    roster = darko[darko.PLAYER_NAME.isin(depth_chart)].drop_duplicates("PLAYER_NAME")
    found = roster.set_index("PLAYER_NAME")
    missing = [p for p in depth_chart if p not in found.index]

    present = [p for p in depth_chart if p in found.index]
    minutes = allocate_minutes(present, starters=starters)

    point = team_rating(
        found.DPM, minutes, o_dpm=found.O_DPM, d_dpm=found.D_DPM
    )
    draws = rating_uncertainty(found.DPM, minutes, **kwargs)

    baselines = {n: league_baseline(darko, n) for n in (300, 350, 400)}
    return {
        **point,
        "missing_players": missing,
        "p10": float(np.percentile(draws, 10)),
        "p50": float(np.percentile(draws, 50)),
        "p90": float(np.percentile(draws, 90)),
        "sd": float(draws.std()),
        "draws": draws,
        "minutes": minutes,
        # Raw rating minus the league-average team under each rotation-size assumption.
        # The spread across these is a real uncertainty in the *level*, not noise.
        "centered": {n: point["rating"] - b for n, b in baselines.items()},
        "baselines": baselines,
    }
