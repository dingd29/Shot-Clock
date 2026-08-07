"""What is the ball worth at the end of a period, and do teams hand it over when they should?

`twoforone.py` established that offenses hurry when hurrying buys a second trip (they do,
unmistakably) and that it is worth nothing measurable. This asks *why* nothing, and whether the
behaviour makes sense given the answer.

The premise behind end-of-period clock management is that there are good and bad moments to give
the ball away — a sawtooth in the value of possession, driven by whether the opponent can get a
clean trip before the buzzer. A team running a 2-for-1 is trying to land the handover in a
trough. **This module measures whether the sawtooth exists.**

Two ways to answer it, and they disagree:

  `mechanical_benchmark`  a dynamic program over alternating possessions. Predicts a clear
                          sawtooth. **It does not survive validation** and is kept as a
                          documented failure — see its docstring.
  `ball_value`            the same quantity measured directly, no model. This is the one used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.models.rebound import possession_panel

REGULATION_PERIODS = (1, 2, 3, 4)
# The range where end-of-period decisions are live. Below 6 seconds a possession is a single
# shot; above 45 the buzzer is not yet shaping anyone's choices.
CLOCK_RANGE = (6, 45)


def possession_level(panel: pd.DataFrame) -> pd.DataFrame:
    """Collapse chances into possessions, with net points from each one to the buzzer.

    Possessions rather than chances, because the whole question is about *handing the ball to
    the opponent*, and an offensive rebound does not do that. Working at chance level makes
    consecutive rows alternate only 84.5% of the time, which quietly breaks every alternating
    argument built on top.
    """
    chained = possession_panel(panel[panel.PERIOD.isin(REGULATION_PERIODS)])
    keys = ["GAME_ID", "PERIOD", "POSSESSION_ID"]
    grouped = chained.groupby(keys, sort=False)
    poss = (
        pd.DataFrame(
            {
                "TEAM": grouped.TEAM.first(),
                "SEASON": grouped.SEASON.first(),
                "START_GC": grouped.PREV_GC.first(),
                "END_GC": grouped.LAST_GC.last(),
                "START_SC": grouped.START_SC.first(),
                "END_SC": grouped.END_SC.last(),
                "PTS": grouped.PTS_FG.sum(),
            }
        )
        .reset_index()
        .sort_values(keys)
    )

    side = poss.groupby(["GAME_ID", "PERIOD"], sort=False).TEAM.transform(
        lambda s: (s != s.iloc[0]).astype(int)
    )
    poss["SIDE"] = side
    for value in (0, 1):
        points = poss.PTS.where(poss.SIDE == value, 0.0)
        block = points.groupby([poss.GAME_ID, poss.PERIOD], sort=False)
        poss[f"REST_{value}"] = block.transform("sum") - block.cumsum() + points
    own = np.where(poss.SIDE == 0, poss.REST_0, poss.REST_1)
    opponent = np.where(poss.SIDE == 0, poss.REST_1, poss.REST_0)

    poss["NET_FROM_START"] = own - opponent
    poss["NET_AFTER"] = poss.NET_FROM_START - poss.PTS
    poss["DURATION"] = poss.START_GC - poss.END_GC
    return poss.drop(columns=["REST_0", "REST_1"])


def ball_value(
    poss: pd.DataFrame, clock_range: tuple[int, int] = CLOCK_RANGE, min_possessions: int = 400
) -> pd.DataFrame:
    """`V_ball(S)`: net points from here to the buzzer, for the team holding the ball at `S`.

    Measured, not modelled. This is the equilibrium value under how teams actually play, which
    is the right object for the question being asked: when you hand the ball over, the opponent
    will play the way opponents actually play, not the way a model says they should.
    """
    low, high = clock_range
    frame = poss.assign(S=poss.START_GC.round())
    frame = frame[frame.S.between(low, high)]
    table = frame.groupby("S").NET_FROM_START.agg(N="size", V_BALL="mean", SD="std")
    table["SE"] = table.SD / np.sqrt(table.N)
    return table[table.N >= min_possessions].reset_index()


def handover_identity(poss: pd.DataFrame, values: pd.DataFrame) -> dict:
    """Ending a possession at `S` should be worth `−V_ball(S)`. Check that it is.

    Not a hypothesis test — an internal consistency check on the accounting. If a possession
    ending at `S` and a possession starting at `S` do not agree up to sign, the two sides are
    not measuring the same handover and nothing built on them means anything.
    """
    lookup = values.set_index("S").V_BALL
    ending = poss.assign(S=poss.END_GC.round())
    ending = ending[ending.S.isin(lookup.index)]
    observed = ending.groupby("S").NET_AFTER.agg(N="size", OBSERVED="mean")
    observed = observed[observed.N >= 400]
    predicted = -lookup.reindex(observed.index)
    difference = observed.OBSERVED - predicted
    return {
        "n_bins": len(observed),
        "correlation": float(observed.OBSERVED.corr(predicted)),
        "mean_abs_error": float(difference.abs().mean()),
        "bias": float(difference.mean()),
    }


def flatness(values: pd.DataFrame, degree: int = 2) -> dict:
    """Is there structure in `V_ball(S)` beyond a smooth trend, and how big is it?

    The sawtooth, if it exists, is what end-of-period clock management is trying to exploit. A
    smooth polynomial captures "more time left is worth more"; anything left over is the part a
    team could actually play against.

    Reported as a chi-square against the measured per-bin noise floor, plus the residual
    amplitude in points — which is the number that decides whether the structure is worth
    anything, regardless of its p-value at this sample size.
    """
    x = values.S.to_numpy(dtype=float)
    y = values.V_BALL.to_numpy()
    weights = values.N.to_numpy(dtype=float)
    design = np.column_stack([x**power for power in range(degree + 1)])
    root = np.sqrt(weights)[:, None]
    coefficients, *_ = np.linalg.lstsq(design * root, y * np.sqrt(weights), rcond=None)
    residual = y - design @ coefficients

    errors = values.SE.to_numpy()
    chi_square = float(np.sum((residual / errors) ** 2))
    dof = len(x) - (degree + 1)
    residual_sd = float(residual.std(ddof=1))
    noise = float(np.sqrt(np.mean(errors**2)))
    return {
        "n_bins": len(x),
        "chi_square": chi_square,
        "dof": dof,
        "residual_sd": residual_sd,
        "noise_floor": noise,
        # What is left after removing the noise the bins carry anyway. This is the amplitude a
        # team could in principle play against.
        "structure_amplitude": float(np.sqrt(max(residual_sd**2 - noise**2, 0.0))),
        "range": float(y.max() - y.min()),
    }


def mechanical_benchmark(
    poss: pd.DataFrame, max_seconds: int = 60, natural_from: float = 90.0
) -> pd.DataFrame:
    """A dynamic program over strictly alternating possessions. **Rejected — kept as a record.**

    `V(S) = Σ_d P(D = d) [ E(points | d) − V(S − d) ]`, with the duration and scoring
    distributions taken from mid-period possessions so that end-of-period hurrying does not
    define the benchmark meant to judge it.

    It produces exactly the textbook picture: a peak around 20 seconds (you get the last shot)
    and a trough near 35 (you shoot, they get the last shot), a sawtooth of about 0.14 points.
    That picture is wrong. Scored against observed outcomes it correlates **−0.03** with a mean
    absolute error of **0.19 points** — worse than predicting a constant.

    Two identifiable reasons, both fatal:

    - It assumes possession alternates. At chance level that holds 84.5% of the time; the model
      has no offensive rebounds.
    - It truncates: a possession that would outlast the period scores zero. That badly
      understates value at low `S`, exactly where the buzzer matters most.

    Kept because the failure is the point. The sawtooth everybody reasons about is an artifact
    of assuming basketball is a clean alternating renewal process, and `ball_value` measures
    what is actually there instead.
    """
    natural = poss[(poss.START_GC > natural_from) & poss.DURATION.between(1, 30)]
    durations = natural.DURATION.round()
    pmf = durations.value_counts(normalize=True).sort_index()
    points = natural.assign(D=durations).groupby("D").PTS.mean()
    overall = float(natural.PTS.mean())

    value = np.zeros(max_seconds + 1)
    for second in range(1, max_seconds + 1):
        value[second] = sum(
            probability * (points.get(int(d), overall) - value[second - int(d)])
            for d, probability in pmf.items()
            if int(d) <= second
        )
    return pd.DataFrame({"S": np.arange(max_seconds + 1), "V_MECHANICAL": value})


def selection_bias(window_frame: pd.DataFrame, gained_between: tuple[float, float]) -> dict:
    """How wrong the observational answer is, against the quasi-experimental one.

    `E[net | clock used]` says teams that finish in 5 seconds do enormously better than teams
    that take 13. Read as a policy that is nonsense: possessions ending at 5 seconds ended there
    because a transition layup *appeared*, not because anybody chose to hurry. The same trap that
    makes the raw efficiency-vs-clock curve uninterpretable.

    This returns the observational gap so it can be set beside the reduced-form estimate from
    `twoforone`, where treatment is *when the ball was gained* and is set by the opponent.
    """
    low, high = gained_between
    frame = window_frame[window_frame.PREV_GC.between(low, high)]
    used = frame.CLOCK_USED.round()
    grouped = frame.assign(U=used).groupby("U").agg(
        N=("NET_REST", "size"), NET=("NET_REST", "mean"), PTS_THIS=("PTS_FG", "mean")
    )
    grouped = grouped[grouped.N >= 200]
    fast = grouped.loc[grouped.index <= 6, "NET"].mean()
    slow = grouped.loc[grouped.index.isin(range(11, 17)), "NET"].mean()
    return {
        "gained_between": f"{low:.0f}-{high:.0f}",
        "net_if_finished_by_6s": float(fast),
        "net_if_finished_11_to_16s": float(slow),
        "observational_gap": float(fast - slow),
        "median_clock_used": float(frame.CLOCK_USED.median()),
    }


def handover_behaviour(poss: pd.DataFrame, values: pd.DataFrame) -> pd.DataFrame:
    """Where teams actually hand the ball over, against where `V_ball` says they should.

    The behavioural test. If end-of-period management is being played well, the distribution of
    handover times should favour the values of `S` where `V_ball` is lowest — those are the
    moments least useful to the opponent.
    """
    lookup = values.set_index("S")
    ending = poss.assign(S=poss.END_GC.round())
    ending = ending[ending.S.isin(lookup.index)]
    counts = ending.groupby("S").size().rename("N_HANDOVERS")
    table = lookup.join(counts, how="inner")
    table["SHARE"] = table.N_HANDOVERS / table.N_HANDOVERS.sum()
    # What the average handover costs, against handing over at the single best second.
    table["EXCESS_VS_BEST"] = table.V_BALL - table.V_BALL.min()
    return table.reset_index()
