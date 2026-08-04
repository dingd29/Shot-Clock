"""Does creation overlap actually cost a team anything?

`creation.py` measures whether players want the ball at the same moments. That is
descriptive. This module tests whether it *predicts* offensive efficiency falling below
what the players' individual quality implies — the claim the Sixers projection rests on.

Design of the test:

  unit          one team-season (10 seasons x 30 teams)
  outcome       offensive rating, points per 100 possessions
  treatment     volume-weighted creation overlap among the team's top creators
  control       the same players' *prior-season* scoring quality, volume-weighted

The control is what makes this a test rather than a correlation: good teams have good
players, and good players may cluster in usage. Only the variance in efficiency left after
accounting for individual quality can be attributed to fit. The control uses strictly prior
seasons, so it cannot absorb the outcome it is meant to isolate.

Two limitations, stated rather than buried:
  - Team-season is a coarse unit. Five-man lineup data would be sharper, but deriving
    on-court lineups is a separate build; this test uses only data already reconstructed.
  - Overlap is measured from realised shot distributions, so it partly reflects how a coach
    *used* players, not only how they would want to be used elsewhere.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.models.creation import creation_profiles, lineup_overlap

# Standard possession estimate. The 0.44 coefficient converts free-throw attempts into
# possessions used, accounting for and-1s and technicals that do not end a possession.
FT_POSSESSION_COEF = 0.44


def team_possessions(pbp: pd.DataFrame) -> pd.DataFrame:
    """Possessions and points per team-season from reconstructed play-by-play."""
    df = pbp.dropna(subset=["OFF_TEAM_ID"]).copy()

    made_fg = df[df.EVENTMSGTYPE == 1]
    fga = df[df.EVENTMSGTYPE.isin([1, 2])]
    fta = df[df.EVENTMSGTYPE == 3]
    tov = df[df.EVENTMSGTYPE == 5]
    # One row per off-rebound *chance*, not per event inside one. Every other term here is
    # already event-level (an FGA is one row, a turnover is one row), but CHANCE_START_TYPE is
    # a property of the chance and is repeated on all of its events. Counting rows gave 1,955
    # offensive rebounds per team in 2024-25 against a true 1,144, which subtracted too much
    # from POSS and left possessions at 87.5 per game instead of 97.4.
    orb = df[df.CHANCE_START_TYPE == "off_rebound"].drop_duplicates(["GAME_ID", "CHANCE_ID"])

    def per_team(frame, name):
        return frame.groupby("OFF_TEAM_ID").size().rename(name)

    made_ft = fta[~fta.apply(lambda r: "MISS" in str(r.get("HOMEDESCRIPTION", "")) or
                             "MISS" in str(r.get("VISITORDESCRIPTION", "")), axis=1)]

    table = pd.concat(
        [
            per_team(fga, "FGA"),
            per_team(fta, "FTA"),
            per_team(tov, "TOV"),
            per_team(orb, "ORB"),
            per_team(made_fg, "FGM"),
            per_team(made_ft, "FTM"),
        ],
        axis=1,
    ).fillna(0)

    # Three-pointers need the description, so points come from the scored shot table
    # instead; this frame supplies only the possession denominator.
    table["POSS"] = table.FGA - table.ORB + table.TOV + FT_POSSESSION_COEF * table.FTA
    return table.reset_index().rename(columns={"OFF_TEAM_ID": "TEAM_ID"})


def team_season_panel(
    shots: pd.DataFrame, possessions: pd.DataFrame, top_n: int = 8, min_attempts: int = 150
) -> pd.DataFrame:
    """Assemble the regression panel: efficiency, overlap, and a prior-quality control."""
    rows = []
    for season, season_shots in shots.groupby("SEASON"):
        profiles = creation_profiles(season_shots, min_attempts=min_attempts)
        if profiles.empty:
            continue
        profiled_ids = set(profiles.index.get_level_values("PLAYER_ID"))

        prior = shots[season - 1 == shots.SEASON]
        prior_quality = (
            prior.groupby("PLAYER_ID")
            .apply(
                lambda g: pd.Series(
                    {
                        "PRIOR_PPA": g.PTS.sum() / len(g),
                        "PRIOR_FGA": len(g),
                    }
                ),
                include_groups=False,
            )
            if len(prior)
            else pd.DataFrame(columns=["PRIOR_PPA", "PRIOR_FGA"])
        )

        for team, team_shots in season_shots.groupby("TEAM_ABBREVIATION"):
            usage = team_shots.groupby("PLAYER_ID").size().sort_values(ascending=False)
            core = [p for p in usage.index if p in profiled_ids][:top_n]
            if len(core) < min(top_n, 3):
                continue

            weights = usage.loc[core].to_numpy(dtype=float)
            merged = prior_quality.reindex(core)
            if merged.PRIOR_PPA.notna().sum() < 3:
                continue
            valid = merged.PRIOR_PPA.notna().to_numpy()

            rows.append(
                {
                    "SEASON": season,
                    "TEAM_ABBREVIATION": team,
                    "TEAM_ID": team_shots.TEAM_ID.iloc[0] if "TEAM_ID" in team_shots else np.nan,
                    "OVERLAP": lineup_overlap(profiles, core),
                    "PRIOR_QUALITY": float(
                        np.average(
                            merged.PRIOR_PPA.to_numpy()[valid], weights=weights[valid]
                        )
                    ),
                    "TEAM_FGA": len(team_shots),
                    "TEAM_PTS_FG": team_shots.PTS.sum(),
                    "TEAM_XPTS": team_shots.XPTS.sum(),
                    "N_CORE": len(core),
                }
            )

    panel = pd.DataFrame(rows)
    if panel.empty:
        raise ValueError("empty panel — no team-seasons met the core-size threshold")
    if possessions is not None and not possessions.empty:
        # Join on whichever key both sides actually carry. The scored shot table has the
        # abbreviation but no TEAM_ID, so a TEAM_ID-only join left POSS entirely null and
        # ORTG_FG silently never existed.
        key = (
            "TEAM_ABBREVIATION"
            if "TEAM_ABBREVIATION" in possessions and panel.TEAM_ID.isna().all()
            else "TEAM_ID"
        )
        other = "TEAM_ID" if key == "TEAM_ABBREVIATION" else "TEAM_ABBREVIATION"
        panel = panel.merge(
            possessions.drop(columns=other, errors="ignore"), on=["SEASON", key], how="left"
        )
        panel["ORTG_FG"] = panel.TEAM_PTS_FG / panel.POSS * 100
    panel["PTS_PER_FGA"] = panel.TEAM_PTS_FG / panel.TEAM_FGA
    # How much the team scored relative to the quality of the looks it generated. This is
    # the fit-sensitive residual: shot-making above or below expectation, at team level.
    panel["PTS_VS_XPTS"] = (panel.TEAM_PTS_FG - panel.TEAM_XPTS) / panel.TEAM_FGA
    return panel


def fit_overlap_effect(panel: pd.DataFrame, outcome: str = "PTS_PER_FGA") -> dict:
    """OLS of efficiency on overlap, controlling for prior quality and season fixed effects.

    Season dummies absorb league-wide scoring trends, which rose materially over the
    sample and would otherwise be attributed to whatever else moved with them.
    """
    df = panel.dropna(subset=[outcome, "OVERLAP", "PRIOR_QUALITY"]).copy()
    seasons = sorted(df.SEASON.unique())[1:]  # first season is the reference level

    design = [np.ones(len(df)), df.OVERLAP.to_numpy(), df.PRIOR_QUALITY.to_numpy()]
    names = ["intercept", "overlap", "prior_quality"]
    for season in seasons:
        design.append((season == df.SEASON).to_numpy(dtype=float))
        names.append(f"season_{season}")

    x = np.column_stack(design)
    y = df[outcome].to_numpy()

    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coef
    dof = len(y) - x.shape[1]
    sigma2 = resid @ resid / dof
    cov = sigma2 * np.linalg.pinv(x.T @ x)
    se = np.sqrt(np.diag(cov))

    ss_tot = ((y - y.mean()) ** 2).sum()
    return {
        "n": len(y),
        "outcome": outcome,
        "r2": 1 - (resid @ resid) / ss_tot,
        "coefficients": pd.DataFrame(
            {
                "term": names,
                "estimate": coef,
                "std_error": se,
                "t": coef / se,
            }
        ),
        "overlap_sd": float(df.OVERLAP.std()),
    }
