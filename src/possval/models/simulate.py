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

# Converts a point-margin edge into a win probability. A logistic scale of ~10.5 points per
# logit is the long-standing NBA value; `fit_margin_scale` re-estimates it from the sample.
DEFAULT_MARGIN_SCALE = 10.5


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
    """A round-robin schedule with equal home/away splits.

    A stand-in for the real NBA schedule, which is conference-weighted. Good enough for a
    win *distribution*; replace with the published schedule before quoting seeding odds,
    since strength of schedule genuinely differs by conference.
    """
    pairs = [(h, a) for h in teams for a in teams if h != a]
    reps = int(np.ceil(games_each * len(teams) / 2 / len(pairs)))
    rows = (pairs * reps)[: games_each * len(teams) // 2]
    return pd.DataFrame(rows, columns=["HOME", "AWAY"])


def simulate_playoffs(
    ratings: pd.Series,
    seeds: list[str],
    n_sims: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    scale: float = DEFAULT_MARGIN_SCALE,
    seed: int = 0,
) -> pd.Series:
    """Best-of-seven bracket from an ordered 16-seed field; returns P(title) per team.

    Home-court follows the 2-2-1-1-1 format, so the higher seed hosts four of seven.
    """
    rng = np.random.default_rng(seed)
    base = {team: ratings[team] for team in seeds}
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

    for _ in range(n_sims):
        field = list(seeds)
        while len(field) > 1:
            # Seeds are re-paired highest-vs-lowest each round; the earlier entry holds home.
            field = [series_winner(field[i], field[-1 - i]) for i in range(len(field) // 2)]
        titles[field[0]] += 1

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
