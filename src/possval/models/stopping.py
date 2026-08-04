"""Shooting as an optimal-stopping problem.

The efficiency-vs-clock curve is a selected sample at every point: possessions alive at 5
seconds are the ones where nothing worked earlier. Framing the shot as an exercise decision
(take what's available, or hold an option whose value decays) conditions on the decision
rather than the outcome, which is what the curve can't do.

Only one side is identified. Taken shots come with a model value, so shooting when holding was
worth more is measurable. A declined shot leaves no record, so holding too long isn't.
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

    A chance's opening moment is never a logged event, so the start clock is recovered as the
    first event's shot clock plus the game-clock gap back to the previous chance's last event.
    Both clocks fall together within a chance, so this is exact up to the inbound delay. It
    returns the rule values: median 24 after a defensive rebound, 14 after an offensive one,
    26 after a made basket (24 plus the 2s inbound delay), hence the clip back to 24.
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

    A chance is live at `t` if it began at or above `t` and ended at or below it. Those that
    didn't end at `t` are the ones where the offense declined and played on, so their mean
    outcome is the value of continuing.

    This is continuation under observed behaviour, not optimal play, which is the right
    benchmark for a marginal question: should this shot have been taken given how this offense
    would otherwise have finished. `outcome` defaults to field-goal points to match `XPTS`.
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

    A shot at `t` worth `q` is premature when `q < V(t)`.
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
    """How much continuation value moves when free throws are counted.

    `XPTS` is field-goal points, so both sides run on field-goal points. That understates
    `V(t)`, since declining also preserves the chance of drawing a foul, and understates it in
    a known direction: a lower bar makes fewer shots look premature. So the reported result is
    conservative.
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
    """The implied shoot-or-hold boundary against the optimal one.

    Under a threshold rule every taken shot sits above `b(t)`, so the bottom of the accepted
    distribution estimates it. The 5th percentile rather than the minimum, since the rule
    isn't sharp: ~5% of shots fall below continuation value.

    Optimal exercise puts `b(t) = V(t)`, so positive `GAP` means offenses demanded more than
    continuing was worth. It measures what teams accepted, not what they refused; a declined
    shot leaves no record, so a positive gap is equally consistent with nothing better being
    on offer.
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

    The boundary's level isn't identified: calling the 5th percentile the threshold rather
    than the 2nd or 20th moves the gap from -0.22 to +0.14, flipping the sign of "too
    aggressive" vs "too patient". Only the shape survives that choice, so both summaries are
    computed at every quantile.
    """
    rows = []
    for quantile in quantiles:
        boundary = exercise_boundary(shots, values, quantile=quantile).set_index("SECOND")
        late, early = LATE_SECONDS, EARLY_SECONDS
        # The ratio is anchored on specific seconds, and a thin subsample can fail to populate
        # them — a two-season slice split thirty ways leaves some teams with too few shots at
        # 23 seconds to clear the reporting threshold. Fail with the reason rather than a bare
        # KeyError from the index.
        missing = [t for t in (late[0], early[1]) if t not in boundary.index]
        if missing:
            raise InsufficientData(
                f"no boundary estimate at second(s) {missing}; "
                f"{len(shots):,} shots is too few to anchor the ratio"
            )
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

    This measure doesn't work, and the arithmetic says why: per-player mean surplus correlates
    0.984 with per-player mean late-clock `XPTS`, and the SD of their difference is 0.012
    against 0.067 for either alone. Every player's late shots span roughly the same seconds,
    so `V` enters as a near-constant and surplus is late-clock shot quality renamed. It ranks
    who finishes (+0.59 with rim share), not who decides.

    Kept because it looks like a skill ranking and would be easy to publish as one.
    `attrs["signal_share"]` is the variance left after subtracting sampling noise.
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


class InsufficientData(ValueError):
    """A subsample too thin to anchor the relaxation ratio at its endpoint seconds."""


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
        try:
            ratios = relaxation(taken, continuation_value(chances, min_chances=min_chances))
        except InsufficientData:
            # Dropping the team is right: an unanchored ratio is not a low ratio.
            continue
        rows.append(
            {
                "TEAM": team,
                "n_chances": len(chances),
                "n_shots": len(taken),
                "relaxation_ratio": float(ratios.relaxation_ratio.mean()),
                "excess_late_demand": float(ratios.excess_late_demand.mean()),
            }
        )
    if not rows:
        # Every team was too thin to anchor a ratio. Returning an empty frame with the right
        # columns keeps callers (and the permutation null) from failing on a missing key.
        return pd.DataFrame(
            columns=["TEAM", "n_chances", "n_shots", "relaxation_ratio", "excess_late_demand"]
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
    n_draws: int = 50,
    seed: int = 0,
    min_shots: int = MIN_TEAM_SHOTS,
    min_chances: int = 50,
) -> dict:
    """How much team-to-team spread appears when team labels are meaningless.

    Splitting a fixed dataset thirty ways and fitting a two-stage quantity in each cell
    produces spread whether or not teams differ, so the observed standard deviation means
    nothing without this.

    The permutation unit is the **team-game**, not the row. Three properties matter and each
    one was got wrong by an earlier version that drew labels i.i.d. with `rng.choice`:

    - Permuting rather than resampling keeps every fake team's block count equal to a real
      team's. Sampling with replacement equalises group sizes toward the mean, which shrinks
      the null spread and overstates how much signal is left.
    - Relabelling whole team-games keeps a team's chances contiguous. Scattering individual
      rows destroys the game and season clustering that real team samples have, and a null
      without that clustering is again too tight.
    - One mapping drives both frames, so a fake team's chances and its shots come from the
      same team-games. Shuffling them independently pairs a team's continuation value with
      somebody else's shots, which is not a null of anything.
    """
    panel = panel.dropna(subset=["TEAM"])
    shots = shots.dropna(subset=["TEAM_ABBREVIATION"])

    # Factorise the (game, team) blocks once; each draw is then a permutation of one array
    # plus two integer take operations, rather than a merge over 4.8M rows.
    panel_key = pd.MultiIndex.from_arrays([panel.GAME_ID, panel.TEAM])
    shots_key = pd.MultiIndex.from_arrays([shots.GAME_ID, shots.TEAM_ABBREVIATION])
    # `.unique()` is load-bearing: MultiIndex.union keeps duplicates, and get_indexer
    # requires a unique index.
    blocks = panel_key.union(shots_key).unique()
    panel_at = blocks.get_indexer(panel_key)
    shots_at = blocks.get_indexer(shots_key)
    labels = np.asarray(blocks.get_level_values(1))

    spreads = []
    for draw in range(n_draws):
        rng = np.random.default_rng(seed + draw)
        fake = rng.permutation(labels)
        # Thresholds must match the real call exactly. Letting the null keep its defaults
        # while the observed estimate used looser ones compares two different calculations.
        result = team_relaxation(
            shots.assign(TEAM_ABBREVIATION=fake[shots_at]),
            panel.assign(TEAM=fake[panel_at]),
            min_shots=min_shots,
            min_chances=min_chances,
        )
        if len(result) > 1:
            spreads.append(float(result.relaxation_ratio.std(ddof=1)))
    if not spreads:
        raise InsufficientData(
            "no permutation draw produced enough teams to estimate a null spread"
        )
    spreads = np.asarray(spreads)
    return {
        "null_spreads": spreads.tolist(),
        "null_mean": float(spreads.mean()),
        "null_sd": float(spreads.std(ddof=1)) if len(spreads) > 1 else float("nan"),
        "null_p05": float(np.percentile(spreads, 5)),
        "null_p95": float(np.percentile(spreads, 95)),
        "n_draws": len(spreads),
    }
