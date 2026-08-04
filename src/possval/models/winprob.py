"""Live win probability, and whether the reconstructed shot clock adds anything to it.

The ablation in §6 asked whether the shot clock helps predict **whether a shot goes in** and
answered no: removing it costs 0.00136 log loss, the smallest group tested. That is the right
answer to that question and the wrong question to stop on.

Shot clock is not about whether the shot you took goes in. It is about whether you get a good
shot at all — the continuation value in `stopping.py` runs from 0.36 points to 0.81 across the
clock, a 2.2x range. So the place it should earn its keep is a model of **possession and game
outcomes**, not shot outcomes.

This is that test. Live win probability from game state, fitted with and without shot-clock
features, on the same rows and the same time-ordered split. NBA publishes its own per-second
win probability, so a production benchmark exists — and it is built from a feed that does not
contain a shot clock, which is exactly why this is worth asking.

**The honest framing.** A win-probability model is dominated by score margin and time
remaining; nothing else comes close. Any shot-clock contribution will be small in absolute
terms. The question is whether it is reliably non-zero out of sample, not whether it is large.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.paths import PROCESSED

PERIOD_SECONDS = 720.0
OVERTIME_SECONDS = 300.0

# State that any win-probability model has. These are the baseline; the shot-clock block is
# tested on top of them.
BASE_FEATURES = [
    "MARGIN",
    "GAME_SECONDS_REMAINING",
    "MARGIN_PER_SQRT_TIME",
    "IS_HOME_POSSESSION",
    "PERIOD",
]

# The block under test. `SHOT_CLOCK` is the reconstructed field; the rest are the possession
# context that only exists because chances were reconstructed alongside it.
CLOCK_FEATURES = [
    "SHOT_CLOCK",
    "CHANCE_ELAPSED",
    "IS_LATE_CLOCK",
]


def game_seconds_remaining(period: pd.Series, game_clock: pd.Series) -> pd.Series:
    """Seconds left in regulation, treating overtime as extra time beyond zero."""
    regulation_left = np.maximum(4 - period, 0) * PERIOD_SECONDS
    overtime = np.where(period > 4, 0.0, 0.0)
    return game_clock + regulation_left + overtime


def build_state(season: int) -> pd.DataFrame:
    """One row per play-by-play event, carrying the state a live model would see.

    The label is whether the *home* team went on to win, joined from the final result. Events
    with no reconstructed clock are dropped rather than imputed, matching the treatment
    everywhere else in the project.
    """
    from possval.models.ratings import game_results

    events = pd.read_parquet(
        PROCESSED / f"pbp_clock_{season}.parquet",
        columns=[
            "GAME_ID", "EVENTNUM", "PERIOD", "GAME_CLOCK", "SCOREMARGIN",
            "SHOT_CLOCK", "OFF_TEAM_ID", "CHANCE_ID",
        ],
    ).sort_values(["GAME_ID", "EVENTNUM"])

    margin = events.SCOREMARGIN.replace("TIE", "0").astype("string").astype("Float64")
    events["MARGIN"] = margin.groupby(events.GAME_ID).ffill().fillna(0.0).astype(float)

    events["GAME_SECONDS_REMAINING"] = game_seconds_remaining(events.PERIOD, events.GAME_CLOCK)
    # Margin matters more as time runs out, and this is the standard way to say so: a
    # two-point lead with a minute left is not a two-point lead in the first quarter.
    events["MARGIN_PER_SQRT_TIME"] = events.MARGIN / np.sqrt(
        events.GAME_SECONDS_REMAINING.clip(lower=1.0)
    )
    events["CHANCE_ELAPSED"] = 24.0 - events.SHOT_CLOCK
    events["IS_LATE_CLOCK"] = (events.SHOT_CLOCK <= 7).astype(float)

    results = game_results(season)[["GAME_ID", "HOME", "AWAY", "HOME_WIN"]]
    teams = (
        pd.read_parquet(
            PROCESSED / f"pbp_clock_{season}.parquet",
            columns=["GAME_ID", "PLAYER1_TEAM_ID", "PLAYER1_TEAM_ABBREVIATION"],
        )
        .dropna()
        .drop_duplicates("PLAYER1_TEAM_ID")
        .set_index("PLAYER1_TEAM_ID")
        .PLAYER1_TEAM_ABBREVIATION
    )
    merged = events.merge(results, on="GAME_ID", how="inner")
    merged["OFF_TEAM"] = merged.OFF_TEAM_ID.map(teams)
    merged["IS_HOME_POSSESSION"] = (merged.OFF_TEAM == merged.HOME).astype(float)

    merged["SEASON"] = season
    keep = ["GAME_ID", "SEASON", "HOME_WIN", *BASE_FEATURES, *CLOCK_FEATURES]
    return merged.dropna(subset=keep)[keep]


def load_state(first: int = 2015, last: int = 2024) -> pd.DataFrame:
    frames = []
    for season in range(first, last + 1):
        if (PROCESSED / f"pbp_clock_{season}.parquet").exists():
            frames.append(build_state(season))
    return pd.concat(frames, ignore_index=True)


def compare(
    state: pd.DataFrame,
    train_through: int = 2022,
    valid: int = 2023,
    test: int = 2024,
    seed: int = 0,
) -> pd.DataFrame:
    """Fit with and without the shot-clock block; report out-of-sample separation.

    Split is by season and never random — two events from the same game are near-duplicates,
    so a random split would leak the outcome directly.

    **Clustered on games, not events.** A season has ~575k events but only ~1,230 games, and
    every event in a game shares one label. Reporting an event-level standard error would
    imply hundreds of times more information than exists, so the difference between the two
    models is bootstrapped over *games*.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    train = state[state.SEASON <= train_through]
    validation = state[state.SEASON == valid]
    held_out = state[state.SEASON == test]
    if held_out.empty:
        raise ValueError(f"no rows for the test season {test}")

    fitted = {}
    for name, columns in [
        ("base", BASE_FEATURES),
        ("base + shot clock", BASE_FEATURES + CLOCK_FEATURES),
    ]:
        model = HistGradientBoostingClassifier(
            max_iter=400,
            learning_rate=0.06,
            max_leaf_nodes=63,
            min_samples_leaf=500,
            l2_regularization=1.0,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=25,
            random_state=seed,
        ).fit(
            pd.concat([train, validation])[columns],
            pd.concat([train, validation]).HOME_WIN,
        )
        fitted[name] = model.predict_proba(held_out[columns])[:, 1]

    outcomes = held_out.HOME_WIN.to_numpy()
    rows = []
    for name, probabilities in fitted.items():
        rows.append(
            {
                "model": name,
                "n_events": len(held_out),
                "n_games": held_out.GAME_ID.nunique(),
                "log_loss": log_loss(outcomes, np.clip(probabilities, 1e-6, 1 - 1e-6)),
                "brier": brier_score_loss(outcomes, probabilities),
                "auc": roc_auc_score(outcomes, probabilities),
            }
        )
    return pd.DataFrame(rows)


def bootstrap_difference(
    state: pd.DataFrame,
    n_boot: int = 200,
    train_through: int = 2022,
    valid: int = 2023,
    test: int = 2024,
    seed: int = 0,
) -> dict:
    """Game-clustered bootstrap of the log-loss improvement from the shot-clock block.

    Refitting per resample would be honest but is not what is uncertain here — the models are
    fitted once on the training seasons, and the bootstrap resamples the *test games* to ask
    how stable the measured difference is on unseen data.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier

    train = pd.concat([state[state.SEASON <= train_through], state[state.SEASON == valid]])
    held_out = state[state.SEASON == test].copy()

    predictions = {}
    for name, columns in [
        ("base", BASE_FEATURES),
        ("clock", BASE_FEATURES + CLOCK_FEATURES),
    ]:
        model = HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.06, max_leaf_nodes=63, min_samples_leaf=500,
            l2_regularization=1.0, early_stopping=True, validation_fraction=0.1,
            n_iter_no_change=25, random_state=seed,
        ).fit(train[columns], train.HOME_WIN)
        predictions[name] = np.clip(model.predict_proba(held_out[columns])[:, 1], 1e-6, 1 - 1e-6)

    outcomes = held_out.HOME_WIN.to_numpy()

    def loss(probabilities, mask):
        y, p = outcomes[mask], probabilities[mask]
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

    # `groupby(...).indices` builds the game -> row-positions map in a single pass. Scanning
    # the full array once per game instead is O(games x rows) — 1,230 x 550,132 here, which
    # turned a few-second bootstrap into one that never finished.
    index = held_out.reset_index(drop=True).groupby("GAME_ID").indices
    unique_games = np.array(list(index))

    rng = np.random.default_rng(seed)
    differences = []
    for _ in range(n_boot):
        drawn = rng.choice(unique_games, size=len(unique_games), replace=True)
        mask = np.concatenate([index[game] for game in drawn])
        differences.append(loss(predictions["base"], mask) - loss(predictions["clock"], mask))

    differences = np.array(differences)
    return {
        "improvement": float(loss(predictions["base"], slice(None))
                             - loss(predictions["clock"], slice(None))),
        "ci_low": float(np.percentile(differences, 2.5)),
        "ci_high": float(np.percentile(differences, 97.5)),
        "share_positive": float((differences > 0).mean()),
        "n_games": int(len(unique_games)),
    }
