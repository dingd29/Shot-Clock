"""The possession valuation curve, assembled from the pieces built separately.

`stopping.py` produced a continuation value over the shot clock. `rebound.py` showed it was
built on the wrong unit — chances rather than possessions — and that a shot's value has to
include the second chance a miss can generate. `endgame.py` added what happens when the period
clock, rather than the shot clock, is the binding constraint.

This puts them in one place and validates the result, which none of the pieces did on their own:

    V(t, start type)   expected points for the remainder of the possession, given `t` seconds of
                       shot clock left and how the possession began
    shot value         XPTS + P(retain | shot) * V(second chance)
    boundary           the shot value an offense will accept at `t`

**`V_ball(S)` from `endgame.py` is deliberately not folded in.** It is net points including what
the opponent scores, so merging it here would mix offence with defence in a single number. It
composes on top of this curve rather than into it.

The curve is fitted on training seasons and scored on held-out ones. A valuation nobody has
checked out of sample is a description of the past.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.models.rebound import (
    attach_retention,
    possession_panel,
    retention_lookup,
)

FULL_CLOCK = 24
SECONDS = np.arange(0, FULL_CLOCK + 1)

# Below this a cell's mean is over too little to mean anything. Matches `stopping`.
MIN_CHANCES = 200

# Start types are pooled into the ones that behave differently and have the volume to support a
# separate curve. `off_rebound` is its own group because the rule gives it a different clock and
# because a scrambled defence is measurably worth about 0.06 points; the live-ball turnover group
# is separate because it is the transition case; everything else is a half-court start.
START_GROUPS = {
    "off_rebound": "second_chance",
    "after_turnover": "live_ball",
    "after_made_fg": "half_court",
    "def_rebound": "half_court",
    "after_made_ft": "half_court",
    "after_def_foul": "half_court",
    "after_off_foul": "half_court",
    "period_start": "half_court",
    "jump_ball": "half_court",
    "after_kicked_ball": "half_court",
}
DEFAULT_GROUP = "half_court"


def start_group(start_type: pd.Series) -> pd.Series:
    return start_type.map(START_GROUPS).fillna(DEFAULT_GROUP)


def possession_curve(
    panel: pd.DataFrame,
    min_chances: int = MIN_CHANCES,
    by_start: bool = True,
    drop_period_expiry: bool = True,
    points_column: str = "PTS_FG",
) -> pd.DataFrame:
    """`V(t)`: expected points from declining to shoot with `t` seconds of shot clock left.

    Possession-level throughout: the outcome is points from this chance to the end of the
    *possession*, so a team that misses, rebounds its own shot and scores is credited here
    rather than having those points land on a different row. That is the correction from
    `rebound.py`, and it lowers the value drop across the clock from 0.448 to 0.384.

    A chance is live at `t` if it began at or above `t` and ended at or below it. The ones that
    did not end at `t` are those where the offence declined and played on, so their mean outcome
    is what continuing was worth.
    """
    chained = possession_panel(panel, points_column=points_column)
    if drop_period_expiry and "PERIOD_EXPIRED" in chained.columns:
        chained = chained[~chained.PERIOD_EXPIRED]
    chained = chained.assign(GROUP=start_group(chained.START_TYPE))

    groups = ["GROUP"] if by_start else []
    rows = []
    for key, frame in (chained.groupby(groups) if groups else [((), chained)]):
        start = frame.START_SC.to_numpy()
        end = frame.END_SC.to_numpy()
        points = frame.PTS_POSS.to_numpy(dtype=float)
        for second in SECONDS:
            live = (start >= second) & (end <= second)
            continued = live & (end < second)
            if continued.sum() < min_chances:
                continue
            row = {
                "SECOND": int(second),
                "V": float(points[continued].mean()),
                "SD": float(points[continued].std(ddof=1)),
                "N": int(continued.sum()),
            }
            if groups:
                row["GROUP"] = key[0] if isinstance(key, tuple) else key
            rows.append(row)
    table = pd.DataFrame(rows)
    table["SE"] = table.SD / np.sqrt(table.N)
    return table


def calibration(
    train: pd.DataFrame,
    test: pd.DataFrame,
    min_chances: int = MIN_CHANCES,
    points_column: str = "PTS_FG",
) -> pd.DataFrame:
    """Fit the curve on one set of seasons, score it on another.

    For every held-out chance that was live at `t` and continued, the curve predicts `V(t)`.
    The check is whether those predictions match what actually happened. A valuation that has
    only ever been evaluated on the data that produced it is a description, not a model.
    """
    fitted = possession_curve(
        train,
        min_chances=min_chances,
        points_column=points_column,
    ).set_index(["GROUP", "SECOND"]).V

    chained = possession_panel(test, points_column=points_column)
    if "PERIOD_EXPIRED" in chained.columns:
        chained = chained[~chained.PERIOD_EXPIRED]
    chained = chained.assign(GROUP=start_group(chained.START_TYPE))

    rows = []
    for group, frame in chained.groupby("GROUP"):
        start = frame.START_SC.to_numpy()
        end = frame.END_SC.to_numpy()
        points = frame.PTS_POSS.to_numpy(dtype=float)
        for second in SECONDS:
            continued = (start >= second) & (end < second)
            if continued.sum() < min_chances or (group, int(second)) not in fitted.index:
                continue
            realised = points[continued]
            rows.append(
                {
                    "GROUP": group,
                    "SECOND": int(second),
                    "N": int(continued.sum()),
                    "PREDICTED": float(fitted.loc[(group, int(second))]),
                    "REALISED": float(realised.mean()),
                    "SE": float(realised.std(ddof=1) / np.sqrt(len(realised))),
                }
            )
    table = pd.DataFrame(rows)
    table["ERROR"] = table.REALISED - table.PREDICTED
    return table


def calibration_summary(table: pd.DataFrame, level_shift: bool = False) -> dict:
    """Weighted error of the held-out predictions, and whether it is worse than noise.

    `level_shift` removes a single league-wide constant before scoring. That one parameter is
    the difference between two questions, and only the second is answerable from history:

    - *Does the curve's level transfer across eras?* No, and it should not be expected to. The
      league scores more in 2022-24 than in 2015-21 for reasons that have nothing to do with
      the shot clock — pace, three-point rate, rule changes on freedom of movement.
    - *Does the curve's shape transfer?* This is the part a decision rule actually uses, since
      shooting or holding turns on how value changes across the clock, not on its level.

    Reported both ways so the distinction is visible rather than assumed.
    """
    weights = table.N.to_numpy(dtype=float)
    error = table.ERROR.to_numpy()
    shift = float(np.average(error, weights=weights)) if level_shift else 0.0
    adjusted = error - shift
    chi_square = float(np.sum((adjusted / table.SE.to_numpy()) ** 2))
    dof = len(table) - (1 if level_shift else 0)
    return {
        "n_cells": len(table),
        "n_chances": int(table.N.sum()),
        "level_shift": shift,
        "mean_abs_error": float(np.average(np.abs(adjusted), weights=weights)),
        "bias": float(np.average(adjusted, weights=weights)),
        "chi_square": chi_square,
        "dof": dof,
        # A curve that merely reproduced the training seasons would have error far above the
        # sampling noise of the held-out cells; near 1 means it is as good as the data allows.
        "chi_square_per_dof": chi_square / max(dof, 1),
    }


def shot_value(
    shots: pd.DataFrame, outcomes: pd.DataFrame, second_chance: float
) -> pd.DataFrame:
    """A shot's full value: its own expected points plus the rebound option it carries.

    `XPTS` alone understates a shot, and understates it unevenly — retention runs 23.2% at 0-3
    seconds on the shot clock against about 14% mid-clock, so the omission is largest exactly
    where the shoot-or-hold decision binds.
    """
    lookup = retention_lookup(outcomes)
    frame = shots.copy()
    if "CLOCK_BAND" not in frame:
        from possval.models.rebound import _band

        frame["CLOCK_BAND"] = _band(frame.SHOT_CLOCK)
    frame["RETAIN"] = attach_retention(frame, lookup)
    frame["SHOT_VALUE"] = frame.XPTS + frame.RETAIN * second_chance
    frame["SECOND"] = frame.SHOT_CLOCK.round().clip(0, FULL_CLOCK).astype(int)
    return frame


# Shots landing exactly on the reset are tips and putbacks arriving with the clock at maximum;
# they are not decisions and are excluded from every boundary comparison.
RESET_INSTANT = FULL_CLOCK


def boundary(
    valued: pd.DataFrame,
    curve: pd.DataFrame,
    quantile: float = 0.05,
    min_shots: int = 200,
) -> pd.DataFrame:
    """The shot value an offence accepts at `t`, against what continuing was worth.

    The curve is pooled across start groups here because a shot carries no start type of its
    own in the scored table; the group-conditioned curve is used for valuation, not for the
    boundary.
    """
    pooled = curve.groupby("SECOND").apply(
        lambda g: np.average(g.V, weights=g.N), include_groups=False
    ).rename("V")
    scored = valued[valued.SECOND != RESET_INSTANT]
    accepted = scored.groupby("SECOND").SHOT_VALUE.agg(
        BOUNDARY=lambda x: float(x.quantile(quantile)), N_SHOTS="size"
    )
    joined = accepted.join(pooled, how="inner")
    joined = joined[joined.N_SHOTS >= min_shots]
    joined["GAP"] = joined.BOUNDARY - joined.V
    return joined.reset_index()


# ---------------------------------------------------------------------------------------
# Teams: three different questions that are easy to confuse
# ---------------------------------------------------------------------------------------
#
#   1. Where on the curve does a team sit?      -> shot timing. Style.
#   2. Is the team's curve itself different?    -> V_team(t). Capability.
#   3. Is the team above or below its own curve? -> premature share. Decision quality.
#
# Only the third is a claim that anybody is doing anything wrong. A team whose star takes the
# first available look sits at a different point on the curve, and if that star is good the
# curve is different too — neither is a mistake. Previous attempts here measured only a version
# of (3), found nothing, and that was read as "teams do not differ", which does not follow.

MIN_TEAM_SHOTS = 5_000


def team_shot_timing(valued: pd.DataFrame, min_shots: int = MIN_TEAM_SHOTS) -> pd.DataFrame:
    """Where teams sit on the clock. Pure description of style, no claim about quality."""
    frame = valued.dropna(subset=["TEAM_ABBREVIATION", "SECOND"])
    frame = frame[frame.SECOND != RESET_INSTANT]
    grouped = frame.groupby("TEAM_ABBREVIATION")
    table = pd.DataFrame(
        {
            "N_SHOTS": grouped.size(),
            "MEAN_SECOND": grouped.SECOND.mean(),
            "EARLY_SHARE": grouped.SECOND.apply(lambda s: float((s >= 18).mean())),
            "LATE_SHARE": grouped.SECOND.apply(lambda s: float((s <= 7).mean())),
        }
    )
    return table[table.N_SHOTS >= min_shots].reset_index().sort_values("MEAN_SECOND")


def _curve_array(start, end, points, min_chances):
    """`V(t)` as a plain array, for use inside permutation loops."""
    values = np.full(FULL_CLOCK + 1, np.nan)
    for second in SECONDS:
        continued = (start >= second) & (end < second)
        count = continued.sum()
        if count >= min_chances:
            values[second] = points[continued].mean()
    return values


def team_curves(
    chained: pd.DataFrame,
    labels: np.ndarray | None = None,
    min_chances: int = 200,
    min_possessions: int = 20_000,
) -> pd.DataFrame:
    """`V_team(t)` for every team, from a pre-chained possession panel.

    Takes the chained panel rather than the raw one so a permutation loop does not re-chain
    2.8M rows on every draw.
    """
    team = chained.TEAM.to_numpy() if labels is None else labels
    start = chained.START_SC.to_numpy()
    end = chained.END_SC.to_numpy()
    points = chained.PTS_POSS.to_numpy(dtype=float)

    rows = []
    for name in pd.unique(team[pd.notna(team)]):
        mask = team == name
        if mask.sum() < min_possessions:
            continue
        values = _curve_array(start[mask], end[mask], points[mask], min_chances)
        rows.append({"TEAM": name, "N": int(mask.sum()), **{f"V{t}": values[t] for t in SECONDS}})
    return pd.DataFrame(rows)


def curve_shape(
    curves: pd.DataFrame, seconds: tuple[int, ...] = (2, 6, 10, 14, 18, 22)
) -> pd.DataFrame:
    """Each team's curve, re-centred on its own mean so only *shape* is compared.

    A team of better shooters has a higher curve everywhere. That is capability, not style, and
    it would otherwise dominate any dispersion measure. Subtracting each team's own level leaves
    how steeply its value decays — which is the thing a shoot-or-hold decision actually turns on.
    """
    columns = [f"V{t}" for t in seconds]
    frame = curves[["TEAM", *columns]].dropna()
    centred = frame[columns].sub(frame[columns].mean(axis=1), axis=0)
    centred.insert(0, "TEAM", frame.TEAM.to_numpy())
    return centred


def premature_share(
    valued: pd.DataFrame,
    curves: pd.DataFrame | None,
    pooled_curve: pd.Series | None = None,
    min_shots: int = MIN_TEAM_SHOTS,
) -> pd.DataFrame:
    """Share of a team's shots taken below the continuation value they gave up.

    **A proportion, deliberately.** The relaxation ratio is a quotient of two fitted slopes
    estimated on a thirtieth of the data, and it was too noisy to resolve team differences at
    all: `preregistration_situational.md` H4 returned a signal share of zero out of sample. A
    proportion over ~350,000 shots per team has a standard error near 0.0004, which is three
    orders of magnitude better conditioned.

    Pass `curves` to score each team against **its own** curve, which asks whether it decides
    well given its own capability. Pass `pooled_curve` to score everyone against the league,
    which mixes capability back in.
    """
    frame = valued.dropna(subset=["TEAM_ABBREVIATION", "SHOT_VALUE", "SECOND"])
    frame = frame[frame.SECOND != RESET_INSTANT]

    if curves is not None:
        # Fancy-indexed rather than looked up row by row: this runs inside a permutation loop
        # over 1.3M shots, where a Python-level lookup costs minutes per draw.
        order = curves.TEAM.to_numpy()
        grid = curves[[f"V{t}" for t in SECONDS]].to_numpy(dtype=float)
        position = pd.Index(order).get_indexer(frame.TEAM_ABBREVIATION.to_numpy())
        seconds = frame.SECOND.to_numpy()
        reference = np.where(
            position >= 0, grid[np.clip(position, 0, None), seconds], np.nan
        )
    else:
        reference = frame.SECOND.map(pooled_curve).to_numpy(dtype=float)

    frame = frame.assign(REFERENCE=reference).dropna(subset=["REFERENCE"])
    frame = frame.assign(BELOW=(frame.SHOT_VALUE < frame.REFERENCE))
    grouped = frame.groupby("TEAM_ABBREVIATION")
    table = pd.DataFrame({"N_SHOTS": grouped.size(), "PREMATURE": grouped.BELOW.mean()})
    table = table[table.N_SHOTS >= min_shots]
    table["SE"] = np.sqrt(table.PREMATURE * (1 - table.PREMATURE) / table.N_SHOTS)
    return table.reset_index().sort_values("PREMATURE")


def premature_null(
    valued: pd.DataFrame,
    chained: pd.DataFrame,
    n_draws: int = 50,
    seed: int = 0,
    **kwargs,
) -> dict:
    """Spread in premature share when team labels carry no information.

    Same construction as every other null here: relabel whole **team-games** with one shared
    mapping across both frames, so a fake team keeps a real team's clustering and its shots stay
    paired with its own possessions.
    """
    chained = chained.dropna(subset=["TEAM"])
    valued = valued.dropna(subset=["TEAM_ABBREVIATION"])

    panel_key = chained.GAME_ID.astype(str) + "|" + chained.TEAM.astype(str)
    shots_key = valued.GAME_ID.astype(str) + "|" + valued.TEAM_ABBREVIATION.astype(str)
    codes, _ = pd.factorize(pd.concat([panel_key, shots_key], ignore_index=True))
    panel_at, shots_at = codes[: len(chained)], codes[len(chained) :]
    teams = pd.concat(
        [chained.TEAM, valued.TEAM_ABBREVIATION], ignore_index=True
    ).astype(str)
    labels = teams.groupby(codes).first().to_numpy()

    spreads = []
    for draw in range(n_draws):
        rng = np.random.default_rng(seed + draw)
        fake = rng.permutation(labels)
        curves = team_curves(chained, labels=fake[panel_at], **kwargs)
        table = premature_share(
            valued.assign(TEAM_ABBREVIATION=fake[shots_at]), curves
        )
        if len(table) > 1:
            spreads.append(float(table.PREMATURE.std(ddof=1)))
    if not spreads:
        raise ValueError("no permutation draw produced enough teams")
    spreads = np.asarray(spreads)
    return {
        "null_mean": float(spreads.mean()),
        "null_sd": float(spreads.std(ddof=1)),
        "null_p95": float(np.percentile(spreads, 95)),
        "n_draws": len(spreads),
    }
