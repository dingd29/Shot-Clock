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

# 2017-18 is dropped from the design, and the reason is a property of the feed rather than a
# convenience. The NBA changed how it timestamps play-by-play that season: the share of events
# immediately following a rebound that carry the *identical* game clock as the rebound jumps
# from 14.8% (2015-16, 2016-17) to 18.7%, and stays near 18.5% every season after. Because
# duration here is measured from game-clock differences, and because the change lands
# specifically on events after rebounds — which is exactly how a treated chance begins — that
# season measures shorter chances for reasons that have nothing to do with the rule.
#
# It is also the only season carrying the new timestamping *and* the old 24-second reset,
# which is why it showed up as an outlier three separate ways: an anomalous DiD baseline, a
# 3.1% pile-up of shots at exactly 24 seconds against ~0.5% elsewhere, and a 14-second
# fingerprint appearing a year early. Including it inflates the standard error on the
# long-chance effect more than fourfold.
CONTAMINATED_SEASONS = (2017,)


def timestamp_granularity(first: int = 2015, last: int = 2024) -> pd.DataFrame:
    """Share of events sharing their predecessor's game clock, per season.

    A feed-quality measure, not a basketball one, and the diagnostic that identified the
    2017-18 problem. Reported alongside the experiment because a design resting on
    game-clock differences is only as good as the timestamps underneath it.
    """
    rows = []
    for season in range(first, last + 1):
        path = PROCESSED / f"pbp_clock_{season}.parquet"
        if not path.exists():
            continue
        events = pd.read_parquet(
            path, columns=["GAME_ID", "EVENTNUM", "EVENTMSGTYPE", "PERIOD", "GAME_CLOCK"]
        ).sort_values(["GAME_ID", "EVENTNUM"])

        same_game = (events.GAME_ID == events.GAME_ID.shift()) & (
            events.PERIOD == events.PERIOD.shift()
        )
        identical = (events.GAME_CLOCK.diff() == 0) & same_game
        after_rebound = (events.EVENTMSGTYPE.shift() == 4) & same_game
        rows.append(
            {
                "SEASON": season,
                "identical_clock_pct": 100 * identical.mean(),
                "after_rebound_identical_pct": 100
                * (identical & after_rebound).sum()
                / max(after_rebound.sum(), 1),
            }
        )
    return pd.DataFrame(rows).set_index("SEASON")


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


def event_study(
    table: pd.DataFrame, outcome: str, base_season: int | None = None
) -> pd.DataFrame:
    """Treated-minus-control gap by season, relative to the last clean pre-rule season.

    This is the check that decides whether the DiD is believable. A jump at 2018-19 with a
    flat run-up is the rule; a gap already drifting beforehand would mean the two groups were
    diverging for their own reasons and the design is invalid.

    The base defaults to the newest pre-rule season still in the table, which is 2016-17 once
    2017-18 is dropped — anchoring on a contaminated season is exactly how its measurement
    artifact would be laundered into the estimate.
    """
    means = table.groupby(["SEASON", "START"])[outcome].mean().unstack()
    gap = means[TREATED] - means[CONTROL]
    if base_season is None:
        base_season = max(s for s in gap.index if s < RULE_SEASON)
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
    choices = {
        "vs 2015-16 and 2016-17": [RULE_SEASON - 3, RULE_SEASON - 2],
        "vs 2017-18 only": [RULE_SEASON - 1],
        "vs all three pre-seasons": list(range(RULE_SEASON - 3, RULE_SEASON)),
    }
    for label, seasons in choices.items():
        present = [s for s in seasons if s in gap.index]
        if not present:
            continue
        rows.append({"baseline": label, "change": float(post - gap.loc[present].mean())})
    return pd.DataFrame(rows)


def report(
    first: int = 2015, last: int = 2024, drop_contaminated: bool = True
) -> dict:
    """Run the whole experiment: DiD on three outcomes, plus the event study for each.

    `drop_contaminated` removes 2017-18 — see `CONTAMINATED_SEASONS`. Both versions are
    returned so the decision is visible rather than buried in a default.
    """
    full = chance_table(first, last)
    table = full[~full.SEASON.isin(CONTAMINATED_SEASONS)] if drop_contaminated else full
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
    with_contaminated = pd.DataFrame(
        [
            {"outcome": label, **difference_in_differences(full, column)}
            for column, label in outcomes.items()
        ]
    )
    return {
        "n_chances": len(table),
        "n_treated": int(table.TREATED.sum()),
        "dropped_seasons": list(CONTAMINATED_SEASONS) if drop_contaminated else [],
        "estimates_including_2017": with_contaminated,
        "timestamp_granularity": timestamp_granularity(first, last),
        "estimates": estimates,
        "baseline_sensitivity": sensitivity.pivot(
            index="outcome", columns="baseline", values="change"
        ),
        "event_studies": {c: event_study(table, c) for c in outcomes},
    }
