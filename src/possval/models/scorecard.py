"""Scoring the pre-registered 2026-27 projection against results as they land.

`PREREGISTRATION.md` commits to a number before the season and promises to score it honestly
afterwards. This is the machinery that keeps the second half of that promise, and it exists
*before* opening night on purpose: a scoring rule written after seeing results is not a
scoring rule, it is a choice of the flattering one.

**What is scored, and against what.** Every completed game gets a win probability from the
frozen pre-registration ratings, and that prediction is graded by Brier score and log loss
against two baselines:

``home team always``   the trivial rule — 56.5% of NBA games are home wins. Beating this is
                       the minimum bar for the projection to have said anything at all.
``prior-season SRS``   last season's ratings, the honest naive alternative. This is the
                       baseline that matters: the projection layer only earns its keep if
                       modelling rosters beats simply carrying last year's team strength
                       forward.

**What is not scored.** The title probability. One championship is one observation, and 2.1%
is neither refuted by Philadelphia winning nor confirmed by their losing. Scoring it would be
theatre. The game-level numbers are the real test, which is why there are ~1,230 of them.

The predictions are frozen at import from the committed projection, never recomputed from
current data — the whole point is that they cannot move.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.paths import PROCESSED, REPORTS

# The season being scored, and the one whose ratings form the naive baseline.
SEASON = 2026
PRIOR_SEASON = 2025

# League-wide home win rate over 2015-2025, used as the trivial baseline.
BASE_HOME_WIN_RATE = 0.5649


def frozen_projection() -> pd.Series:
    """The pre-registered ratings, read from the committed projection.

    Deliberately loaded from `reports/league_projection_2026_27.csv` rather than recomputed.
    Regenerating them at scoring time would silently let a later model version grade itself,
    which is the exact failure the pre-registration exists to rule out. If the file is missing
    the answer is to check out the `projection-2026-27` tag, not to rebuild it.
    """
    path = REPORTS / "league_projection_2026_27.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. It is the pre-registered prediction and must not be "
            "regenerated to score itself — recover it from the projection-2026-27 tag."
        )
    return pd.read_csv(path, index_col=0).RATING


def prior_season_ratings(season: int = PRIOR_SEASON) -> pd.Series:
    """Last season's SRS — the naive baseline the projection has to beat."""
    ratings = pd.read_parquet(PROCESSED / "srs_ratings.parquet")
    return ratings[ratings.SEASON == season].set_index("TEAM").SRS


def completed_games(season: int = SEASON) -> pd.DataFrame:
    """Every finished game of the season so far, from whichever feed covers it.

    Returns an empty frame rather than raising when the season has not started, so the
    harness can be wired up and run before there is anything to score.
    """
    from possval.models.ratings import game_results, game_results_v3

    if (PROCESSED / f"pbp_clock_{season}.parquet").exists():
        return game_results(season)
    try:
        return game_results_v3(season)
    except Exception:
        return pd.DataFrame(columns=["GAME_ID", "HOME", "AWAY", "MARGIN", "HOME_WIN", "SEASON"])


def _metrics(probabilities: np.ndarray, outcomes: np.ndarray) -> dict:
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    return {
        "brier": float(np.mean((clipped - outcomes) ** 2)),
        "log_loss": float(
            -np.mean(outcomes * np.log(clipped) + (1 - outcomes) * np.log(1 - clipped))
        ),
    }


def score_games(games: pd.DataFrame, ratings: pd.Series, baseline: pd.Series) -> pd.DataFrame:
    """Grade the projection and both baselines on every completed game."""
    from possval.models.simulate import win_probability

    if games.empty:
        return pd.DataFrame(columns=["model", "n_games", "brier", "log_loss"])

    known = games[games.HOME.isin(ratings.index) & games.AWAY.isin(ratings.index)].copy()
    outcomes = known.HOME_WIN.to_numpy(dtype=float)

    projected = win_probability(
        known.HOME.map(ratings).to_numpy() - known.AWAY.map(ratings).to_numpy(), True
    )
    naive = win_probability(
        known.HOME.map(baseline).fillna(0.0).to_numpy()
        - known.AWAY.map(baseline).fillna(0.0).to_numpy(),
        True,
    )
    trivial = np.full(len(known), BASE_HOME_WIN_RATE)

    rows = []
    for name, probabilities in [
        ("pre-registered projection", projected),
        ("prior-season SRS", naive),
        ("home team always", trivial),
    ]:
        rows.append({"model": name, "n_games": len(known), **_metrics(probabilities, outcomes)})
    return pd.DataFrame(rows)


def calibration(games: pd.DataFrame, ratings: pd.Series, bins: int = 10) -> pd.DataFrame:
    """Predicted win probability against realised win rate, in buckets.

    A model can beat a baseline on Brier while being badly calibrated, which for a projection
    quoted with intervals matters as much as the score does.
    """
    from possval.models.simulate import win_probability

    if games.empty:
        return pd.DataFrame(columns=["bucket", "n", "predicted", "actual"])

    known = games[games.HOME.isin(ratings.index) & games.AWAY.isin(ratings.index)].copy()
    known["P"] = win_probability(
        known.HOME.map(ratings).to_numpy() - known.AWAY.map(ratings).to_numpy(), True
    )
    known["BUCKET"] = pd.cut(known.P, np.linspace(0, 1, bins + 1), include_lowest=True)
    grouped = known.groupby("BUCKET", observed=True).agg(
        n=("P", "size"), predicted=("P", "mean"), actual=("HOME_WIN", "mean")
    )
    return grouped.reset_index()


def win_total_error(games: pd.DataFrame, projection: pd.DataFrame) -> pd.DataFrame:
    """Projected wins against the pace each team is actually on.

    Extrapolating a partial season to 82 games is noisy early and is labelled as such; the
    column is there so the running record is visible, not so it can be read as a verdict in
    November.
    """
    if games.empty:
        return pd.DataFrame(columns=["TEAM", "played", "wins", "pace_82", "projected", "error"])

    home = games.groupby("HOME").HOME_WIN.agg(["sum", "size"])
    away = games.groupby("AWAY").HOME_WIN.agg(lambda s: (1 - s).sum()).rename("sum").to_frame()
    away["size"] = games.groupby("AWAY").HOME_WIN.size()
    totals = home.add(away, fill_value=0)

    out = pd.DataFrame(
        {
            "played": totals["size"].astype(int),
            "wins": totals["sum"].astype(int),
            "projected": projection.WINS,
        }
    ).dropna()
    out["pace_82"] = out.wins / out.played * 82
    out["error"] = out.pace_82 - out.projected
    return out.reset_index(names="TEAM").sort_values("error")


def scorecard(season: int = SEASON) -> dict:
    """The whole running record: game-level scores, calibration, and win-total pace."""
    ratings = frozen_projection()
    projection = pd.read_csv(REPORTS / "league_projection_2026_27.csv", index_col=0)
    games = completed_games(season)

    return {
        "n_games": len(games),
        "scores": score_games(games, ratings, prior_season_ratings()),
        "calibration": calibration(games, ratings),
        "win_totals": win_total_error(games, projection),
    }
