"""Calibrating DPM-implied team ratings against observed ones.

The textbook identity says a team's rating is the minutes-weighted sum of its players' DPM,
since five on-court slots supply 240 player-minutes per game. That's theoretical. 2025-26 is
the one season where both halves exist to check it: observed ratings from `nbastatsv3`, and a
DARKO snapshot covering the players who produced them.

The snapshot postdates the season it's scored against, so the fitted slope is the right
correction to apply but the fit statistics are optimistic and the residual is a lower bound on
forward error. n = 30 teams, one season. Not out-of-sample validation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.paths import PROCESSED, REFERENCE

# Players outside DARKO's 530 are the league's fringe — 1.6% of minutes in 2025-26. They are
# assigned a replacement level rather than dropped, because dropping them shrinks the minutes
# denominator and quietly inflates every team's rating. The fit is near-insensitive to the
# value: slope moves 1.39 to 1.45 across a -4.0 to -1.0 sweep.
REPLACEMENT_DPM = -2.0

LINEUP_SIZE = 5


def load_minutes(season: int = 2025) -> pd.DataFrame:
    """Season minutes per player, from the box score rather than derived from substitutions.

    The `nbastatsv3` feed logs substitutions but not on-court state, so minutes would have to
    be reconstructed by walking each period — the same job `nba_on_court` does for the legacy
    schema, and not worth reimplementing when the box score reports them directly.
    """
    path = REFERENCE / f"minutes_{season}_{str(season + 1)[-2:]}.csv"
    if path.exists():
        return pd.read_csv(path)

    from nba_api.stats.endpoints import leaguedashplayerstats

    frame = leaguedashplayerstats.LeagueDashPlayerStats(
        season=f"{season}-{str(season + 1)[-2:]}",
        season_type_all_star="Regular Season",
        timeout=60,
    ).get_data_frames()[0]
    frame = frame[["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GP", "MIN"]]
    frame.to_csv(path, index=False)
    return frame


def team_dpm(
    minutes: pd.DataFrame, darko: pd.DataFrame, replacement: float = REPLACEMENT_DPM
) -> pd.DataFrame:
    """Minutes-weighted DPM per team, on the raw theoretical scale (5 x mean DPM)."""
    merged = minutes.merge(
        darko[["PLAYER_ID", "DPM", "O_DPM", "D_DPM"]], on="PLAYER_ID", how="left"
    )
    for column in ("DPM", "O_DPM", "D_DPM"):
        merged[column] = merged[column].fillna(replacement)

    return merged.groupby("TEAM_ABBREVIATION").apply(
        lambda team: pd.Series(
            {
                "PRED": np.average(team.DPM, weights=team.MIN) * LINEUP_SIZE,
                "PRED_OFF": np.average(team.O_DPM, weights=team.MIN) * LINEUP_SIZE,
                "PRED_DEF": np.average(team.D_DPM, weights=team.MIN) * LINEUP_SIZE,
                "MINUTES_COVERED": float(
                    team.loc[team.DPM != replacement, "MIN"].sum() / team.MIN.sum()
                ),
            }
        ),
        include_groups=False,
    )


def observed_splits(season: int = 2025) -> pd.DataFrame:
    """Points scored and allowed per game, relative to the league, per team.

    Defence is signed so that positive is good, matching DPM's convention.

    **These are diagnostic only and must not be used as calibration targets.** Both are
    per-game and unadjusted for pace, so a fast team looks better on offence and worse on
    defence for reasons that cancel in its net rating. Fitting offence and defence against
    them separately produces slopes of 0.90 and 1.78 and the false conclusion that DARKO
    compresses defensive spread twice as hard as offensive — an artifact of the targets, not
    a property of DPM. Against a common target the two slopes are 1.47 and 1.31 and cannot
    be told apart (see `slopes_differ`).
    """
    from possval.models.ratings import game_results_v3

    games = game_results_v3(season)
    home = games.groupby("HOME").agg(
        PF=("HOME_PTS", "sum"), PA=("AWAY_PTS", "sum"), N=("HOME_PTS", "size")
    )
    away = games.groupby("AWAY").agg(
        PF=("AWAY_PTS", "sum"), PA=("HOME_PTS", "sum"), N=("AWAY_PTS", "size")
    )
    totals = home.add(away, fill_value=0)

    scored, allowed = totals.PF / totals.N, totals.PA / totals.N
    return pd.DataFrame(
        {"OFF_REL": scored - scored.mean(), "DEF_REL": allowed.mean() - allowed}
    )


def _fit_line(x: np.ndarray, y: np.ndarray) -> dict:
    """Least-squares line with a standard error on the slope.

    The slope is the quantity of interest and n is 30, so quoting it without an interval
    would invite exactly the false precision this module exists to remove.
    """
    design = np.column_stack([np.ones(len(x)), x])
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ coefficients
    dof = len(y) - 2
    covariance = (residual @ residual / dof) * np.linalg.pinv(design.T @ design)
    errors = np.sqrt(np.diag(covariance))
    return {
        "intercept": float(coefficients[0]),
        "slope": float(coefficients[1]),
        "slope_se": float(errors[1]),
        "r": float(np.corrcoef(x, y)[0, 1]),
        "residual_sd": float(residual.std(ddof=2)),
        "predicted_sd": float(x.std()),
        "observed_sd": float(y.std()),
    }


def calibration_panel(season: int = 2025, replacement: float = REPLACEMENT_DPM) -> pd.DataFrame:
    """DPM-implied ratings and observed ones, one row per team."""
    darko = pd.read_csv(REFERENCE / "darko_2026_07.csv")
    predicted = team_dpm(load_minutes(season), darko, replacement)

    ratings = pd.read_parquet(PROCESSED / "srs_ratings.parquet")
    srs = ratings[ratings.SEASON == season].set_index("TEAM").SRS
    return predicted.join(srs.rename("SRS")).join(observed_splits(season)).dropna()


def slopes_differ(panel: pd.DataFrame) -> dict:
    """Test whether offence and defence need separate slopes onto the same target.

    They plausibly could: if DARKO shrinks defensive impact harder than offensive — which is
    the usual story, defence being harder to measure — then an offence-heavy roster like
    Philadelphia's would be systematically misvalued by one blended slope. Worth testing
    rather than assuming, in either direction.
    """
    y = panel.SRS.to_numpy()
    ones = np.ones(len(y))
    restricted = np.column_stack([ones, panel.PRED.to_numpy()])
    full = np.column_stack([ones, panel.PRED_OFF.to_numpy(), panel.PRED_DEF.to_numpy()])

    def rss(design):
        coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
        return float(((y - design @ coefficients) ** 2).sum()), coefficients

    rss_restricted, _ = rss(restricted)
    rss_full, coefficients = rss(full)
    dof = len(y) - full.shape[1]
    f_statistic = ((rss_restricted - rss_full) / 1) / (rss_full / dof)

    from scipy import stats

    return {
        "offence_slope": float(coefficients[1]),
        "defence_slope": float(coefficients[2]),
        "f": float(f_statistic),
        "p": float(1 - stats.f.cdf(f_statistic, 1, dof)),
    }


def calibrate(season: int = 2025, replacement: float = REPLACEMENT_DPM) -> pd.DataFrame:
    """Fit observed ratings on DPM-implied ones.

    The headline row is the only one that should be applied. The two component rows are
    reported because they are the natural thing to try and they are *wrong* — see
    `observed_splits` — and leaving them out would hide why the single slope is used.
    """
    panel = calibration_panel(season, replacement)
    rows = []
    for name, source, target in [
        ("overall (vs SRS)", "PRED", "SRS"),
        ("offence (vs pts scored, diagnostic)", "PRED_OFF", "OFF_REL"),
        ("defence (vs pts allowed, diagnostic)", "PRED_DEF", "DEF_REL"),
    ]:
        fit = _fit_line(panel[source].to_numpy(), panel[target].to_numpy())
        rows.append({"component": name, "n": len(panel), **fit})
    return pd.DataFrame(rows)


def apply_calibration(raw_rating: float, fits: pd.DataFrame) -> dict:
    """Map a raw DPM-implied team rating onto the observed scale.

    One slope, applied to the total. Calibrating offence and defence separately and adding
    them would have put Philadelphia at +2.80 rather than +5.11 — a 2.3-point error driven
    entirely by the pace contamination in the component targets, and one that bites hardest
    on exactly the offence-heavy rosters this project exists to evaluate.
    """
    overall = fits.set_index("component").loc["overall (vs SRS)"]
    return {
        "rating": float(overall.intercept + overall.slope * raw_rating),
        "slope": float(overall.slope),
        "residual_sd": float(overall.residual_sd),
    }
