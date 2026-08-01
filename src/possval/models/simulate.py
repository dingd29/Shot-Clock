"""Season and playoff simulation.

Layers 3 and 4 of the projection: team ratings become per-game win probabilities, which are
simulated forward into a win distribution, a seeding distribution, and finally a title
probability.

**The validation strategy is the point of this module.** A championship is one observation
per season, so a title model can never be validated on title outcomes — there will never be
enough of them. Instead the pipeline is validated where the data is and the result propagates
upward:

    game outcomes      ~1,230 per season, ~12,000 over the sample   -> Brier, log loss
    season win totals  30 teams x 10 seasons = 300                  -> MAE, calibration
    title odds         a *derived* output of the simulator          -> never fit directly

Nothing here may be tuned against title outcomes. Doing so would overfit to roughly ten data
points and invalidate everything downstream.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Points of margin the home team gets for free. Fitted below from actual results rather than
# assumed; this is the initial value only.
DEFAULT_HOME_ADVANTAGE = 2.2

# Converts a point-margin edge into a win probability.
#
# **The right value depends on what the ratings are.** Fitted against *prior-season* ratings
# — noisy predictors of the season being played — the scale comes out near 10.5, because the
# fit has to flatten predictions that are only partly informative. A simulator is not in that
# situation: it is handed the ratings it is asked to treat as true, so the correct scale is
# the one fitted against *contemporaneous* ratings, which is 7.0 (11,968 games, 2015-2025).
#
# Using 10.5 here compresses everything. A +12.7 team came out at 60 wins rather than the 68
# Oklahoma City actually won in 2024-25, and the same compression flowed into title odds.
CONTEMPORANEOUS_MARGIN_SCALE = 7.0
PRIOR_SEASON_MARGIN_SCALE = 10.5
DEFAULT_MARGIN_SCALE = CONTEMPORANEOUS_MARGIN_SCALE


def win_probability(
    rating_diff: np.ndarray | float,
    home: np.ndarray | bool = True,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    scale: float = DEFAULT_MARGIN_SCALE,
) -> np.ndarray:
    """P(team wins) given its net-rating edge over the opponent."""
    edge = np.asarray(rating_diff, dtype=float) + np.where(home, home_advantage, -home_advantage)
    return 1.0 / (1.0 + np.exp(-edge / scale))


def fit_margin_scale(games: pd.DataFrame) -> dict:
    """Estimate home advantage and the logistic scale from observed game results.

    `games` needs HOME_RATING, AWAY_RATING, HOME_WIN. Both parameters are fitted by simple
    grid search on log loss — the surface is smooth and two-dimensional, so anything more
    elaborate would be ceremony.
    """
    diff = (games.HOME_RATING - games.AWAY_RATING).to_numpy(dtype=float)
    won = games.HOME_WIN.to_numpy(dtype=float)

    best = None
    for advantage in np.arange(0.0, 5.01, 0.1):
        for scale in np.arange(6.0, 16.01, 0.25):
            p = 1.0 / (1.0 + np.exp(-(diff + advantage) / scale))
            p = np.clip(p, 1e-6, 1 - 1e-6)
            loss = -np.mean(won * np.log(p) + (1 - won) * np.log(1 - p))
            if best is None or loss < best["log_loss"]:
                best = {"home_advantage": advantage, "scale": scale, "log_loss": loss}

    p = win_probability(diff, True, best["home_advantage"], best["scale"])
    best["brier"] = float(np.mean((p - won) ** 2))
    best["n"] = len(games)
    return best


def simulate_season(
    ratings: pd.Series,
    schedule: pd.DataFrame,
    n_sims: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    scale: float = DEFAULT_MARGIN_SCALE,
    rating_sd: float = 0.0,
    seed: int = 0,
) -> pd.DataFrame:
    """Monte-Carlo an 82-game season.

    `rating_sd` injects uncertainty in the ratings themselves, redrawn once per simulation.
    Without it the win distribution reflects only game-level coin-flip noise and is far too
    narrow — the dominant uncertainty in a projection is whether the ratings are right, not
    how the coin lands.
    """
    rng = np.random.default_rng(seed)
    teams = list(ratings.index)
    index = {team: i for i, team in enumerate(teams)}

    home = schedule.HOME.map(index).to_numpy()
    away = schedule.AWAY.map(index).to_numpy()
    base = ratings.to_numpy(dtype=float)

    wins = np.zeros((n_sims, len(teams)), dtype=np.int16)
    for sim in range(n_sims):
        draw = base + rng.normal(0.0, rating_sd, len(teams)) if rating_sd else base
        p = win_probability(draw[home] - draw[away], True, home_advantage, scale)
        home_won = rng.random(len(p)) < p
        np.add.at(wins[sim], home[home_won], 1)
        np.add.at(wins[sim], away[~home_won], 1)

    return pd.DataFrame(wins, columns=teams)


def balanced_schedule(teams: list[str], games_each: int = 82) -> pd.DataFrame:
    """A round-robin schedule where every team plays exactly `games_each` games.

    Built by the circle method: one team is held fixed, the rest rotate, and each round
    pairs them off so every team plays exactly once per round. Home and away alternate by
    round, so the split is even to within one game.

    > The previous implementation enumerated all ordered pairs, repeated the list, and
    > truncated it to the right total number of games. The total was right and nothing else
    > was: truncation kept whichever pairs happened to sort first, so teams played between
    > **70 and 99 games** and hosted between 29 and 58 of them. Philadelphia drew a short
    > schedule and came out at 34 wins on a rating that deserved 43. A schedule generator is
    > exactly the kind of plumbing that looks obviously fine and is checked by nobody, so
    > `tests/test_simulate.py` now asserts the counts.

    Still a stand-in for the real NBA schedule, which is conference-weighted. Good enough for
    a win *distribution*; replace with the published schedule before quoting seeding odds.
    """
    if len(teams) % 2:
        raise ValueError("circle-method scheduling needs an even number of teams")

    fixed, rotating = teams[0], list(teams[1:])
    rounds = len(teams) - 1
    rows = []
    for round_index in range(games_each):
        order = [fixed, *rotating[round_index % rounds :], *rotating[: round_index % rounds]]
        for i in range(len(teams) // 2):
            home, away = order[i], order[len(teams) - 1 - i]
            # Alternate by round so neither side of a pairing always hosts.
            rows.append((home, away) if round_index % 2 == 0 else (away, home))
    return pd.DataFrame(rows, columns=["HOME", "AWAY"])


def simulate_playoffs(
    ratings: pd.Series,
    seeds: list[str],
    n_sims: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    scale: float = DEFAULT_MARGIN_SCALE,
    conferences: dict[str, str] | None = None,
    rating_sd: float = 0.0,
    seed: int = 0,
) -> pd.Series:
    """Best-of-seven bracket from an ordered seed field; returns P(title) per team.

    Home-court follows the 2-2-1-1-1 format, so the higher seed hosts four of seven.

    `conferences` maps team to conference. Passing it runs two eight-team brackets meeting
    in a final, as the league does. Omitting it runs one ladder over the whole field, which
    is only correct if conference has no bearing on who plays whom — it does.

    `rating_sd` redraws each team's rating once per simulated postseason, and leaving it at
    zero is a mistake worth naming: with the ratings treated as exactly known, the bracket
    is a near-deterministic ladder and the best team's title odds barely respond to how
    uncertain the projection actually is. Injecting it in the regular season alone changes
    win totals and nothing else — the title numbers came out identical at every level of
    season uncertainty, which is how this surfaced.
    """
    rng = np.random.default_rng(seed)
    fixed = {team: float(ratings[team]) for team in seeds}
    base = dict(fixed)
    titles = dict.fromkeys(seeds, 0)

    def series_winner(a: str, b: str) -> str:
        """`a` holds home court."""
        p_home = win_probability(base[a] - base[b], True, home_advantage, scale)
        p_away = win_probability(base[a] - base[b], False, home_advantage, scale)
        wins_a = wins_b = 0
        for game in range(7):
            at_home = game in (0, 1, 4, 6)
            if rng.random() < (p_home if at_home else p_away):
                wins_a += 1
            else:
                wins_b += 1
            if wins_a == 4 or wins_b == 4:
                break
        return a if wins_a == 4 else b

    def bracket(field: list[str]) -> str:
        while len(field) > 1:
            # Seeds are re-paired highest-vs-lowest each round; the earlier entry holds home.
            field = [series_winner(field[i], field[-1 - i]) for i in range(len(field) // 2)]
        return field[0]

    for _ in range(n_sims):
        if rating_sd:
            draw = rng.normal(0.0, rating_sd, len(seeds))
            base = {team: fixed[team] + shift for team, shift in zip(seeds, draw, strict=True)}
        if conferences is None:
            titles[bracket(list(seeds))] += 1
            continue
        # Two eight-team brackets meeting in the final, which is how the league actually
        # works and is not a detail: the three strongest teams in this projection are split
        # across conferences, so a single sixteen-team ladder can pit two of them against
        # each other in a semi-final that could never happen.
        finalists = [
            bracket([team for team in seeds if conferences.get(team) == side][:8])
            for side in sorted({conferences[team] for team in seeds})
        ]
        higher, lower = sorted(finalists, key=lambda team: seeds.index(team))
        titles[series_winner(higher, lower)] += 1

    return pd.Series({team: count / n_sims for team, count in titles.items()}).sort_values(
        ascending=False
    )


def summarise(wins: pd.DataFrame) -> pd.DataFrame:
    """Win distribution per team: mean and the interval a projection should be quoted with."""
    return pd.DataFrame(
        {
            "MEAN_WINS": wins.mean(),
            "P10": wins.quantile(0.10),
            "P50": wins.quantile(0.50),
            "P90": wins.quantile(0.90),
            "P_50_PLUS": (wins >= 50).mean(),
            "P_60_PLUS": (wins >= 60).mean(),
        }
    ).sort_values("MEAN_WINS", ascending=False)
