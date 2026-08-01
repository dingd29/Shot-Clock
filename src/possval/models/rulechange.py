"""The 2018-19 shot-clock rule as a natural experiment.

From 2018-19 the clock resets to 14 rather than 24 after an offensive rebound. That gives a
difference-in-differences with an unusually clean structure, because the treatment is defined
by a rule rather than by anyone's choice:

    treated   chances starting with an **offensive** rebound  — reset cut from 24 to 14
    control   chances starting with a **defensive** rebound   — untouched by the rule

Both are live-ball rebound starts, so they share the era's pace, spacing and officiating
trends; only one had time taken away from it. Restricting the control to defensive rebounds
rather than "all other chances" matters: chances beginning after a made basket or a foul
carry dead-ball time that moves for unrelated reasons.

**Outcomes are measured from the raw feed, not from the reconstruction.** Chance duration
comes from game-clock differences and points from the play-by-play descriptions. This is
deliberate — the reconstruction *implements* the rule being tested, so using reconstructed
shot clocks as the outcome would recover the rule by construction and prove nothing. The
reconstruction is used only to say where one chance ends and the next begins, a judgment that
does not depend on the 14-second rule.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.paths import PROCESSED

RULE_SEASON = 2018
TREATED, CONTROL = "off_rebound", "def_rebound"
MAX_CHANCE_SECONDS = 24
SHORT_CLOCK = 14


def chance_table(first: int = 2015, last: int = 2024) -> pd.DataFrame:
    """One row per chance: how it started, how long it lasted, what it scored.

    A chance's duration is the gap between the *previous* chance's last event and its own —
    the play-by-play logs events, not clock starts, so the moment a chance begins is the
    moment the one before it ended. Measuring within a chance's own events instead gives a
    mean of 1.8 seconds, which is the interval between logged events and not a possession.
    """
    from possval.models.lineup_synergy import event_points

    frames = []
    for season in range(first, last + 1):
        path = PROCESSED / f"pbp_clock_{season}.parquet"
        if not path.exists():
            continue
        events = pd.read_parquet(
            path,
            columns=[
                "GAME_ID", "EVENTNUM", "EVENTMSGTYPE", "PERIOD", "CHANCE_ID",
                "CHANCE_START_TYPE", "GAME_CLOCK", "HOMEDESCRIPTION", "VISITORDESCRIPTION",
            ],
        ).sort_values(["GAME_ID", "EVENTNUM"])
        events["PTS"] = event_points(events)

        chances = (
            events.groupby(["GAME_ID", "PERIOD", "CHANCE_ID"], sort=True)
            .agg(
                START=("CHANCE_START_TYPE", "first"),
                PTS=("PTS", "sum"),
                END_GC=("GAME_CLOCK", "min"),
            )
            .reset_index()
            .sort_values(["GAME_ID", "PERIOD", "CHANCE_ID"])
        )
        chances["DURATION"] = (
            chances.groupby(["GAME_ID", "PERIOD"]).END_GC.shift() - chances.END_GC
        )
        # A period's first chance has no predecessor, and a non-positive or over-length gap
        # means the clock or the chance boundary is unreliable there.
        chances = chances[chances.DURATION.between(0, MAX_CHANCE_SECONDS, inclusive="right")]
        chances["SEASON"] = season
        frames.append(chances[["SEASON", "GAME_ID", "START", "PTS", "DURATION"]])

    table = pd.concat(frames, ignore_index=True)
    table = table[table.START.isin([TREATED, CONTROL])].copy()
    table["TREATED"] = (table.START == TREATED).astype(float)
    table["POST"] = (table.SEASON >= RULE_SEASON).astype(float)
    # The rule can only bind on a chance that would otherwise have run past 14 seconds;
    # everything shorter was never constrained, which is why the mean moves so little.
    table["RAN_LONG"] = (table.DURATION > SHORT_CLOCK).astype(float)
    return table


def _cluster_ols(x: np.ndarray, y: np.ndarray, clusters: np.ndarray, names: list[str]) -> dict:
    """OLS with standard errors clustered on `clusters`.

    Clustering is on season. There are only ten, so the interval is wide and honest rather
    than the implausibly tight one a million-chance sample would otherwise produce — the
    variation being used is between seasons, and there are ten of those, not a million.
    """
    coefficients, *_ = np.linalg.lstsq(x, y, rcond=None)
    residual = y - x @ coefficients
    bread = np.linalg.pinv(x.T @ x)

    meat = np.zeros((x.shape[1], x.shape[1]))
    unique = np.unique(clusters)
    for cluster in unique:
        rows = clusters == cluster
        score = x[rows].T @ residual[rows]
        meat += np.outer(score, score)
    scale = len(unique) / max(len(unique) - 1, 1)
    covariance = scale * bread @ meat @ bread
    errors = np.sqrt(np.clip(np.diag(covariance), 0, None))

    return {
        name: {"estimate": float(c), "std_error": float(e), "t": float(c / e) if e else np.nan}
        for name, c, e in zip(names, coefficients, errors, strict=True)
    }


def difference_in_differences(table: pd.DataFrame, outcome: str) -> dict:
    """The DiD estimate for one outcome, with season-clustered standard errors."""
    design = np.column_stack(
        [
            np.ones(len(table)),
            table.TREATED.to_numpy(),
            table.POST.to_numpy(),
            (table.TREATED * table.POST).to_numpy(),
        ]
    )
    return _cluster_ols(
        design,
        table[outcome].to_numpy(dtype=float),
        table.SEASON.to_numpy(),
        ["intercept", "treated", "post", "did"],
    )["did"]


def event_study(table: pd.DataFrame, outcome: str, base_season: int = 2017) -> pd.DataFrame:
    """Treated-minus-control gap by season, relative to the season before the rule.

    This is the check that decides whether the DiD is believable. A jump at 2018-19 with a
    flat run-up is the rule; a gap already drifting beforehand would mean the two groups were
    diverging for their own reasons and the design is invalid.
    """
    means = table.groupby(["SEASON", "START"])[outcome].mean().unstack()
    gap = means[TREATED] - means[CONTROL]
    return pd.DataFrame(
        {
            "SEASON": gap.index,
            "treated_mean": means[TREATED].to_numpy(),
            "control_mean": means[CONTROL].to_numpy(),
            "gap": gap.to_numpy(),
            "relative_to_base": (gap - gap.loc[base_season]).to_numpy(),
        }
    ).reset_index(drop=True)


def base_sensitivity(table: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """The same gap-change, measured against each possible pre-period baseline.

    Worth doing because 2017-18 is an odd year: the treated-minus-control gap narrows there
    and then returns, in both duration and the long-chance share. An event study anchored on
    it therefore flatters the estimate, and one anchored on 2015-16 shrinks it. Reporting the
    range says which conclusions survive the choice and which do not.
    """
    means = table.groupby(["SEASON", "START"])[outcome].mean().unstack()
    gap = means[TREATED] - means[CONTROL]
    post = gap[gap.index >= RULE_SEASON].mean()

    rows = []
    for label, seasons in {
        "vs 2017-18 only": [RULE_SEASON - 1],
        "vs 2015-16 and 2016-17": [RULE_SEASON - 3, RULE_SEASON - 2],
        "vs all three pre-seasons": list(range(RULE_SEASON - 3, RULE_SEASON)),
    }.items():
        rows.append({"baseline": label, "change": float(post - gap.loc[seasons].mean())})
    return pd.DataFrame(rows)


def report(first: int = 2015, last: int = 2024) -> dict:
    """Run the whole experiment: DiD on three outcomes, plus the event study for each."""
    table = chance_table(first, last)
    outcomes = {
        "RAN_LONG": "P(chance lasts past 14s)",
        "DURATION": "chance duration (seconds)",
        "PTS": "points per chance",
    }
    estimates = pd.DataFrame(
        [
            {"outcome": label, **difference_in_differences(table, column)}
            for column, label in outcomes.items()
        ]
    )
    sensitivity = pd.concat(
        [
            base_sensitivity(table, column).assign(outcome=label)
            for column, label in outcomes.items()
        ]
    )
    return {
        "n_chances": len(table),
        "n_treated": int(table.TREATED.sum()),
        "estimates": estimates,
        "baseline_sensitivity": sensitivity.pivot(
            index="outcome", columns="baseline", values="change"
        ),
        "event_studies": {c: event_study(table, c) for c in outcomes},
    }
