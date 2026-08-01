"""Retest the creation-overlap hypothesis at five-man lineup level.

`synergy.py` found no relationship between creation overlap and offensive efficiency across
team-seasons. That test had a specific, stated weakness: a team's top creators do not share
the floor for all their minutes, so a real five-on-five effect could average away over a
season and leave no trace.

This module removes that weakness. The unit is a **lineup-season** — one specific five-man
group, in one season — and the outcome is the offense that group actually produced while
together. If usage redundancy costs anything, this is where it has to show up.

Same control discipline as the team-season test: individual quality enters as the summed
prior-season scoring of the five players, so only efficiency unexplained by who they are can
be attributed to how they fit.
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


def build_lineup_panel(
    lineup_efficiency_table: pd.DataFrame,
    profiles_by_season: dict[int, pd.DataFrame],
    prior_quality: pd.DataFrame,
) -> pd.DataFrame:
    """Attach overlap and a prior-quality control to each lineup-season."""
    rows = []
    for record in lineup_efficiency_table.itertuples(index=False):
        profiles = profiles_by_season.get(record.SEASON)
        if profiles is None:
            continue
        ids = [int(p) for p in record.LINEUP_KEY.split("|")]
        profiled = set(profiles.index.get_level_values("PLAYER_ID"))
        if not set(ids).issubset(profiled):
            continue

        quality = prior_quality.reindex(ids).PRIOR_PPA
        if quality.notna().sum() < 4:
            continue

        rows.append(
            {
                "SEASON": record.SEASON,
                "TEAM_ID": record.TEAM_ID,
                "LINEUP_KEY": record.LINEUP_KEY,
                "CHANCES": record.CHANCES,
                "PTS_PER_CHANCE": record.PTS_PER_CHANCE,
                "OVERLAP": lineup_overlap(profiles, ids),
                "PRIOR_QUALITY": float(quality.mean(skipna=True)),
            }
        )
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
    df = panel.dropna(subset=[outcome, "OVERLAP", "PRIOR_QUALITY"]).copy()

    design = [np.ones(len(df)), df.OVERLAP.to_numpy(), df.PRIOR_QUALITY.to_numpy()]
    names = ["intercept", "overlap", "prior_quality"]

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
    reference_sd = float(panel.OVERLAP.std())
    rows = []
    for label, fixed_effects, cluster, min_chances in specifications or SPECIFICATIONS:
        subset = panel[panel.CHANCES >= min_chances]
        fit = fit_lineup_overlap(subset, fixed_effects=fixed_effects, cluster=cluster)
        overlap = fit["coefficients"].set_index("term").loc["overlap"]
        effect = overlap.estimate * reference_sd
        margin = 1.96 * overlap.std_error * reference_sd
        rows.append(
            {
                "specification": label,
                "n_lineups": fit["n_lineups"],
                "per_1sd": effect,
                "ci_low": effect - margin,
                "ci_high": effect + margin,
                "t": overlap.t,
            }
        )
    return pd.DataFrame(rows)
