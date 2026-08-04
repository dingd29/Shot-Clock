"""Retest the creation-overlap hypothesis at five-man lineup level.

`synergy.py` found no relationship between creation overlap and offensive efficiency across
team-seasons. That test had a specific, stated weakness: a team's top creators do not share
the floor for all their minutes, so a real five-on-five effect could average away over a
season and leave no trace.

This module removes that weakness. The unit is a **lineup-season** — one specific five-man
group, in one season — and the outcome is the offense that group actually produced while
together. If usage redundancy costs anything, this is where it has to show up.

Same control discipline as the team-season test: individual quality enters as the five
players' mean scoring over strictly *earlier* seasons, so only efficiency unexplained by who
they are can be attributed to how they fit. The mean rather than the sum, because a lineup is
kept when four of five players have a history and a sum would read that missing fifth as low
quality rather than as unknown.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.features.lineups import ON_COURT_COLUMNS
from possval.models.creation import lineup_overlap

HOME_COLUMNS = ON_COURT_COLUMNS[:5]
AWAY_COLUMNS = ON_COURT_COLUMNS[5:]


def player_team_map(pbp: pd.DataFrame) -> pd.Series:
    """PLAYER_ID -> TEAM_ID, taken from whichever events name each player."""
    named = pbp[["PLAYER1_ID", "PLAYER1_TEAM_ID"]].dropna()
    named = named[named.PLAYER1_TEAM_ID > 0]
    return named.groupby("PLAYER1_ID").PLAYER1_TEAM_ID.agg(
        lambda s: s.value_counts().idxmax()
    )


def offensive_lineups(events: pd.DataFrame, teams: pd.Series) -> pd.DataFrame:
    """For every event, the five players on offense and the team they play for.

    Which side is on offense is decided by testing membership: whichever of the two
    five-man groups contains players belonging to `OFF_TEAM_ID`.
    """
    df = events.dropna(subset=["OFF_TEAM_ID"]).copy()

    home_team = df[HOME_COLUMNS[0]].map(teams)
    away_team = df[AWAY_COLUMNS[0]].map(teams)
    home_on_offense = home_team == df.OFF_TEAM_ID

    # Fall back to the away side's identity where the first home slot is unmapped.
    home_on_offense = home_on_offense.where(home_team.notna(), away_team != df.OFF_TEAM_ID)

    offense = np.where(
        home_on_offense.to_numpy()[:, None],
        df[HOME_COLUMNS].to_numpy(),
        df[AWAY_COLUMNS].to_numpy(),
    )
    for i in range(5):
        df[f"OFF_P{i + 1}"] = offense[:, i]

    # Sorted ids make the key order-independent, so the same five always hash alike.
    df["LINEUP_KEY"] = [
        "|".join(str(int(p)) for p in sorted(row)) for row in offense
    ]
    return df


def event_points(df: pd.DataFrame) -> np.ndarray:
    """Points scored on each event, read off the play-by-play description.

    The PBP feed carries no shot-value or free-throw-result column, so both facts have to
    come from the description text: made three-pointers are the ones containing "3PT", and
    a missed free throw is prefixed "MISS". An earlier version defaulted these through
    `.get(...)`, which scored every make as 2 and every free throw as good — quietly, since
    the resulting points-per-chance still looked believable.
    """
    missing = {"HOMEDESCRIPTION", "VISITORDESCRIPTION"} - set(df.columns)
    if missing:
        raise KeyError(f"cannot score events without description columns: {sorted(missing)}")

    text = df.HOMEDESCRIPTION.fillna("") + " " + df.VISITORDESCRIPTION.fillna("")
    made_fg = df.EVENTMSGTYPE == 1  # type 2 is a miss, so type 1 is made by definition
    is_three = text.str.contains("3PT", regex=False)
    made_ft = (df.EVENTMSGTYPE == 3) & ~text.str.contains("MISS", regex=False)

    return (
        np.where(made_fg & is_three, 3, 0)
        + np.where(made_fg & ~is_three, 2, 0)
        + np.where(made_ft, 1, 0)
    ).astype(float)


def lineup_efficiency(
    events_with_lineups: pd.DataFrame, min_chances: int = 100
) -> pd.DataFrame:
    """Points per chance for each offensive lineup.

    A *chance* is one shot-clock interval, which the reconstruction already identifies.
    Using chances rather than possessions is deliberate: it is the unit the shot-clock work
    produces natively, and it counts a second-chance opportunity separately, which is what
    an offense-generation question wants.
    """
    df = events_with_lineups
    df = df.assign(PTS=event_points(df))

    # CHANCE_ID restarts at zero in every game, so counting it alone would merge chance 7
    # of one game with chance 7 of every other and leave a denominator far too small —
    # which showed up as an impossible 2.2 points per chance.
    df = df.assign(
        CHANCE_UID=df.GAME_ID.astype(str) + ":" + df.CHANCE_ID.astype(str)
    )
    grouped = df.groupby(["SEASON", "LINEUP_KEY"], observed=True).agg(
        CHANCES=("CHANCE_UID", "nunique"),
        PTS=("PTS", "sum"),
        EVENTS=("EVENTNUM", "size"),
        TEAM_ID=("OFF_TEAM_ID", "first"),
    )
    grouped = grouped[grouped.CHANCES >= min_chances].reset_index()
    grouped["PTS_PER_CHANCE"] = grouped.PTS / grouped.CHANCES
    return grouped


def usage_rates(events_with_lineups: pd.DataFrame) -> pd.Series:
    """Shot attempts per 100 on-court offensive chances, per player-season.

    This is the **incumbent** measure of redundancy — how much of the ball a player wants —
    against which the creation-profile measure has to justify itself. Every public
    diminishing-returns adjustment is some version of this: five players whose usage demands
    sum past what one offense can supply must give something up.

    It is computed on-court rather than per game, which is the fair version: a player's shot
    rate should be measured against the chances he was actually present for, not against his
    team's whole season.
    """
    df = events_with_lineups.assign(
        CHANCE_UID=events_with_lineups.GAME_ID.astype(str)
        + ":"
        + events_with_lineups.CHANCE_ID.astype(str)
    )
    on_court = df.melt(
        id_vars=["SEASON", "CHANCE_UID"],
        value_vars=[f"OFF_P{i}" for i in range(1, 6)],
        value_name="PLAYER_ID",
    )
    chances = on_court.groupby(["PLAYER_ID", "SEASON"]).CHANCE_UID.nunique()

    attempts = (
        df[df.EVENTMSGTYPE.isin([1, 2])]
        .groupby(["PLAYER1_ID", "SEASON"])
        .size()
        .rename_axis(["PLAYER_ID", "SEASON"])
    )
    rate = 100 * attempts / chances
    return rate.dropna()


def build_lineup_panel(
    lineup_efficiency_table: pd.DataFrame,
    profiles_by_season: dict[int, pd.DataFrame],
    prior_quality: pd.DataFrame,
    usage: pd.Series | None = None,
) -> pd.DataFrame:
    """Attach overlap and a prior-quality control to each lineup-season.

    `prior_quality` is indexed by (PLAYER_ID, SEASON) and must hold only *earlier* seasons'
    scoring. Looking it up per season rather than once per player is what keeps the control
    from being contemporaneous with the outcome it is meant to absorb.

    `usage` adds the incumbent redundancy measure: the five players' combined shot demand,
    carried as `USAGE_SUM`, so the two hypotheses can be raced on identical rows.
    """
    rows = []
    for record in lineup_efficiency_table.itertuples(index=False):
        profiles = profiles_by_season.get(record.SEASON)
        if profiles is None:
            continue
        ids = [int(p) for p in record.LINEUP_KEY.split("|")]
        profiled = set(profiles.index.get_level_values("PLAYER_ID"))
        if not set(ids).issubset(profiled):
            continue

        quality = prior_quality.reindex(
            [(player, record.SEASON) for player in ids]
        ).PRIOR_PPA
        if quality.notna().sum() < 4:
            continue

        row = {
            "SEASON": record.SEASON,
            "TEAM_ID": record.TEAM_ID,
            "LINEUP_KEY": record.LINEUP_KEY,
            "CHANCES": record.CHANCES,
            "PTS_PER_CHANCE": record.PTS_PER_CHANCE,
            "OVERLAP": lineup_overlap(profiles, ids),
            "PRIOR_QUALITY": float(quality.mean(skipna=True)),
        }
        if usage is not None:
            demands = usage.reindex([(p, record.SEASON) for p in ids])
            # A lineup missing a player's usage would otherwise get a quietly smaller sum,
            # which reads as *less* redundancy — a bias toward the incumbent's null.
            row["USAGE_SUM"] = float(demands.sum()) if demands.notna().all() else np.nan
        rows.append(row)
    panel = pd.DataFrame(rows)
    panel["TEAM_SEASON"] = (
        panel.TEAM_ID.astype("Int64").astype(str) + ":" + panel.SEASON.astype(str)
    )
    return panel


def fit_lineup_overlap(
    panel: pd.DataFrame,
    outcome: str = "PTS_PER_CHANCE",
    fixed_effects: str = "season",
    cluster: str | None = "TEAM_SEASON",
    regressors: list[str] | None = None,
) -> dict:
    """Weighted least squares of lineup efficiency on overlap.

    Weighted by chances: a lineup with 800 chances carries far more information than one
    scraping the 100-chance threshold, and treating them equally would let noise dominate.

    `fixed_effects` selects what is absorbed. `"season"` leaves teams free to differ, so the
    overlap coefficient is identified partly by *good teams having high-overlap lineups* —
    which is confounded, because the same front offices that assemble talent also assemble
    modern shot diets. `"team_season"` compares only lineups fielded by the same team in the
    same year, which strips out roster quality, coaching and system, and asks the narrower
    question the hypothesis actually poses: given a squad, do its more redundant five-man
    groups score less?

    `cluster` is not optional in practice. 4,233 lineups are drawn from ~300 team-seasons and
    share players wholesale — a starter appears in dozens of rows — so treating each lineup
    as an independent observation understates the standard errors badly.
    """
    regressors = list(regressors or ["OVERLAP"])
    df = panel.dropna(subset=[outcome, "PRIOR_QUALITY", *regressors]).copy()

    design = [np.ones(len(df))]
    names = ["intercept"]
    for regressor in regressors:
        # Standardised so coefficients read as "per one standard deviation" and are
        # comparable between measures on completely different scales — a similarity in
        # [0,1] against a sum of shot rates in the tens.
        column = df[regressor].to_numpy(dtype=float)
        design.append((column - column.mean()) / column.std())
        names.append(regressor.lower())
    design.append(df.PRIOR_QUALITY.to_numpy())
    names.append("prior_quality")

    if fixed_effects == "season":
        groups = sorted(df.SEASON.unique())[1:]
        indicator = df.SEASON
    elif fixed_effects == "team_season":
        groups = sorted(df.TEAM_SEASON.dropna().unique())[1:]
        indicator = df.TEAM_SEASON
    else:
        raise ValueError(f"unknown fixed_effects: {fixed_effects!r}")

    for group in groups:
        design.append((indicator == group).to_numpy(dtype=float))
        names.append(f"fe_{group}")

    x = np.column_stack(design)
    y = df[outcome].to_numpy()
    w = np.sqrt(df.CHANCES.to_numpy(dtype=float))
    xw, yw = x * w[:, None], y * w

    coef, *_ = np.linalg.lstsq(xw, yw, rcond=None)
    resid = yw - xw @ coef
    bread = np.linalg.pinv(xw.T @ xw)

    if cluster is None:
        dof = len(y) - np.linalg.matrix_rank(xw)
        cov = (resid @ resid / dof) * bread
        n_clusters = None
    else:
        codes = df[cluster].astype("category").cat.codes.to_numpy()
        n_clusters = int(codes.max()) + 1
        meat = np.zeros((x.shape[1], x.shape[1]))
        for c in range(n_clusters):
            rows = codes == c
            score = xw[rows].T @ resid[rows]
            meat += np.outer(score, score)
        # Standard finite-cluster correction; without it few-cluster SEs run optimistic.
        scale = n_clusters / max(n_clusters - 1, 1)
        cov = scale * bread @ meat @ bread

    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, coef / se, np.nan)

    weighted_mean = np.average(y, weights=df.CHANCES)
    ss_tot = (w**2 * (y - weighted_mean) ** 2).sum()
    return {
        "n_lineups": len(y),
        "total_chances": int(df.CHANCES.sum()),
        "n_clusters": n_clusters,
        "fixed_effects": fixed_effects,
        "r2": 1 - (resid @ resid) / ss_tot,
        "coefficients": pd.DataFrame(
            {"term": names, "estimate": coef, "std_error": se, "t": t}
        ),
        "overlap_sd": float(df.OVERLAP.std()),
    }


SPECIFICATIONS = [
    ("season FE, unclustered", "season", None, 100),
    ("season FE, clustered", "season", "TEAM_SEASON", 100),
    ("team-season FE, clustered", "team_season", "TEAM_SEASON", 100),
    ("team-season FE, >=200 chances", "team_season", "TEAM_SEASON", 200),
    ("team-season FE, >=400 chances", "team_season", "TEAM_SEASON", 400),
    ("team-season FE, >=800 chances", "team_season", "TEAM_SEASON", 800),
]


def specification_curve(
    panel: pd.DataFrame, specifications: list | None = None
) -> pd.DataFrame:
    """Re-estimate the overlap effect under every defensible modelling choice.

    Reporting one number here would be a choice about which answer to believe. The estimate
    is comfortably significant pooled and loses significance — and eventually sign — as the
    sample is restricted to lineups that actually played, so the honest output is the range.

    The effect is reported per one standard deviation of overlap, in points per chance, so
    the columns are comparable across rows with different samples.
    """
    rows = []
    for label, fixed_effects, cluster, min_chances in specifications or SPECIFICATIONS:
        subset = panel[panel.CHANCES >= min_chances]
        fit = fit_lineup_overlap(subset, fixed_effects=fixed_effects, cluster=cluster)
        # Regressors are standardised inside the fit, so the coefficient already reads as
        # the effect of one standard deviation.
        overlap = fit["coefficients"].set_index("term").loc["overlap"]
        margin = 1.96 * overlap.std_error
        rows.append(
            {
                "specification": label,
                "n_lineups": fit["n_lineups"],
                "per_1sd": overlap.estimate,
                "ci_low": overlap.estimate - margin,
                "ci_high": overlap.estimate + margin,
                "t": overlap.t,
            }
        )
    return pd.DataFrame(rows)


def head_to_head(panel: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Race the creation-profile measure against the incumbent usage measure.

    The plan's actual scientific claim is not that overlap predicts anything on its own — it
    is that *when* players want the ball carries information that *how much* they want it
    does not. That requires all three fits on identical rows: each measure alone, and both
    together, where a measure that only proxies the other collapses.
    """
    subset = panel.dropna(subset=["OVERLAP", "USAGE_SUM", "PTS_PER_CHANCE", "PRIOR_QUALITY"])
    rows = []
    for label, regressors in [
        ("usage only (incumbent)", ["USAGE_SUM"]),
        ("creation overlap only", ["OVERLAP"]),
        ("both", ["USAGE_SUM", "OVERLAP"]),
    ]:
        fit = fit_lineup_overlap(subset, regressors=regressors, **kwargs)
        coefficients = fit["coefficients"].set_index("term")
        row = {"model": label, "n_lineups": fit["n_lineups"], "r2": fit["r2"]}
        for regressor in ("usage_sum", "overlap"):
            row[regressor] = (
                coefficients.loc[regressor, "estimate"] if regressor in coefficients.index
                else np.nan
            )
            row[f"{regressor}_t"] = (
                coefficients.loc[regressor, "t"] if regressor in coefficients.index else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)
