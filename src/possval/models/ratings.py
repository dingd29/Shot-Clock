"""Game results and team ratings.

Team strength is estimated with a least-squares **Simple Rating System**: every game says
`margin = rating_home - rating_away + home_advantage`, and the whole season is solved at
once. This adjusts for schedule strength, which a raw point differential does not — a team
that played the league's hardest schedule is underrated by its margin alone.

The system is rank-deficient by construction (adding a constant to every rating leaves all
margins unchanged), so ratings are pinned to sum to zero and read as points per game
relative to a league-average opponent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.paths import PROCESSED

# stats.nba.com writes SCORE as "VISITOR - HOME". Verified empirically rather than assumed:
# in game 22400002 a Miami (visiting) basket incremented the first number and a Detroit
# (home) basket the second.
SCORE_IS_VISITOR_FIRST = True


def game_results(season: int) -> pd.DataFrame:
    """Final score, teams, and margin for every game in a season."""
    pbp = pd.read_parquet(
        PROCESSED / f"pbp_clock_{season}.parquet", columns=["GAME_ID", "EVENTNUM", "SCORE"]
    )
    shots = pd.read_parquet(
        PROCESSED / f"shots_clock_{season}.parquet", columns=["GAME_ID", "HTM", "VTM"]
    )

    scored = pbp.dropna(subset=["SCORE"]).sort_values(["GAME_ID", "EVENTNUM"])
    final = scored.groupby("GAME_ID").SCORE.last().str.split("-", expand=True)
    final.columns = ["A", "B"]
    visitor = final.A.astype(str).str.strip().astype(int)
    home = final.B.astype(str).str.strip().astype(int)
    if not SCORE_IS_VISITOR_FIRST:
        visitor, home = home, visitor

    teams = shots.drop_duplicates("GAME_ID").set_index("GAME_ID")[["HTM", "VTM"]]
    games = pd.DataFrame(
        {"HOME_PTS": home, "AWAY_PTS": visitor}
    ).join(teams, how="inner").reset_index()

    games = games.rename(columns={"HTM": "HOME", "VTM": "AWAY"})
    games["MARGIN"] = games.HOME_PTS - games.AWAY_PTS
    games["HOME_WIN"] = (games.MARGIN > 0).astype(int)
    games["SEASON"] = season
    return games[games.MARGIN != 0]  # ties are impossible; a zero margin means a parse failure


def all_game_results(first: int = 2015, last: int = 2024) -> pd.DataFrame:
    frames = []
    for season in range(first, last + 1):
        if (PROCESSED / f"pbp_clock_{season}.parquet").exists():
            frames.append(game_results(season))
    return pd.concat(frames, ignore_index=True)


def srs_ratings(games: pd.DataFrame) -> tuple[pd.Series, float]:
    """Least-squares SRS. Returns (ratings in points per game, fitted home advantage)."""
    teams = sorted(set(games.HOME) | set(games.AWAY))
    index = {team: i for i, team in enumerate(teams)}

    design = np.zeros((len(games), len(teams) + 1))
    design[np.arange(len(games)), games.HOME.map(index).to_numpy()] = 1.0
    design[np.arange(len(games)), games.AWAY.map(index).to_numpy()] = -1.0
    design[:, -1] = 1.0  # home advantage

    # Pin the ratings to sum to zero, otherwise the system is rank-deficient.
    constraint = np.zeros((1, len(teams) + 1))
    constraint[0, : len(teams)] = 1.0

    x = np.vstack([design, constraint])
    y = np.concatenate([games.MARGIN.to_numpy(dtype=float), [0.0]])

    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    return pd.Series(coef[: len(teams)], index=teams).sort_values(ascending=False), float(coef[-1])


def season_ratings(games: pd.DataFrame) -> pd.DataFrame:
    """SRS per team-season, long format."""
    rows = []
    for season, season_games in games.groupby("SEASON"):
        ratings, home_advantage = srs_ratings(season_games)
        for team, rating in ratings.items():
            rows.append(
                {"SEASON": season, "TEAM": team, "SRS": rating, "HOME_ADV": home_advantage}
            )
    return pd.DataFrame(rows)


def backtest_ratings(games: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    """Predict each season's games from the *previous* season's ratings.

    This is the honest test of the rating layer: within-season SRS trivially fits its own
    games. What matters for a projection is whether last year's ratings predict this year's
    results, before any roster modelling is added.
    """
    lookup = ratings.set_index(["SEASON", "TEAM"]).SRS
    rows = []
    for season in sorted(games.SEASON.unique())[1:]:
        current = games[season == games.SEASON].copy()
        current["HOME_RATING"] = [
            lookup.get((season - 1, t), np.nan) for t in current.HOME
        ]
        current["AWAY_RATING"] = [
            lookup.get((season - 1, t), np.nan) for t in current.AWAY
        ]
        rows.append(current.dropna(subset=["HOME_RATING", "AWAY_RATING"]))
    return pd.concat(rows, ignore_index=True)
