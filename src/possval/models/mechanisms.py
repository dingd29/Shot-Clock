"""Exploratory mechanisms behind team continuation-value profiles.

These functions turn the descriptive team signal into questions about NBA reality.  None treats
the continuation curve as the counterfactual for a particular possession.  The outputs separate
context, player continuity, game state, and short-run sequencing so those stories do not get
collapsed into a single claim about decision quality.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from possval.models.team_profiles import score_against_team_curve
from possval.models.value import shot_value, team_curves


def game_state_profiles(scored: pd.DataFrame, min_shots: int = 100) -> pd.DataFrame:
    """Exposure and timing by offense-relative margin and game phase."""
    frame = scored.dropna(subset=["SCORE_MARGIN", "PERIOD", "IS_HOME"]).copy()
    frame["OFFENSE_MARGIN"] = np.where(
        frame.IS_HOME.eq(1), frame.SCORE_MARGIN, -frame.SCORE_MARGIN
    )
    frame["SCORE_STATE"] = pd.cut(
        frame.OFFENSE_MARGIN,
        [-np.inf, -10, -4, 3, 9, np.inf],
        labels=["trailing 10+", "trailing 4–9", "within 3", "leading 4–9", "leading 10+"],
    )
    frame["GAME_PHASE"] = np.select(
        [frame.PERIOD.le(3), frame.PERIOD.eq(4)],
        ["quarters 1–3", "fourth quarter"],
        default="overtime",
    )
    keys = ["GAME_PHASE", "SCORE_STATE"]
    league = (
        frame.groupby(keys, observed=True)
        .agg(
            LEAGUE_N=("EXPOSURE", "size"),
            LEAGUE_EXPOSURE=("EXPOSURE", "mean"),
            LEAGUE_CLOCK=("SECOND", "mean"),
        )
        .reset_index()
    )
    table = (
        frame.groupby(["TEAM_ABBREVIATION", *keys], observed=True)
        .agg(
            N_SHOTS=("EXPOSURE", "size"),
            PREMATURE=("BELOW", "mean"),
            EXPOSURE_PER_SHOT=("EXPOSURE", "mean"),
            MEAN_SECOND=("SECOND", "mean"),
            MEAN_SHOT_VALUE=("SHOT_VALUE", "mean"),
        )
        .reset_index()
        .merge(league, on=keys, how="left", validate="many_to_one")
    )
    table["EXPOSURE_VS_LEAGUE_STATE"] = table.EXPOSURE_PER_SHOT - table.LEAGUE_EXPOSURE
    table["CLOCK_VS_LEAGUE_STATE"] = table.MEAN_SECOND - table.LEAGUE_CLOCK
    return table[table.N_SHOTS >= min_shots]


def season_profiles(
    chained: pd.DataFrame,
    shots: pd.DataFrame,
    outcomes: pd.DataFrame,
    first: int = 2015,
    last: int = 2023,
    min_player_shots: int = 150,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build season-specific team and player exposure with contemporaneous curves."""
    team_rows: list[pd.DataFrame] = []
    player_rows: list[pd.DataFrame] = []
    for season in range(first, last + 1):
        season_panel = chained[chained.SEASON.eq(season)]
        second_chance = float(
            season_panel.loc[season_panel.START_TYPE.eq("off_rebound"), "PTS_POSS"].mean()
        )
        season_shots = shots[shots.SEASON.eq(season) & shots.GAME_CLOCK_EXPIRING.eq(0)]
        valued = shot_value(
            season_shots,
            outcomes[outcomes.SEASON.eq(season)],
            second_chance,
        )
        curves = team_curves(
            season_panel,
            min_chances=50,
            min_possessions=1_500,
        )
        scored = score_against_team_curve(valued, curves)
        teams = (
            scored.groupby("TEAM_ABBREVIATION")
            .agg(
                N_SHOTS=("EXPOSURE", "size"),
                EXPOSURE_PER_SHOT=("EXPOSURE", "mean"),
                PREMATURE=("BELOW", "mean"),
                MEAN_SECOND=("SECOND", "mean"),
            )
            .reset_index()
        )
        teams["SEASON"] = season
        team_rows.append(teams)

        players = (
            scored.groupby(["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"])
            .agg(
                N_SHOTS=("EXPOSURE", "size"),
                EXPOSURE_PER_SHOT=("EXPOSURE", "mean"),
                PREMATURE=("BELOW", "mean"),
                MEAN_SECOND=("SECOND", "mean"),
            )
            .reset_index()
        )
        players = players[players.N_SHOTS >= min_player_shots]
        players["SEASON"] = season
        player_rows.append(players)
    return pd.concat(team_rows, ignore_index=True), pd.concat(player_rows, ignore_index=True)


def mover_pairs(
    team_seasons: pd.DataFrame,
    player_seasons: pd.DataFrame,
) -> pd.DataFrame:
    """Adjacent-season team changers, using each player's largest team sample each year."""
    primary = (
        player_seasons.sort_values("N_SHOTS")
        .drop_duplicates(["PLAYER_ID", "SEASON"], keep="last")
        .merge(
            team_seasons[["TEAM_ABBREVIATION", "SEASON", "EXPOSURE_PER_SHOT"]].rename(
                columns={"EXPOSURE_PER_SHOT": "TEAM_EXPOSURE"}
            ),
            on=["TEAM_ABBREVIATION", "SEASON"],
            how="left",
            validate="many_to_one",
        )
    )
    primary["RELATIVE_TO_TEAM"] = primary.EXPOSURE_PER_SHOT - primary.TEAM_EXPOSURE
    pairs = primary.merge(primary, on="PLAYER_ID", suffixes=("_FROM", "_TO"))
    pairs = pairs[
        pairs.SEASON_TO.eq(pairs.SEASON_FROM + 1)
        & pairs.TEAM_ABBREVIATION_FROM.ne(pairs.TEAM_ABBREVIATION_TO)
    ].copy()
    pairs["PLAYER_EXPOSURE_CHANGE"] = (
        pairs.EXPOSURE_PER_SHOT_TO - pairs.EXPOSURE_PER_SHOT_FROM
    )
    pairs["TEAM_EXPOSURE_CHANGE"] = pairs.TEAM_EXPOSURE_TO - pairs.TEAM_EXPOSURE_FROM
    return pairs.sort_values(["SEASON_FROM", "PLAYER_NAME_FROM"])


def persistence_summary(
    team_seasons: pd.DataFrame,
    movers: pd.DataFrame,
) -> pd.DataFrame:
    """Three correlations that distinguish franchise, player, and environment persistence."""
    teams = team_seasons.sort_values(["TEAM_ABBREVIATION", "SEASON"]).copy()
    teams["NEXT_EXPOSURE"] = teams.groupby("TEAM_ABBREVIATION").EXPOSURE_PER_SHOT.shift(-1)
    teams["NEXT_SEASON"] = teams.groupby("TEAM_ABBREVIATION").SEASON.shift(-1)
    adjacent = teams[teams.NEXT_SEASON.eq(teams.SEASON + 1)]

    def row(label: str, x: pd.Series, y: pd.Series) -> dict[str, float | int | str]:
        pearson, pearson_p = stats.pearsonr(x, y)
        spearman, spearman_p = stats.spearmanr(x, y)
        return {
            "COMPARISON": label,
            "N": len(x),
            "PEARSON": pearson,
            "PEARSON_P": pearson_p,
            "SPEARMAN": spearman,
            "SPEARMAN_P": spearman_p,
        }

    return pd.DataFrame(
        [
            row(
                "same franchise, adjacent seasons",
                adjacent.EXPOSURE_PER_SHOT,
                adjacent.NEXT_EXPOSURE,
            ),
            row(
                "mover relative-to-team persistence",
                movers.RELATIVE_TO_TEAM_FROM,
                movers.RELATIVE_TO_TEAM_TO,
            ),
            row(
                "mover change vs team-environment change",
                movers.PLAYER_EXPOSURE_CHANGE,
                movers.TEAM_EXPOSURE_CHANGE,
            ),
        ]
    )


def possession_sequence_profiles(
    chained: pd.DataFrame,
    shots: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """How the first shot of a possession changes after the team's previous result.

    Residuals remove team × current start type × period averages.  This controls broad context,
    but not lineups, opponent behavior, or play calls; it is a test of short-memory magnitude,
    not a causal momentum estimate.
    """
    mapping = chained[["GAME_ID", "PERIOD", "CHANCE_ID", "POSSESSION_ID", "TEAM"]]
    attached = shots.merge(mapping, on=["GAME_ID", "PERIOD", "CHANCE_ID"], how="inner")
    first_shot = (
        attached.sort_values(["GAME_ID", "PERIOD", "POSSESSION_ID", "GAME_EVENT_ID"])
        .drop_duplicates(["GAME_ID", "PERIOD", "POSSESSION_ID"])
        [["GAME_ID", "PERIOD", "POSSESSION_ID", "SHOT_CLOCK", "XPTS"]]
    )
    possessions = (
        chained.sort_values(["GAME_ID", "PERIOD", "POSSESSION_ID", "CHANCE_ID"])
        .groupby(["GAME_ID", "PERIOD", "POSSESSION_ID"], sort=False)
        .first()
        .reset_index()
        [["GAME_ID", "PERIOD", "POSSESSION_ID", "TEAM", "PTS_POSS", "FGA", "START_TYPE"]]
        .merge(first_shot, on=["GAME_ID", "PERIOD", "POSSESSION_ID"], how="left")
        .sort_values(["TEAM", "GAME_ID", "PERIOD", "POSSESSION_ID"])
    )
    for column in ("PTS_POSS", "FGA"):
        possessions[f"PREV_{column}"] = possessions.groupby(
            ["TEAM", "GAME_ID", "PERIOD"]
        )[column].shift()
    possessions["PREVIOUS_RESULT"] = np.select(
        [
            possessions.PREV_PTS_POSS.eq(0) & possessions.PREV_FGA.eq(0),
            possessions.PREV_PTS_POSS.eq(0) & possessions.PREV_FGA.gt(0),
            possessions.PREV_PTS_POSS.ge(2),
        ],
        ["turnover / no FGA", "empty shooting possession", "scored 2+"],
        default="other",
    )
    frame = possessions[
        possessions.PREVIOUS_RESULT.ne("other") & possessions.SHOT_CLOCK.notna()
    ].copy()
    cells = ["TEAM", "START_TYPE", "PERIOD"]
    frame["CLOCK_RESIDUAL"] = frame.SHOT_CLOCK - frame.groupby(cells).SHOT_CLOCK.transform(
        "mean"
    )
    frame["XPTS_RESIDUAL"] = frame.XPTS - frame.groupby(cells).XPTS.transform("mean")
    league = (
        frame.groupby("PREVIOUS_RESULT")
        .agg(
            N=("SHOT_CLOCK", "size"),
            MEAN_SHOT_CLOCK=("SHOT_CLOCK", "mean"),
            CLOCK_RESIDUAL=("CLOCK_RESIDUAL", "mean"),
            MEAN_XPTS=("XPTS", "mean"),
            XPTS_RESIDUAL=("XPTS_RESIDUAL", "mean"),
        )
        .reset_index()
    )
    teams = (
        frame.groupby(["TEAM", "PREVIOUS_RESULT"])
        .agg(
            N=("SHOT_CLOCK", "size"),
            MEAN_SHOT_CLOCK=("SHOT_CLOCK", "mean"),
            CLOCK_RESIDUAL=("CLOCK_RESIDUAL", "mean"),
            MEAN_XPTS=("XPTS", "mean"),
            XPTS_RESIDUAL=("XPTS_RESIDUAL", "mean"),
        )
        .reset_index()
    )
    return league, teams
