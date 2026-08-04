"""Shooting as an optimal-stopping problem.

The efficiency-versus-clock curve in `reports/findings.md` §2 is a **selected sample at every
point**. Possessions still alive at 5 seconds are the ones where nothing materialised earlier,
so the slope conflates two things that cannot be separated by conditioning: time pressure
degrading shot quality, and bad possessions being the ones that last. Controlling for how the
possession *started* does not help, because the selection happens *within* the chance.

This module changes the question. At every moment the offense holds a live decision — shoot
now at whatever is available, or decline and draw again from a distribution whose value decays
as the clock runs. That is American option exercise, and the useful question is not "how does
efficiency vary with the clock" but **"are teams exercising at the right threshold?"**

The reason this identifies something the curve cannot: it conditions on the **decision** (a
shot was taken at time t, with estimated value q) rather than on the **outcome**. Whether that
particular exercise beat its own continuation value is answerable without knowing why the
possession lasted as long as it did.

**What is identified, and what is not.**

Taken shots are observed with their model value, so *premature exercise* — shooting when
holding was worth more — is measurable. The converse is not: a shot passed up leaves no record
of what it would have been worth, so this cannot measure teams holding too long. Every number
here is therefore a **lower bound on total decision error**, and it is one-sided by
construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.paths import PROCESSED

FULL_CLOCK = 24
# The continuation value is estimated per whole second of shot clock. Finer bins buy nothing:
# the feed quantises the game clock to a second, so sub-second resolution is invented.
SECONDS = np.arange(0, FULL_CLOCK + 1)

# Chances with fewer than this many observations at a given second are not reported — the
# continuation value there is a mean over too little to mean anything.
MIN_CHANCES_PER_SECOND = 200

# A chance that ends because the *period* ran out is not a shot-clock decision, and it must be
# removed before the continuation value is fitted rather than after. Left in, it poisons V(t)
# exactly where the model is most sensitive: **33% of chances ending with 2 or fewer seconds on
# the shot clock are period expiries**, and they carry near-zero value for reasons that have
# nothing to do with the shot clock. This is the same exclusion applied to shots in
# `features/shots.EXPIRING_SECONDS`, applied here to the chance side.
EXPIRING_GAME_SECONDS = 3.0

# Games inside this margin are "competitive". Outside it, shot selection stops being about the
# shot clock — a team down 20 takes quick threes, a team up 20 runs clock — so an
# unconditional V(t) silently averages three different decision problems together.
COMPETITIVE_MARGIN = 10.0


def chance_panel(first: int = 2015, last: int = 2024) -> pd.DataFrame:
    """One row per chance: when it began, when it ended, and what it produced.

    **Deriving the start clock is the fiddly part.** A chance's opening moment is never itself
    a logged event — the first row belonging to a chance is already some seconds in — so the
    start value has to be recovered as

        start = (shot clock at the first event) + (game clock at the chance's start
                                                   − game clock at that first event)

    where the chance's start is the previous chance's final event. Within a chance the shot
    clock and game clock fall together, so this is exact up to the inbound delay. It recovers
    the rule values cleanly: median 24 after a defensive rebound, 14 after an offensive one,
    and 26 after a made basket — that last being 24 plus the calibrated 2-second inbound delay,
    which is why the result is clipped back to 24.
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
                "CHANCE_START_TYPE", "SHOT_CLOCK", "GAME_CLOCK", "SCOREMARGIN",
                "OFF_TEAM_ID", "PLAYER1_TEAM_ID", "PLAYER1_TEAM_ABBREVIATION",
                "HOMEDESCRIPTION", "VISITORDESCRIPTION",
            ],
        ).sort_values(["GAME_ID", "EVENTNUM"])
        events["PTS"] = event_points(events)
        # SCOREMARGIN is only written on scoring events, so it has to be carried forward
        # before it can describe the state a chance was played in.
        margin = events.SCOREMARGIN.replace("TIE", "0").astype("string").astype("Float64")
        events["MARGIN"] = margin.groupby(events.GAME_ID).ffill().fillna(0.0).astype(float)

        timed = events.dropna(subset=["SHOT_CLOCK"])
        keys = ["GAME_ID", "PERIOD", "CHANCE_ID"]
        grouped = timed.groupby(keys, sort=True)

        panel = grouped.agg(
            START_TYPE=("CHANCE_START_TYPE", "first"),
            FIRST_SC=("SHOT_CLOCK", "first"),
            FIRST_GC=("GAME_CLOCK", "first"),
            LAST_GC=("GAME_CLOCK", "last"),
            END_SC=("SHOT_CLOCK", "min"),
            MARGIN=("MARGIN", "first"),
            OFF_TEAM_ID=("OFF_TEAM_ID", "first"),
            FGA=("EVENTMSGTYPE", lambda s: int(s.isin([1, 2]).sum())),
        ).reset_index()

        # Points are summed over *all* events of the chance, including free throws, so the
        # continuation value knows that holding can end in a trip to the line.
        totals = events.groupby(keys).PTS.sum().rename("PTS_ALL")
        field_goals = (
            events[events.EVENTMSGTYPE == 1].groupby(keys).PTS.sum().rename("PTS_FG")
        )
        panel = panel.merge(totals, on=keys, how="left").merge(field_goals, on=keys, how="left")
        panel["PTS_FG"] = panel.PTS_FG.fillna(0.0)

        # Play-by-play carries team ids on chances but abbreviations only on player events,
        # so the mapping is recovered from the feed rather than hard-coded.
        abbreviations = (
            events[["PLAYER1_TEAM_ID", "PLAYER1_TEAM_ABBREVIATION"]]
            .dropna()
            .drop_duplicates("PLAYER1_TEAM_ID")
            .set_index("PLAYER1_TEAM_ID")
            .PLAYER1_TEAM_ABBREVIATION
        )
        panel["TEAM"] = panel.OFF_TEAM_ID.map(abbreviations)

        panel = panel.sort_values(keys)
        panel["PREV_GC"] = panel.groupby(["GAME_ID", "PERIOD"]).LAST_GC.shift()
        panel["START_SC"] = (
            panel.FIRST_SC + (panel.PREV_GC - panel.FIRST_GC)
        ).clip(upper=float(FULL_CLOCK))
        panel["SEASON"] = season
        frames.append(panel)

    out = pd.concat(frames, ignore_index=True)
    # A period's opening chance has no predecessor to date it from, and a start below its own
    # end is a clock the reconstruction could not order.
    ordered = out.START_SC.notna() & (out.START_SC >= out.END_SC)
    # `PERIOD_EXPIRED` is kept as a column rather than silently dropped so the exclusion can be
    # switched off and its effect measured.
    out["PERIOD_EXPIRED"] = out.LAST_GC < EXPIRING_GAME_SECONDS
    out["COMPETITIVE"] = out.MARGIN.abs() <= COMPETITIVE_MARGIN
    return out[ordered].reset_index(drop=True)


def continuation_value(
    panel: pd.DataFrame,
    outcome: str = "PTS_FG",
    by_start_type: bool = False,
    min_chances: int = MIN_CHANCES_PER_SECOND,
    drop_period_expiry: bool = True,
) -> pd.DataFrame:
    """`V(t)`: expected points from declining to shoot with `t` seconds left.

    A chance is *live* at `t` when it began at or above `t` and ended at or below it. Of those,
    the ones that did **not** end at `t` are exactly the chances where the offense declined and
    played on, so their mean outcome is the value of continuing.

    This is the continuation value under **observed** behaviour, not under an optimal policy,
    and that is the right benchmark for the question being asked. The comparison is marginal —
    *should this shot have been taken, given how this offense would otherwise have finished the
    possession?* — so the counterfactual wanted is the team's own actual continuation, not a
    hypothetical perfectly-played one.

    `outcome` defaults to field-goal points because that is the unit `XPTS` is in. `PTS_ALL`
    adds free throws; see `free_throw_bias`.
    """
    if "PERIOD_EXPIRED" in panel.columns and drop_period_expiry:
        panel = panel[~panel.PERIOD_EXPIRED]
    groups = ["START_TYPE"] if by_start_type else []
    rows = []
    for keys, frame in (panel.groupby(groups) if groups else [((), panel)]):
        start, end, points = (
            frame.START_SC.to_numpy(),
            frame.END_SC.to_numpy(),
            frame[outcome].to_numpy(dtype=float),
        )
        for second in SECONDS:
            live = (start >= second) & (end <= second)
            continued = live & (end < second)
            if continued.sum() < min_chances:
                continue
            row = {
                "SECOND": int(second),
                "V_CONT": float(points[continued].mean()),
                "N_CONTINUED": int(continued.sum()),
                "N_LIVE": int(live.sum()),
                "P_TERMINATE": float((live & (end == second)).sum() / max(live.sum(), 1)),
            }
            if groups:
                row["START_TYPE"] = keys[0] if isinstance(keys, tuple) else keys
            rows.append(row)
    return pd.DataFrame(rows)


def exercise_gap(
    shots: pd.DataFrame, values: pd.DataFrame, min_shots: int = 200
) -> pd.DataFrame:
    """Compare each taken shot's model value against the continuation value it gave up.

    A shot at `t` with expected value `q` is *premature* when `q < V(t)`: the offense exercised
    an option worth less than holding it. The share of such shots, and the points they cost,
    are the two numbers this produces.
    """
    lookup = values.set_index("SECOND").V_CONT
    scored = shots.dropna(subset=["XPTS", "SHOT_CLOCK"]).copy()
    scored["SECOND"] = scored.SHOT_CLOCK.round().clip(0, FULL_CLOCK).astype(int)
    scored["V_CONT"] = scored.SECOND.map(lookup)
    scored = scored.dropna(subset=["V_CONT"])
    scored["SURPLUS"] = scored.XPTS - scored.V_CONT

    grouped = scored.groupby("SECOND").agg(
        N_SHOTS=("XPTS", "size"),
        MEAN_XPTS=("XPTS", "mean"),
        V_CONT=("V_CONT", "first"),
        PREMATURE_SHARE=("SURPLUS", lambda s: float((s < 0).mean())),
        MEAN_SURPLUS=("SURPLUS", "mean"),
        COST_IF_PREMATURE=("SURPLUS", lambda s: float(-s[s < 0].mean()) if (s < 0).any() else 0.0),
    )
    return grouped[grouped.N_SHOTS >= min_shots].reset_index()


def free_throw_bias(panel: pd.DataFrame) -> pd.DataFrame:
    """How much the continuation value moves when free throws are counted.

    `XPTS` predicts field-goal points only, so the headline comparison runs on field-goal
    points on both sides. That understates continuation value, because declining to shoot also
    preserves the chance of drawing a foul — and it understates it in a *known direction*:
    a lower bar makes fewer shots look premature. The field-goal-only result is therefore
    conservative for the premature-exercise finding, which is why it is the one reported.
    """
    field_goals = continuation_value(panel, "PTS_FG").set_index("SECOND").V_CONT
    everything = continuation_value(panel, "PTS_ALL").set_index("SECOND").V_CONT
    return pd.DataFrame(
        {
            "SECOND": field_goals.index,
            "V_FG_ONLY": field_goals.to_numpy(),
            "V_WITH_FT": everything.reindex(field_goals.index).to_numpy(),
            "FT_UPLIFT": (everything.reindex(field_goals.index) - field_goals).to_numpy(),
        }
    )


# Shots landing on the reset instant itself are excluded from the boundary comparison. They
# are tips and putbacks that arrive with the clock at its maximum, already flagged as an edge
# case in the findings, and they behave nothing like a decision to shoot: their 5th-percentile
# value is 0.08 against a continuation value of 0.83.
RESET_INSTANT = FULL_CLOCK


def exercise_boundary(
    shots: pd.DataFrame,
    values: pd.DataFrame,
    quantile: float = 0.05,
    min_shots: int = 200,
) -> pd.DataFrame:
    """The implied shoot-or-hold boundary, against the optimal one.

    If offenses followed a threshold rule — shoot iff value at least `b(t)` — then every taken
    shot would sit above `b(t)`, and the bottom of the accepted distribution would estimate it.
    The 5th percentile is used rather than the minimum because the rule is plainly not sharp:
    about 5% of shots fall below continuation value, so a hard minimum would just track the
    worst decision of the season.

    Optimal exercise puts `b(t) = V(t)`. Positive `GAP` means offenses demanded **more** than
    continuing was worth — passing up shots they should have taken.

    **The unobservable half.** A declined shot leaves no record, so this cannot see whether a
    shot worth taking actually existed at that moment. A positive gap is consistent with
    excessive patience, and equally consistent with nothing better being on offer. The gap
    measures what teams *accepted*, not what they *refused*, and the difference matters most
    exactly where the gap is largest.
    """
    scored = shots.dropna(subset=["XPTS", "SHOT_CLOCK"]).copy()
    scored["SECOND"] = scored.SHOT_CLOCK.round().clip(0, FULL_CLOCK).astype(int)
    scored = scored[scored.SECOND != RESET_INSTANT]

    accepted = scored.groupby("SECOND").XPTS.agg(
        BOUNDARY=lambda x: float(x.quantile(quantile)), N_SHOTS="size"
    )
    joined = accepted.join(values.set_index("SECOND").V_CONT, how="inner")
    joined = joined[joined.N_SHOTS >= min_shots]
    joined["GAP"] = joined.BOUNDARY - joined.V_CONT
    return joined.reset_index()


# Where the clock is genuinely expiring versus where there is still time to work. The split
# is used only to summarise the boundary comparison; nothing is fitted to it.
LATE_SECONDS = (1, 3)
EARLY_SECONDS = (8, 23)


def relaxation(
    shots: pd.DataFrame,
    values: pd.DataFrame,
    quantiles: tuple[float, ...] = (0.02, 0.05, 0.10, 0.20, 0.25),
) -> pd.DataFrame:
    """Do offenses relax their standard as fast as continuation value collapses?

    **The level of the boundary is not identified, and this is the honest way around it.**
    Calling the 5th percentile of accepted shots "the threshold" rather than the 2nd or the
    20th moves the estimated gap from −0.22 to +0.14 — the sign of "too aggressive" versus
    "too patient" is a free parameter, so no claim rests on it.

    What survives the choice is the *shape*: how much offenses lower their standard between an
    early clock and an expiring one, against how much the continuation value falls over the
    same range. Optimal exercise requires the two to move together, since a threshold should
    track the value of the option it is being compared against. Both summaries below are
    computed at every quantile so the reader can see they do not depend on it.
    """
    rows = []
    for quantile in quantiles:
        boundary = exercise_boundary(shots, values, quantile=quantile).set_index("SECOND")
        late, early = LATE_SECONDS, EARLY_SECONDS
        boundary_drop = float(boundary.BOUNDARY[early[1]] - boundary.BOUNDARY[late[0]])
        value_drop = float(boundary.V_CONT[early[1]] - boundary.V_CONT[late[0]])
        rows.append(
            {
                "quantile": quantile,
                "boundary_drop": boundary_drop,
                "value_drop": value_drop,
                "relaxation_ratio": boundary_drop / value_drop,
                "excess_late_demand": float(
                    boundary.GAP.loc[late[0]:late[1]].mean()
                    - boundary.GAP.loc[early[0]:early[1]].mean()
                ),
            }
        )
    return pd.DataFrame(rows)


LATE_CLOCK = 7


def player_exercise(
    shots: pd.DataFrame, values: pd.DataFrame, min_late: int = 60
) -> pd.DataFrame:
    """Per-player exercise surplus on late-clock shots, shrunk toward the league.

    The obvious extension of the boundary result: if some players are genuinely better
    bail-out creators, holding the ball for *them* is worth more, and their optimal threshold
    should differ. That would show up as a real spread in how far their late shots sit above
    continuation value.

    It is also the extension most likely to be noise, which is why it is shrunk before it is
    read. A player with 60 late-clock attempts has a standard error near 0.14 points on this
    quantity, comparable to the entire league spread, so the raw leaderboard would rank
    small samples that happened to regress in one direction — the same trap the late-clock
    making leaderboard fell into (§7, where only 21.6% of raw spread was signal).

    `SIGNAL_SHARE` in the returned frame's `attrs` is the fraction of observed variance left
    after subtracting sampling noise. If it is near zero, players do not differ.

    **This measure does not work, and the arithmetic says why.** Per-player mean surplus
    correlates **0.984** with per-player mean late-clock `XPTS`, and the standard deviation of
    the difference between them is 0.012 against 0.067 for either on its own. Subtracting
    `V(t)` removes almost nothing at player level, because every player's late-clock shots are
    spread over roughly the same seconds, so `V` enters as a near-constant. Mean surplus is
    therefore *mean late-clock shot quality under a different name*.

    That is why the leaderboard grades shot type rather than judgment: rim-runners top it
    (correlation +0.59 with late-clock rim share), and restricting to non-rim shots merely
    swaps them for shooters — Merrill, Strus, Curry — with non-shooters at the bottom.
    Measuring judgment needs the counterfactual, what *else* was available at that moment, and
    a declined shot leaves no record. Kept because the negative is informative and the
    temptation to publish this as a skill ranking is real.
    """
    lookup = values.set_index("SECOND").V_CONT
    late = shots.dropna(subset=["XPTS", "SHOT_CLOCK"]).copy()
    late["SECOND"] = late.SHOT_CLOCK.round().clip(0, FULL_CLOCK).astype(int)
    late = late[(late.SECOND <= LATE_CLOCK) & (late.SECOND != RESET_INSTANT)]
    late["V_CONT"] = late.SECOND.map(lookup)
    late = late.dropna(subset=["V_CONT"])
    late["SURPLUS"] = late.XPTS - late.V_CONT

    grouped = (
        late.groupby(["PLAYER_ID", "PLAYER_NAME"], observed=True)
        .agg(FGA_LATE=("SURPLUS", "size"), SURPLUS=("SURPLUS", "mean"))
        .reset_index()
    )
    grouped = grouped[grouped.FGA_LATE >= min_late]

    # The per-shot noise scale is measured, not assumed. `SURPLUS` is built from a model
    # prediction rather than a realised 0/2/3 outcome, so its shot-to-shot spread is the
    # spread of `XPTS` (~0.3), not the ~1.1 of actual points. Using the outcome figure here —
    # which is correct for the *making* leaderboard in §7 and wrong for this *selection*
    # quantity — inflates the assumed noise more than threefold and drives the signal share to
    # exactly zero by construction.
    per_shot_sd = float(late.groupby("PLAYER_ID").SURPLUS.std().mean())
    grouped["SE"] = per_shot_sd / np.sqrt(grouped.FGA_LATE)
    observed = grouped.SURPLUS.var()
    noise = (grouped.SE**2).mean()
    signal = max(observed - noise, 0.0)

    league = grouped.SURPLUS.mean()
    grouped["SHRUNK_SURPLUS"] = league + (grouped.SURPLUS - league) * (
        signal / (signal + grouped.SE**2)
    )
    result = grouped.sort_values("SHRUNK_SURPLUS", ascending=False).reset_index(drop=True)
    result.attrs["signal_share"] = float(signal / observed) if observed else 0.0
    result.attrs["league_mean"] = float(league)
    result.attrs["per_shot_sd"] = per_shot_sd
    return result


def robustness(shots: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """The relaxation result under the cuts a sceptical reader asks for.

    Two questions the pooled number cannot answer. Is it garbage time — an unconditional
    `V(t)` has blowouts and late-game fouling folded in, and those are different decision
    problems. And is it one season's quirk, or does it hold across the sample the way the
    efficiency curves do in finding 4c.
    """
    rows = []
    for label, chances, taken in [
        ("all games", panel, shots),
        ("competitive (|margin| <= 10)", panel[panel.COMPETITIVE],
         shots[shots.SCORE_MARGIN.abs() <= COMPETITIVE_MARGIN]),
        ("blowouts (|margin| > 10)", panel[~panel.COMPETITIVE],
         shots[shots.SCORE_MARGIN.abs() > COMPETITIVE_MARGIN]),
    ]:
        ratios = relaxation(taken, continuation_value(chances))
        rows.append(
            {
                "cut": label,
                "n_chances": len(chances),
                "ratio_min": ratios.relaxation_ratio.min(),
                "ratio_max": ratios.relaxation_ratio.max(),
                "excess_late_demand": ratios.excess_late_demand.mean(),
            }
        )

    for season in sorted(panel.SEASON.unique()):
        ratios = relaxation(
            shots[shots.SEASON == season], continuation_value(panel[panel.SEASON == season])
        )
        rows.append(
            {
                "cut": f"season {season}-{str(season + 1)[-2:]}",
                "n_chances": int((panel.SEASON == season).sum()),
                "ratio_min": ratios.relaxation_ratio.min(),
                "ratio_max": ratios.relaxation_ratio.max(),
                "excess_late_demand": ratios.excess_late_demand.mean(),
            }
        )
    return pd.DataFrame(rows)


MIN_TEAM_SHOTS = 5_000


def team_relaxation(
    shots: pd.DataFrame,
    panel: pd.DataFrame,
    min_shots: int = MIN_TEAM_SHOTS,
    min_chances: int = 50,
    null_sd: float | None = None,
) -> pd.DataFrame:
    """The relaxation ratio computed per team, on that team's own chances and shots.

    The league figure is ~0.6. If some teams sit near 0.4 and others near 0.9, that is a real
    difference in how offenses handle an expiring clock — the direct answer to "who is being
    inefficient", and the version of the per-player question that is not tautological.

    **Why this escapes the trap that killed `player_exercise`.** That measure was mean surplus,
    which turned out to be mean shot quality renamed (correlation 0.984). The ratio is a
    different object: it compares each team's *own* boundary movement against its *own*
    continuation value, so the level of shot quality divides out and only the shape remains.
    A team of great shooters and a team of poor ones can score the same ratio.

    Pass `null_sd` from `team_relaxation_null` to get shrunk estimates. Without it the raw
    ratios are returned and should not be read as a ranking: thirty teams each fitting a
    two-stage quantity on a thirtieth of the data produce spread by construction, and on the
    real data roughly **two thirds of the raw variance is that noise**.
    """
    rows = []
    for team in sorted(shots.TEAM_ABBREVIATION.dropna().unique()):
        taken = shots[shots.TEAM_ABBREVIATION == team]
        chances = panel[panel.TEAM == team]
        if len(taken) < min_shots or chances.empty:
            continue
        ratios = relaxation(taken, continuation_value(chances, min_chances=min_chances))
        rows.append(
            {
                "TEAM": team,
                "n_chances": len(chances),
                "n_shots": len(taken),
                "relaxation_ratio": float(ratios.relaxation_ratio.mean()),
                "excess_late_demand": float(ratios.excess_late_demand.mean()),
            }
        )
    result = pd.DataFrame(rows).sort_values("relaxation_ratio").reset_index(drop=True)
    if null_sd is not None and len(result) > 1:
        observed = float(result.relaxation_ratio.var(ddof=1))
        signal = max(observed - null_sd**2, 0.0)
        share = signal / observed if observed else 0.0
        league = float(result.relaxation_ratio.mean())
        result["SHRUNK"] = league + (result.relaxation_ratio - league) * share
        result.attrs["signal_share"] = share
        result.attrs["league_mean"] = league
    return result


def team_relaxation_null(
    shots: pd.DataFrame,
    panel: pd.DataFrame,
    n_draws: int = 20,
    seed: int = 0,
) -> dict:
    """How much team-to-team spread appears when team labels are meaningless.

    Splitting a fixed dataset thirty ways and fitting a two-stage quantity in each cell
    produces spread whether or not teams differ, so the observed standard deviation means
    nothing without this. Labels are permuted across chances and shots at the real group sizes
    and the whole calculation is repeated.
    """
    teams = sorted(panel.TEAM.dropna().unique())
    spreads = []
    for draw in range(n_draws):
        rng = np.random.default_rng(seed + draw)
        fake_panel = panel.assign(TEAM=rng.choice(teams, len(panel)))
        fake_shots = shots.assign(TEAM_ABBREVIATION=rng.choice(teams, len(shots)))
        result = team_relaxation(fake_shots, fake_panel)
        spreads.append(float(result.relaxation_ratio.std(ddof=1)))
    return {"null_spreads": spreads, "null_mean": float(np.mean(spreads))}
