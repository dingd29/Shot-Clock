"""A full-league 2026-27 baseline, and the Philadelphia projection built on it.

Title odds are not a property of one team. Philadelphia's championship probability depends
entirely on who else is good, so the only way to quote one is to project all thirty rosters
and simulate the league.

**Construction.** Each team starts from the minutes its players actually played in 2025-26,
valued at current DARKO, then calibrated onto the observed rating scale by
`dpm_calibration`. Transactions are applied by moving players between teams and letting the
minutes follow them.

**The assumption this rests on, stated plainly.** Only the Philadelphia trade is modelled.
Every other roster is frozen at its 2025-26 shape, so an offseason that reshapes a rival
is invisible here. That biases *against* nobody in particular but adds real error to every
team's number, Philadelphia's included — and it means these odds are a snapshot of a league
that will not exist by opening night, not a forecast of the one that will.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.models.dpm_calibration import (
    REPLACEMENT_DPM,
    apply_calibration,
    calibrate,
    load_minutes,
)
from possval.paths import PROCESSED, REFERENCE

# The 2026 offseason move that motivates the project: Philadelphia acquires LeBron James and
# Jaylen Brown, sending Paul George to Boston. Minutes travel with each player.
TRANSACTIONS_2026 = [
    ("LeBron James", "PHI"),
    ("Jaylen Brown", "PHI"),
    ("Paul George", "BOS"),
]

PHILADELPHIA = "PHI"

# Conference membership decides who Philadelphia has to get past, and it is not incidental:
# the three strongest teams in this projection are split across the two, so a bracket that
# ignores conferences can eliminate two of them against each other in a round that could
# never happen — and quietly inflates the survivor's odds.
EAST = [
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND",
    "MIA", "MIL", "NYK", "ORL", "PHI", "TOR", "WAS",
]
WEST = [
    "DAL", "DEN", "GSW", "HOU", "LAC", "LAL", "MEM", "MIN",
    "NOP", "OKC", "PHX", "POR", "SAC", "SAS", "UTA",
]
CONFERENCES = {team: "East" for team in EAST} | {team: "West" for team in WEST}

# Divisions drive the real schedule: a team plays its four division rivals four times each.
DIVISIONS = {
    "Atlantic": ["BOS", "BKN", "NYK", "PHI", "TOR"],
    "Central": ["CHI", "CLE", "DET", "IND", "MIL"],
    "Southeast": ["ATL", "CHA", "MIA", "ORL", "WAS"],
    "Northwest": ["DEN", "MIN", "OKC", "POR", "UTA"],
    "Pacific": ["GSW", "LAC", "LAL", "PHX", "SAC"],
    "Southwest": ["DAL", "HOU", "MEM", "NOP", "SAS"],
}
DIVISION_OF = {team: name for name, teams in DIVISIONS.items() for team in teams}


TEAM_MINUTES_PER_GAME = 240.0
GAMES = 82


def apply_transactions(
    minutes: pd.DataFrame, moves: list[tuple[str, str]] | None = None
) -> pd.DataFrame:
    """Reassign players to new teams, carrying their minutes with them."""
    updated = minutes.copy()
    for player, destination in moves if moves is not None else TRANSACTIONS_2026:
        matched = updated.PLAYER_NAME == player
        if not matched.any():
            raise KeyError(f"{player} is not in the minutes table; cannot move them")
        updated.loc[matched, "TEAM_ABBREVIATION"] = destination
    return updated


def rebalance_minutes(minutes: pd.DataFrame) -> pd.DataFrame:
    """Fit each team's roster back inside the 240 minutes a game actually provides.

    Acquiring a star does not create playing time — it takes it from whoever was playing.
    Without this step Philadelphia keeps every 2025-26 rotation minute *and* adds LeBron's
    1,989 and Brown's 2,443 on top, so the two stars are averaged against a bench that in
    reality would barely play. That diluted the projection to +0.71 when the same roster
    under an explicit ten-man rotation is worth +5.1.

    Incoming players are seated by their own minutes, and the squeeze falls on the end of the
    bench: everyone is ranked by minutes and the roster is trimmed from the bottom until it
    fits. That is what happens to a team that signs two stars.
    """
    capacity = TEAM_MINUTES_PER_GAME * GAMES
    kept = []
    for _, team in minutes.groupby("TEAM_ABBREVIATION", sort=False):
        ordered = team.sort_values("MIN", ascending=False).copy()
        cumulative = ordered.MIN.cumsum()
        inside = cumulative <= capacity
        # Keep the player who straddles the cap, trimmed to whatever room is left.
        if (~inside).any():
            straddler = (~inside).idxmax()
            room = capacity - cumulative.shift(fill_value=0.0).loc[straddler]
            ordered.loc[straddler, "MIN"] = max(room, 0.0)
            inside.loc[straddler] = True
            inside.loc[cumulative.index[cumulative.index.get_indexer([straddler])[0] + 1 :]] = (
                False
            )
        kept.append(ordered[inside])
    return pd.concat(kept, ignore_index=True)


def project_games(minutes: pd.DataFrame, games: int | None) -> pd.DataFrame:
    """Re-express minutes as a rate times a projected games-played total.

    Last season's minutes carry last season's injuries. Philadelphia is the sharpest case in
    the league: Embiid played 38 games, so leaving his total untouched projects him as the
    tenth-most-used player on his own team and quietly assumes he misses half of 2026-27
    again. Availability is the single largest variance term on this roster, and burying it
    inside a minutes column disguises an assumption as data.

    `games=None` keeps minutes exactly as played. A number re-rates every player to that
    many games at his own per-game rate, capped at his observed rate so this can only undo
    missed time, never invent a bigger role than a player has ever held.
    """
    if games is None:
        return minutes
    projected = minutes.copy()
    per_game = projected.MIN / projected.GP.clip(lower=1)
    projected["MIN"] = per_game * np.minimum(games, projected.GP.clip(lower=1).max())
    return projected


def load_darko() -> pd.DataFrame:
    return pd.read_csv(REFERENCE / "darko_2026_07.csv")


def age_player(darko: pd.DataFrame, player: str, decline: float) -> pd.DataFrame:
    """Return a copy of DARKO with one player's impact reduced by `decline`."""
    aged = darko.copy()
    matched = aged.PLAYER_NAME == player
    if not matched.any():
        raise KeyError(f"{player} is not in DARKO")
    aged.loc[matched, "DPM"] -= decline
    return aged


def league_ratings(
    moves: list[tuple[str, str]] | None = None,
    replacement: float = REPLACEMENT_DPM,
    games: int | None = None,
    darko: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Calibrated 2026-27 rating for every team."""
    darko = load_darko() if darko is None else darko
    minutes = project_games(load_minutes(2025), games)
    minutes = rebalance_minutes(apply_transactions(minutes, moves))

    merged = minutes.merge(darko[["PLAYER_ID", "DPM"]], on="PLAYER_ID", how="left")
    merged["DPM"] = merged.DPM.fillna(replacement)

    raw = merged.groupby("TEAM_ABBREVIATION").apply(
        lambda team: np.average(team.DPM, weights=team.MIN) * 5, include_groups=False
    )

    fits = calibrate()
    calibrated = {team: apply_calibration(value, fits)["rating"] for team, value in raw.items()}
    frame = pd.DataFrame({"RAW": raw, "RATING": pd.Series(calibrated)})

    # Ratings are relative to a league-average opponent, so they must sum to zero. The fitted
    # intercept gets this nearly right on its own; the residual is the transactions moving
    # value between teams, and is removed rather than left to bias every game simulated.
    frame["RATING"] = frame.RATING - frame.RATING.mean()
    return frame.sort_values("RATING", ascending=False)


def forward_rating_sd() -> float:
    """How far a team's rating typically moves in one year, from ten seasons of SRS.

    This is the honest scale of a *forward* projection's error, and it is roughly double the
    calibration residual. Fitting next season's rating on this season's over 2015-2025 gives
    a correlation of 0.57 and a residual spread of 3.95 points — the amount by which rosters,
    health, and development move a team in a year, none of which a roster snapshot sees.

    Using the calibration residual instead would understate it, and title odds are extremely
    sensitive to this: at 2.15 the model gives the best team a 39% championship, at 3.95 a
    30%. The larger number is the defensible one, and even it is arguably a floor here, since
    this projection freezes 29 of 30 rosters at their 2025-26 shape.
    """
    ratings = pd.read_parquet(PROCESSED / "srs_ratings.parquet")
    wide = ratings.pivot(index="TEAM", columns="SEASON", values="SRS")

    prior, following = [], []
    for season in wide.columns[:-1]:
        if season + 1 not in wide.columns:
            continue
        pair = wide[[season, season + 1]].dropna()
        prior.extend(pair[season])
        following.extend(pair[season + 1])

    x, y = np.asarray(prior), np.asarray(following)
    slope, intercept = np.polyfit(x, y, 1)
    return float((y - (intercept + slope * x)).std(ddof=2))


def aging_sensitivity(
    player: str = "LeBron James",
    declines: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0),
    games: int | None = 70,
) -> pd.DataFrame:
    """How much one player's decline moves his team, swept over plausible declines.

    No aging is applied to the projection itself, and that is a deliberate refusal rather
    than an oversight. Aging DPM needs a DPM aging curve, which needs DARKO across seasons;
    only one snapshot exists here. The curve this project *can* fit is on shot efficiency,
    and its support collapses exactly where the question lives — 12 player-seasons at age 38,
    one at 41. Applying an extrapolated curve to the single player it matters most for would
    dress an assumption up as a measurement.

    A sweep is the honest substitute: rather than guess the decline, show whether the answer
    depends on it. For LeBron entering an age-42 season it does not much — a full two points
    of DPM, far beyond any plausible one-year fall, moves Philadelphia from 9th to 14th and
    never near contention.
    """
    darko = load_darko()
    roster = apply_transactions(load_minutes(2025))
    named = roster[roster.PLAYER_NAME == player]
    if named.empty:
        raise KeyError(f"{player} is not in the minutes table")
    team = named.TEAM_ABBREVIATION.iloc[0]

    rows = []
    for decline in declines:
        ratings = league_ratings(games=games, darko=age_player(darko, player, decline))
        rows.append(
            {
                "player": player,
                "team": team,
                "decline": decline,
                "rating": float(ratings.loc[team, "RATING"]),
                "rank": list(ratings.index).index(team) + 1,
            }
        )
    return pd.DataFrame(rows)


def project_league(
    n_sims: int = 20_000,
    extra_rating_sd: float | None = None,
    games: int | None = None,
    seed: int = 0,
) -> dict:
    """Simulate 2026-27: win totals for all thirty teams, and title odds.

    `extra_rating_sd` is how wrong each team's rating might be, and it is the single most
    consequential number here — the top three teams take 87% of the titles at 2.15 and 73%
    at 3.95. It defaults to `forward_rating_sd`, the year-over-year figure, rather than the
    calibration residual: that residual is a floor measured against a DARKO snapshot which
    had already seen the season it was scored on, and it excludes injury, minutes
    reallocation, and every transaction this model does not know about.
    """
    from possval.models.simulate import nba_schedule, simulate_playoffs, simulate_season

    if extra_rating_sd is None:
        extra_rating_sd = forward_rating_sd()

    ratings = league_ratings(games=games).RATING
    # The published 2026-27 calendar is not out yet, so the schedule is *sampled* under the
    # league's own structural rules rather than flattened into a round robin: division rivals
    # four times, six conference opponents four, four conference opponents three, everyone in
    # the other conference twice. Only which six get four games is random. Swap in the real
    # schedule when it lands — the shape of the answer should not move, since only the
    # opponent draw differs, but strength of schedule is exactly what a round robin erases.
    schedule = nba_schedule(CONFERENCES, DIVISION_OF, seed=seed)
    wins = simulate_season(
        ratings, schedule, n_sims=n_sims, rating_sd=extra_rating_sd, seed=seed
    )

    # Seeding by simulated win total rather than by rating, so a team that under- or
    # over-performs its rating carries that into the bracket, as it would in reality.
    # Eight per conference, not sixteen overall — a 45-win East team makes the playoffs
    # ahead of a 48-win West team, and that asymmetry is the whole reason conference
    # matters to Philadelphia.
    ordered = wins.mean().sort_values(ascending=False)
    seeded: dict[str, int] = {}
    seeds = []
    for team in ordered.index:
        side = CONFERENCES[team]
        if seeded.get(side, 0) < 8:
            seeded[side] = seeded.get(side, 0) + 1
            seeds.append(team)
    titles = simulate_playoffs(
        ratings,
        seeds,
        n_sims=n_sims,
        conferences=CONFERENCES,
        rating_sd=extra_rating_sd,
        seed=seed,
    )

    summary = pd.DataFrame(
        {
            "RATING": ratings,
            "WINS": wins.mean(),
            "WINS_P10": wins.quantile(0.10),
            "WINS_P90": wins.quantile(0.90),
            "TITLE": titles.reindex(ratings.index).fillna(0.0),
        }
    ).sort_values("RATING", ascending=False)

    return {"summary": summary, "rating_sd": extra_rating_sd, "n_sims": n_sims}
