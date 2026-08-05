"""Two situational questions, pre-registered in `reports/preregistration_situational.md`.

**H4** asks *where in the possession* offenses differ. `stopping.team_relaxation` returns one
ratio per team for a whole possession, which cannot distinguish a team that is fine early and
impatient late from one that is uniformly impatient.

**H5** asks *who the ball goes to* when the clock dies, and whether concentrating it pays.

Both are correlations between team attributes. Neither identifies a causal effect, for the
reason that caps the headline result itself: a declined shot leaves no record, so what an
offense refused is never observed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.models.rulechange import _cluster_ols
from possval.models.stopping import (
    FULL_CLOCK,
    RESET_INSTANT,
    InsufficientData,
    continuation_value,
    exercise_boundary,
)

# Fixed in the pre-registration before any of this ran. Second 0 is excluded (violations and
# heaves, which are not decisions) and second 24 is excluded (the reset instant — tips and
# putbacks arriving with the clock at maximum, already excluded inside `exercise_boundary`).
BANDS: dict[str, tuple[int, int]] = {
    "late": (1, 7),
    "middle": (8, 15),
    "early": (16, 23),
}

# A slope needs more than two points to be worth fitting, and a band that loses most of its
# seconds to the shot-count threshold is not the band that was registered.
MIN_SECONDS_IN_BAND = 4

# Below this the value slope is too flat to divide by: the ratio is a quotient of two fitted
# slopes, and a denominator near zero produces an arbitrarily large number rather than a large
# effect. Points per second.
MIN_VALUE_SLOPE = 0.002

# The primary quantile for the boundary. The level of the boundary is not identified — the
# quantile choice flips the sign of "too aggressive" versus "too patient" — so only the shape
# is claimed, and the sweep in `band_quantile_sweep` shows the shape surviving the choice.
PRIMARY_QUANTILE = 0.05


def _weighted_slope(x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> float:
    """Slope of `y` on `x` by weighted least squares.

    Weights are observation counts, so a second of the clock backed by 40,000 shots is not
    given the same say as one backed by 300.
    """
    w = np.asarray(weights, dtype=float)
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
    if w.sum() <= 0:
        return float("nan")
    x_bar = np.average(x, weights=w)
    y_bar = np.average(y, weights=w)
    variance = np.sum(w * (x - x_bar) ** 2)
    if variance <= 0:
        return float("nan")
    return float(np.sum(w * (x - x_bar) * (y - y_bar)) / variance)


def band_relaxation(
    shots: pd.DataFrame,
    values: pd.DataFrame,
    quantile: float = PRIMARY_QUANTILE,
    min_shots_per_second: int = 50,
    bands: dict[str, tuple[int, int]] | None = None,
) -> pd.DataFrame:
    """Relaxation ratio within each band of the clock, from fitted slopes.

    `stopping.relaxation` differences the boundary at second 23 against second 1. That is two
    numbers out of twenty-three, and it is why H1 in the first exploration could not be
    evaluated on a two-season holdout at all: split thirty ways, some teams had no shots
    surviving the reporting threshold at second 23, and the ratio had no anchor.

    Fitting a slope over every second in the band uses the whole band and degrades gracefully
    when one second is thin. Both series rise with the clock, so both slopes are positive and a
    ratio below 1 means the offense's standard moves more slowly than the value it is giving
    up — under-relaxation, the headline finding, localised.
    """
    bands = bands or BANDS
    boundary = exercise_boundary(shots, values, quantile=quantile, min_shots=min_shots_per_second)
    table = boundary.merge(values[["SECOND", "N_CONTINUED"]], on="SECOND", how="left")

    rows = []
    for name, (low, high) in bands.items():
        band = table[(table.SECOND >= low) & (table.SECOND <= high)]
        if len(band) < MIN_SECONDS_IN_BAND:
            continue
        seconds = band.SECOND.to_numpy(dtype=float)
        value_slope = _weighted_slope(seconds, band.V_CONT.to_numpy(), band.N_CONTINUED.to_numpy())
        if not np.isfinite(value_slope) or abs(value_slope) < MIN_VALUE_SLOPE:
            continue
        boundary_slope = _weighted_slope(seconds, band.BOUNDARY.to_numpy(), band.N_SHOTS.to_numpy())
        rows.append(
            {
                "BAND": name,
                "quantile": quantile,
                "n_seconds": len(band),
                "n_shots": int(band.N_SHOTS.sum()),
                "boundary_slope": boundary_slope,
                "value_slope": value_slope,
                "relaxation_ratio": boundary_slope / value_slope,
                "mean_gap": float(np.average(band.GAP, weights=band.N_SHOTS)),
            }
        )
    return pd.DataFrame(rows)


def band_quantile_sweep(
    shots: pd.DataFrame,
    values: pd.DataFrame,
    quantiles: tuple[float, ...] = (0.02, 0.05, 0.10, 0.20, 0.25),
) -> pd.DataFrame:
    """The band ratios at every boundary quantile, since the level is not identified."""
    return pd.concat(
        [band_relaxation(shots, values, quantile=q) for q in quantiles], ignore_index=True
    )


MIN_TEAM_SHOTS = 5_000


def team_band_relaxation(
    shots: pd.DataFrame,
    panel: pd.DataFrame,
    min_shots: int = MIN_TEAM_SHOTS,
    min_chances: int = 50,
    min_shots_per_second: int = 50,
    quantile: float = PRIMARY_QUANTILE,
) -> pd.DataFrame:
    """Band relaxation per team, on that team's own chances and its own shots.

    Each team's boundary is compared against its *own* continuation value, so the level of
    shot quality divides out and only the shape remains. That is what keeps this from
    collapsing into "who has better shooters", the way per-player exercise surplus did.
    """
    rows = []
    for team in sorted(shots.TEAM_ABBREVIATION.dropna().unique()):
        taken = shots[shots.TEAM_ABBREVIATION == team]
        chances = panel[panel.TEAM == team]
        if len(taken) < min_shots or chances.empty:
            continue
        values = continuation_value(chances, min_chances=min_chances)
        if values.empty:
            continue
        bands = band_relaxation(
            taken, values, quantile=quantile, min_shots_per_second=min_shots_per_second
        )
        for row in bands.to_dict("records"):
            rows.append({"TEAM": team, **row})
    if not rows:
        return pd.DataFrame(
            columns=["TEAM", "BAND", "relaxation_ratio", "boundary_slope", "value_slope"]
        )
    return pd.DataFrame(rows)


def _band_spread(table: pd.DataFrame) -> pd.Series:
    """Variance of the team ratios within each band."""
    return table.groupby("BAND").relaxation_ratio.var(ddof=1)


def team_band_null(
    shots: pd.DataFrame,
    panel: pd.DataFrame,
    n_draws: int = 50,
    seed: int = 0,
    **kwargs,
) -> pd.DataFrame:
    """Per-band variance of the team ratios when team labels carry no information.

    The permutation unit is the **team-game**, with one shared mapping driving both frames —
    the same construction as `stopping.team_relaxation_null`, and for the same three reasons
    documented there: permuting rather than resampling preserves block counts, relabelling
    whole team-games preserves within-team clustering, and one mapping keeps a fake team's
    continuation value paired with its own shots.

    This null is doing more work here than it does for the single-number ratio. The band ratio
    is a quotient of two fitted slopes, and the early band's value slope is the flattest of the
    three, so its ratio has the heaviest tails purely as arithmetic. Because the null runs the
    **identical estimator** on scrambled labels, that inflation appears on both sides of the
    signal share and cancels. Comparing raw variances across bands would not be safe; comparing
    signal shares is.
    """
    panel = panel.dropna(subset=["TEAM"])
    shots = shots.dropna(subset=["TEAM_ABBREVIATION"])

    panel_key = panel.GAME_ID.astype(str) + "|" + panel.TEAM.astype(str)
    shots_key = shots.GAME_ID.astype(str) + "|" + shots.TEAM_ABBREVIATION.astype(str)
    codes, _ = pd.factorize(pd.concat([panel_key, shots_key], ignore_index=True))
    panel_at, shots_at = codes[: len(panel)], codes[len(panel) :]

    teams = pd.concat([panel.TEAM, shots.TEAM_ABBREVIATION], ignore_index=True).astype(str)
    labels = teams.groupby(codes).first().to_numpy()

    draws = []
    for draw in range(n_draws):
        rng = np.random.default_rng(seed + draw)
        fake = rng.permutation(labels)
        result = team_band_relaxation(
            shots.assign(TEAM_ABBREVIATION=fake[shots_at]),
            panel.assign(TEAM=fake[panel_at]),
            **kwargs,
        )
        if result.empty:
            continue
        spread = _band_spread(result)
        spread.name = draw
        draws.append(spread)
    if not draws:
        raise InsufficientData("no permutation draw produced enough teams to estimate a null")
    return pd.concat(draws, axis=1).T


def band_signal_share(
    shots: pd.DataFrame, panel: pd.DataFrame, n_draws: int = 50, seed: int = 0, **kwargs
) -> pd.DataFrame:
    """H4's test statistic: how much of each band's team spread survives the null.

    `signal = max(observed_var - null_var, 0) / observed_var`. Zero in every band is a real
    possible answer and means the question cannot be resolved at this sample size, not that
    teams are identical.
    """
    observed_table = team_band_relaxation(shots, panel, **kwargs)
    if observed_table.empty:
        raise InsufficientData("no team cleared the thresholds for a band ratio")
    observed = _band_spread(observed_table)
    counts = observed_table.groupby("BAND").size()
    null = team_band_null(shots, panel, n_draws=n_draws, seed=seed, **kwargs)

    rows = []
    for band in BANDS:
        if band not in observed.index or band not in null.columns:
            continue
        null_band = null[band].dropna()
        observed_var = float(observed[band])
        null_var = float(null_band.mean())
        signal = max(observed_var - null_var, 0.0)
        team_ratios = observed_table[observed_table.BAND == band].relaxation_ratio
        # The value slope is the denominator of every ratio in this band. If teams disagree
        # about it as much as they disagree about anything else, the ratio is unstable for
        # arithmetic reasons and the band's spread should not be read as behaviour.
        value_slopes = observed_table[observed_table.BAND == band].value_slope
        rows.append(
            {
                "BAND": band,
                "n_teams": int(counts.get(band, 0)),
                "mean_ratio": float(team_ratios.mean()),
                "observed_sd": float(np.sqrt(observed_var)),
                "null_sd": float(np.sqrt(null_var)),
                "null_sd_p95": float(np.sqrt(null_band.quantile(0.95))),
                "signal_share": float(signal / observed_var) if observed_var else 0.0,
                "value_slope_cv": float(value_slopes.std(ddof=1) / abs(value_slopes.mean()))
                if value_slopes.mean()
                else float("nan"),
                "n_draws": int(len(null_band)),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------
# H5: late-clock usage concentration
# ---------------------------------------------------------------------------------------

# The boundary of "late". Matches the `late` band above and `stopping.LATE_CLOCK`, so the two
# hypotheses are talking about the same seconds.
LATE_CLOCK = 7

# A team-season needs enough late-clock attempts for a Herfindahl index to mean anything. With
# fewer than this the index is driven by which of four players happened to take the shots.
MIN_LATE_FGA = 200


def _herfindahl(counts: pd.Series) -> float:
    total = counts.sum()
    if total <= 0:
        return float("nan")
    shares = counts / total
    return float((shares**2).sum())


def concentration_panel(
    shots: pd.DataFrame,
    panel: pd.DataFrame,
    late: int = LATE_CLOCK,
    min_late_fga: int = MIN_LATE_FGA,
) -> pd.DataFrame:
    """One row per team-season: how concentrated the late clock is, and what it produced.

    The outcome and the control are **disjoint samples of chances** by construction. Chances
    live at second `late` supply the outcome; chances that ended above it supply the control.
    Controlling on full-season efficiency instead would put the outcome's own chances on both
    sides of the regression and manufacture a correlation.

    Chances that began below `late` — a short second chance that never had time — belong to
    neither group and are dropped from both, since neither "reached the late clock" nor "ended
    before it" describes them.
    """
    taken = shots.dropna(subset=["SHOT_CLOCK", "PLAYER_ID", "TEAM_ABBREVIATION"]).copy()
    taken["SECOND"] = taken.SHOT_CLOCK.round().clip(0, FULL_CLOCK).astype(int)
    taken = taken[taken.SECOND != RESET_INSTANT]
    late_shots = taken[(taken.SECOND >= 1) & (taken.SECOND <= late)]

    usage = []
    for (season, team), frame in late_shots.groupby(["SEASON", "TEAM_ABBREVIATION"]):
        if len(frame) < min_late_fga:
            continue
        everything = taken[(taken.SEASON == season) & (taken.TEAM_ABBREVIATION == team)]
        hhi_late = _herfindahl(frame.groupby("PLAYER_ID").size())
        hhi_all = _herfindahl(everything.groupby("PLAYER_ID").size())
        usage.append(
            {
                "SEASON": season,
                "TEAM": team,
                "HHI_LATE": hhi_late,
                "HHI_ALL": hhi_all,
                "FUNNEL": hhi_late - hhi_all,
                "N_LATE_FGA": len(frame),
                "TOP_LATE_SHARE": float(
                    frame.groupby("PLAYER_ID").size().max() / len(frame)
                ),
            }
        )
    usage_table = pd.DataFrame(usage)
    if usage_table.empty:
        raise InsufficientData("no team-season cleared the late-clock attempt threshold")

    chances = panel.dropna(subset=["TEAM"])
    if "PERIOD_EXPIRED" in chances.columns:
        chances = chances[~chances.PERIOD_EXPIRED]
    reached = chances[(chances.START_SC >= late) & (chances.END_SC <= late)]
    ended_early = chances[(chances.START_SC >= late) & (chances.END_SC > late)]

    outcome = (
        reached.groupby(["SEASON", "TEAM"])
        .PTS_FG.agg(PPC_LATE="mean", N_LATE_CHANCES="size")
        .reset_index()
    )
    control = (
        ended_early.groupby(["SEASON", "TEAM"])
        .PTS_FG.agg(PPC_EARLY="mean", N_EARLY_CHANCES="size")
        .reset_index()
    )
    merged = usage_table.merge(outcome, on=["SEASON", "TEAM"], how="inner").merge(
        control, on=["SEASON", "TEAM"], how="inner"
    )
    return merged.sort_values(["SEASON", "TEAM"]).reset_index(drop=True)


def _concentration_design(
    table: pd.DataFrame, treatment: str, control: str
) -> tuple[np.ndarray, list[str]]:
    columns = [
        np.ones(len(table)),
        table[treatment].to_numpy(float),
        table[control].to_numpy(float),
    ]
    names = ["intercept", treatment, control]
    for season in sorted(table.SEASON.unique())[1:]:  # first season is the reference level
        columns.append((table.SEASON == season).to_numpy(float))
        names.append(f"season_{season}")
    return np.column_stack(columns), names


def wild_cluster_bootstrap_t(
    design: np.ndarray,
    y: np.ndarray,
    clusters: np.ndarray,
    names: list[str],
    target: str,
    seed: int = 0,
    n_draws: int = 9_999,
) -> dict:
    """Wild cluster bootstrap-t p-value for one coefficient (Cameron, Gelbach & Miller 2008).

    The general form of `rulechange.wild_cluster_bootstrap`, which is welded to the DiD design.
    Thirty team clusters is more comfortable than the nine seasons that killed the rule-change
    result, but "more comfortable than nine" is not the same as enough, and the asymptotic
    clustered standard error is the assumption this project has already been burned by once.

    2^30 sign vectors cannot be enumerated, so this samples. The null is imposed by refitting
    without the target column, which is what makes the reference distribution a null
    distribution rather than a distribution around the estimate.
    """
    target_index = names.index(target)
    unique = np.unique(clusters)
    observed = _cluster_ols(design, y, clusters, names)[target]
    observed_t = observed["t"]

    keep = [i for i in range(design.shape[1]) if i != target_index]
    restricted = design[:, keep]
    coefficients, *_ = np.linalg.lstsq(restricted, y, rcond=None)
    fitted = restricted @ coefficients
    residual = y - fitted

    masks = [clusters == cluster for cluster in unique]
    rng = np.random.default_rng(seed)
    stats = np.empty(n_draws)
    weights = np.ones(len(y))
    for draw in range(n_draws):
        signs = rng.choice([-1.0, 1.0], len(unique))
        for rows, sign in zip(masks, signs, strict=True):
            weights[rows] = sign
        star = fitted + residual * weights
        stats[draw] = _cluster_ols(design, star, clusters, names)[target]["t"]

    finite = stats[np.isfinite(stats)]
    return {
        "estimate": observed["estimate"],
        "std_error": observed["std_error"],
        "t": observed_t,
        "p_wild": float(np.mean(np.abs(finite) >= abs(observed_t))),
        "n_clusters": len(unique),
        "n_draws": int(len(finite)),
        "crit_95": float(np.quantile(np.abs(finite), 0.95)),
    }


def fit_concentration(
    table: pd.DataFrame,
    treatment: str = "HHI_LATE",
    outcome: str = "PPC_LATE",
    control: str = "PPC_EARLY",
    seed: int = 0,
    n_draws: int = 9_999,
) -> dict:
    """H5's test: late-clock efficiency on late-clock concentration, team-clustered.

    Season dummies absorb league-wide scoring drift, which rose materially over the sample.
    Standard errors cluster on team, because a franchise's late-clock philosophy persists
    across seasons and 300 team-seasons are not 300 independent observations of it.
    """
    frame = table.dropna(subset=[treatment, outcome, control]).copy()
    design, names = _concentration_design(frame, treatment, control)
    y = frame[outcome].to_numpy(dtype=float)
    clusters = frame.TEAM.to_numpy()

    fitted = _cluster_ols(design, y, clusters, names)
    wild = wild_cluster_bootstrap_t(
        design, y, clusters, names, treatment, seed=seed, n_draws=n_draws
    )
    # A coefficient per unit of a Herfindahl index is unreadable. One standard deviation of
    # observed concentration is the unit anyone can picture.
    treatment_sd = float(frame[treatment].std(ddof=1))
    return {
        "n": len(frame),
        "n_teams": int(frame.TEAM.nunique()),
        "treatment": treatment,
        "outcome": outcome,
        "estimate": wild["estimate"],
        "std_error": wild["std_error"],
        "t": wild["t"],
        "p_wild": wild["p_wild"],
        "treatment_sd": treatment_sd,
        "effect_per_sd": wild["estimate"] * treatment_sd,
        "control_t": fitted[control]["t"],
        "n_draws": wild["n_draws"],
    }
