"""The 2018-19 shot-clock rule as a natural experiment.

From 2018-19 the clock resets to 14 rather than 24 after an offensive rebound, which gives a
difference-in-differences where treatment is assigned by rule rather than by choice. Treated:
chances starting with an offensive rebound. Control: chances starting with a defensive one.

Both are live-ball rebound starts, so they share the era's pace and officiating drift.
Restricting the control to defensive rebounds matters, since made-basket and foul starts carry
dead-ball time that moves for unrelated reasons.

Outcomes come from the raw feed, not the reconstruction: duration from game-clock differences,
points from descriptions. The reconstruction implements the rule being tested, so using its
clocks as the outcome would recover the rule by construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.paths import PROCESSED

RULE_SEASON = 2018
TREATED, CONTROL = "off_rebound", "def_rebound"
MAX_CHANCE_SECONDS = 24
SHORT_CLOCK = 14

# 2017-18 is dropped because the feed changed that season. Events immediately after a rebound
# carrying that rebound's exact game clock jump from 14.8% to 18.7% and stay there. Duration
# here is a game-clock difference and the change lands on the events that begin a treated
# chance, so that season measures shorter chances for non-basketball reasons. Including it
# inflates the long-chance standard error more than fourfold.
CONTAMINATED_SEASONS = (2017,)


def timestamp_granularity(first: int = 2015, last: int = 2024) -> pd.DataFrame:
    """Share of events sharing their predecessor's game clock, per season.

    A feed-quality measure, not a basketball one, and the diagnostic that identified the
    2017-18 problem. Reported alongside the experiment because a design resting on
    game-clock differences is only as good as the timestamps underneath it.

    Split by rebound type, because that is what decides whether the experiment survives. The
    after-rebound identical-clock share steps up in 2017-18 and never comes back down, so
    dropping that season makes the feed regime almost collinear with treatment. The
    difference-in-differences is then only safe if the shift hit both arms equally: offensive
    rebounds are the treated group and defensive rebounds the control, and a shift that
    landed harder on one of them would show up as a treatment effect.
    """
    rows = []
    for season in range(first, last + 1):
        path = PROCESSED / f"pbp_clock_{season}.parquet"
        if not path.exists():
            continue
        events = pd.read_parquet(
            path,
            columns=[
                "GAME_ID", "EVENTNUM", "EVENTMSGTYPE", "PERIOD", "GAME_CLOCK",
                "CHANCE_START_TYPE",
            ],
        ).sort_values(["GAME_ID", "EVENTNUM"])

        same_game = (events.GAME_ID == events.GAME_ID.shift()) & (
            events.PERIOD == events.PERIOD.shift()
        )
        identical = (events.GAME_CLOCK.diff() == 0) & same_game
        after_rebound = (events.EVENTMSGTYPE.shift() == 4) & same_game

        row = {
            "SEASON": season,
            "identical_clock_pct": 100 * identical.mean(),
            "after_rebound_identical_pct": 100
            * (identical & after_rebound).sum()
            / max(after_rebound.sum(), 1),
        }
        for arm, start_type in [("off", "off_rebound"), ("def", "def_rebound")]:
            in_arm = after_rebound & (events.CHANCE_START_TYPE == start_type)
            row[f"after_{arm}_rebound_identical_pct"] = (
                100 * (identical & in_arm).sum() / max(in_arm.sum(), 1)
            )
            row[f"n_{arm}_rebound"] = int(in_arm.sum())
        row["arm_gap_pp"] = (
            row["after_off_rebound_identical_pct"] - row["after_def_rebound_identical_pct"]
        )
        rows.append(row)
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


def _did_design(table: pd.DataFrame) -> np.ndarray:
    return np.column_stack(
        [
            np.ones(len(table)),
            table.TREATED.to_numpy(),
            table.POST.to_numpy(),
            (table.TREATED * table.POST).to_numpy(),
        ]
    )


def wild_cluster_bootstrap(table: pd.DataFrame, outcome: str, seed: int = 0) -> dict:
    """Wild cluster bootstrap-t p-value for the DiD coefficient.

    Nine season clusters is far too few for the asymptotic clustered standard error. The
    finite-sample correction applied there is only G/(G-1), and the resulting t is read
    against a normal when the reference distribution is closer to t with 8 degrees of freedom:
    the reported t = -2.52 clears 1.96 but only just clears the 2.31 that t(8) asks for.

    This is the standard fix (Cameron, Gelbach and Miller 2008): impose the null, then flip the
    sign of every residual within a whole cluster at a time and read the observed t against the
    distribution that generates.

    With Rademacher weights and G clusters there are only 2^G distinct sign vectors, so at this
    cluster count the whole reference distribution is **enumerated** rather than sampled. 512
    draws is not a small bootstrap here, it is all of them, and the p-value is exact rather than
    simulated. `seed` is unused when enumerating and is kept for the sampled branch.
    """
    design = _did_design(table)
    y = table[outcome].to_numpy(dtype=float)
    clusters = table.SEASON.to_numpy()
    unique = np.unique(clusters)
    names = ["intercept", "treated", "post", "did"]

    observed = _cluster_ols(design, y, clusters, names)["did"]
    observed_t = observed["t"]

    # Fit under H0: drop the interaction, so the residuals carry no treatment effect.
    restricted = design[:, :3]
    coefficients, *_ = np.linalg.lstsq(restricted, y, rcond=None)
    fitted = restricted @ coefficients
    residual = y - fitted

    masks = [clusters == cluster for cluster in unique]
    n_clusters = len(unique)
    exhaustive = n_clusters <= 12
    n_draws = 2**n_clusters if exhaustive else 9_999
    rng = np.random.default_rng(seed)

    stats = np.empty(n_draws)
    weights = np.ones(len(y))
    for draw in range(n_draws):
        if exhaustive:
            signs = [1.0 if (draw >> bit) & 1 else -1.0 for bit in range(n_clusters)]
        else:
            signs = rng.choice([-1.0, 1.0], n_clusters)
        for rows, sign in zip(masks, signs, strict=True):
            weights[rows] = sign
        star = fitted + residual * weights
        stats[draw] = _cluster_ols(design, star, clusters, names)["did"]["t"]

    return {
        "estimate": observed["estimate"],
        "t": observed_t,
        "p_wild": float(np.mean(np.abs(stats) >= abs(observed_t))),
        "n_clusters": n_clusters,
        "n_draws": n_draws,
        "exhaustive": exhaustive,
        "crit_95": float(np.quantile(np.abs(stats), 0.95)),
    }


def difference_in_differences(table: pd.DataFrame, outcome: str) -> dict:
    """The DiD estimate for one outcome, with season-clustered standard errors."""
    return _cluster_ols(
        _did_design(table),
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
    # Ordered deliberately: first stage, then behaviour, then the outcome anyone cares about.
    #
    # `RAN_LONG` is **not a result**. After 2018-19 an offensive rebound under 14 seconds
    # resets to exactly 14, so a treated chance essentially cannot run past 14s except through
    # the `max(remaining, 14)` case. Finding that the rule cut long chances confirms the rule
    # took effect and that the reset is implemented correctly — a manipulation check, and a
    # good one given the flat pre-trend and the sharp step, but it is close to mechanically
    # guaranteed by the treatment and must not be presented as a behavioural finding.
    outcomes = {
        "RAN_LONG": "first stage: P(chance lasts past 14s)",
        "DURATION": "reduced form: chance duration (seconds)",
        "PTS": "RESULT: points per chance",
    }
    estimates = pd.DataFrame(
        [
            {
                "outcome": label,
                **difference_in_differences(table, column),
                # Nine clusters is too few to read the asymptotic t against a normal.
                "p_wild": wild_cluster_bootstrap(table, column)["p_wild"],
            }
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


def treatment_label_agreement(season: int = 2024) -> dict:
    """Check treatment assignment against the feed's own rebound bookkeeping.

    Treatment here is "the chance began with an offensive rebound", and the reconstruction
    decides that by comparing the rebounding team to the team that took the last shot. Error in
    that labelling is measurement error *in treatment*, which attenuates the estimate toward
    zero — so it is worth bounding rather than assuming small.

    **What the classification does and does not touch.** It uses the feed's team ids and event
    ordering plus our own tracking of who shot last. It does not use the reconstructed shot
    clock, the 14-second rule, or anything downstream of them, so treatment cannot be
    contaminated by the outcome. (The repo's claim that "outcomes never touch the
    reconstruction" is about outcomes; this is the matching statement for treatment, and it is
    weaker — treatment does depend on the reconstruction's chance-boundary logic, just not on
    its clock arithmetic.)

    The independent label comes from the description text, which carries each player's running
    offensive and defensive rebound counters — `REBOUND (Off:1 Def:2)`. Whichever counter
    increments identifies the type, from the feed's bookkeeping rather than our inference.
    """
    columns = [
        "GAME_ID", "EVENTNUM", "EVENTMSGTYPE", "PLAYER1_ID",
        "CHANCE_ID", "CHANCE_START_TYPE", "HOMEDESCRIPTION", "VISITORDESCRIPTION",
    ]
    events = pd.read_parquet(
        PROCESSED / f"pbp_clock_{season}.parquet", columns=columns
    ).sort_values(["GAME_ID", "EVENTNUM"]).reset_index(drop=True)

    # A rebound row belongs to the chance it *ends*; the chance it *starts* is the next one.
    next_start = events.groupby("GAME_ID").CHANCE_START_TYPE.shift(-1)
    next_id = events.groupby("GAME_ID").CHANCE_ID.shift(-1)
    events["STARTS"] = np.where(next_id > events.CHANCE_ID, next_start, None)

    rebounds = events[events.EVENTMSGTYPE == 4].copy()
    text = rebounds.HOMEDESCRIPTION.fillna("") + " " + rebounds.VISITORDESCRIPTION.fillna("")
    counters = text.str.extract(r"Off:(\d+)\s+Def:(\d+)")
    rebounds["OFF"] = pd.to_numeric(counters[0])
    rebounds["DEF"] = pd.to_numeric(counters[1])
    rebounds = rebounds.dropna(subset=["OFF", "DEF"])

    by_player = rebounds.groupby(["GAME_ID", "PLAYER1_ID"])
    offensive, defensive = by_player.OFF.diff(), by_player.DEF.diff()
    # A player's first rebound of the game has no predecessor; the counters are the increment.
    offensive = offensive.fillna(rebounds.OFF)
    defensive = defensive.fillna(rebounds.DEF)
    rebounds["FEED"] = np.where(
        offensive == 1, TREATED, np.where(defensive == 1, CONTROL, None)
    )

    comparable = rebounds[
        rebounds.FEED.notna() & rebounds.STARTS.isin([TREATED, CONTROL])
    ]
    agreement = float((comparable.STARTS == comparable.FEED).mean())
    return {
        "n_compared": len(comparable),
        "agreement": agreement,
        "n_disagree": int((comparable.STARTS != comparable.FEED).sum()),
        "confusion": pd.crosstab(comparable.STARTS, comparable.FEED),
    }
