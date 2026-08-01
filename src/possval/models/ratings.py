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


def _check_against_score_string(
    pbp: pd.DataFrame,
    home: pd.Series,
    visitor: pd.Series,
    season: int,
    tolerance: int,
    min_agreement: float,
) -> None:
    """Cross-check event-summed finals against the running `SCORE` column.

    The comparison uses the column's *maximum*, not its last value, because scores only ever
    increase — a max is immune to the stale trailing rows that make `.last()` unusable.
    """
    scored = pbp.dropna(subset=["SCORE"]).sort_values(["GAME_ID", "EVENTNUM"])
    parts = scored.SCORE.str.split("-", expand=True)
    sides = scored.assign(
        V=parts[0].str.strip().astype(int), H=parts[1].str.strip().astype(int)
    )
    if not SCORE_IS_VISITOR_FIRST:
        sides = sides.rename(columns={"V": "H", "H": "V"})

    reference = sides.groupby("GAME_ID")[["V", "H"]].max()
    joined = reference.join(home.rename("DH")).join(visitor.rename("DV")).dropna()
    agree = (
        (joined.H - joined.DH).abs().le(tolerance) & (joined.V - joined.DV).abs().le(tolerance)
    ).mean()
    if agree < min_agreement:
        raise ValueError(
            f"{season}: only {agree:.1%} of games have event-summed scores within "
            f"{tolerance} of the SCORE column, below the {min_agreement:.0%} floor"
        )


def game_results(season: int, tolerance: int = 5, min_agreement: float = 0.90) -> pd.DataFrame:
    """Final score, teams, and margin for every game in a season.

    Scores are **summed from scoring events**, not read off the `SCORE` string. The string
    is unreliable: it carries stale rows that leave the last value far from the true final
    (game 22300902 ends "112 - 118" and then logs a spurious "15 - 26"), which cost 4.8% of
    2015-16 games their real result and fed straight into the ratings. Points come from
    `event_points`, and the side is given by which description column is populated — an
    assignment that is never ambiguous, since no scoring event fills both or neither.

    The string is kept as a cross-check: if event-derived and string-derived finals disagree
    by more than `tolerance` on more than `1 - min_agreement` of games, this raises rather
    than silently returning a corrupted season.
    """
    from possval.models.lineup_synergy import event_points

    pbp = pd.read_parquet(
        PROCESSED / f"pbp_clock_{season}.parquet",
        columns=[
            "GAME_ID", "EVENTNUM", "SCORE", "EVENTMSGTYPE",
            "HOMEDESCRIPTION", "VISITORDESCRIPTION",
        ],
    )
    shots = pd.read_parquet(
        PROCESSED / f"shots_clock_{season}.parquet", columns=["GAME_ID", "HTM", "VTM"]
    )

    pbp = pbp.assign(PTS=event_points(pbp))
    scoring = pbp[pbp.PTS > 0]
    home = scoring[scoring.HOMEDESCRIPTION.notna()].groupby("GAME_ID").PTS.sum()
    visitor = scoring[scoring.VISITORDESCRIPTION.notna()].groupby("GAME_ID").PTS.sum()

    _check_against_score_string(pbp, home, visitor, season, tolerance, min_agreement)

    teams = shots.drop_duplicates("GAME_ID").set_index("GAME_ID")[["HTM", "VTM"]]
    games = pd.DataFrame(
        {"HOME_PTS": home, "AWAY_PTS": visitor}
    ).dropna().astype(int).join(teams, how="inner").reset_index()

    games = games.rename(columns={"HTM": "HOME", "VTM": "AWAY"})
    games["MARGIN"] = games.HOME_PTS - games.AWAY_PTS
    games["HOME_WIN"] = (games.MARGIN > 0).astype(int)
    games["SEASON"] = season
    return games[games.MARGIN != 0]  # ties are impossible; a zero margin means a parse failure


def game_results_v3(season: int) -> pd.DataFrame:
    """Final scores from the `nbastatsv3` feed, which covers seasons past `nbastats`.

    v3 is a different schema and a friendlier one for this purpose: it carries `scoreHome`
    and `scoreAway` as separate numeric columns, so there is no "121 - 123" string to parse
    and no ordering convention to verify. Team side is given by `location`, which takes
    values 'h' and 'v' — not 'a'.
    """
    from possval.ingest.bulk import download_archive, read_archive

    df = read_archive(download_archive("nbastatsv3", season))

    scored = df.dropna(subset=["scoreHome", "scoreAway"]).sort_values(
        ["gameId", "actionNumber"]
    )
    final = scored.groupby("gameId")[["scoreHome", "scoreAway"]].last()

    sides = df.dropna(subset=["teamTricode", "location"])
    home = sides[sides.location == "h"].groupby("gameId").teamTricode.first()
    away = sides[sides.location == "v"].groupby("gameId").teamTricode.first()

    games = (
        final.join(home.rename("HOME"), how="inner")
        .join(away.rename("AWAY"), how="inner")
        .reset_index()
        .rename(columns={"gameId": "GAME_ID", "scoreHome": "HOME_PTS", "scoreAway": "AWAY_PTS"})
    )
    games["MARGIN"] = games.HOME_PTS - games.AWAY_PTS
    games["HOME_WIN"] = (games.MARGIN > 0).astype(int)
    games["SEASON"] = season
    return games[games.MARGIN != 0]


def all_game_results(first: int = 2015, last: int = 2025) -> pd.DataFrame:
    """Stack every season, using whichever feed covers it.

    `nbastats` stops at 2024-25, so later seasons come from `nbastatsv3`.
    """
    frames = []
    for season in range(first, last + 1):
        if (PROCESSED / f"pbp_clock_{season}.parquet").exists():
            frames.append(game_results(season))
        else:
            try:
                frames.append(game_results_v3(season))
            except Exception as exc:  # a missing season should not kill the stack
                print(f"  skipped {season}: {type(exc).__name__}: {exc}")
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
