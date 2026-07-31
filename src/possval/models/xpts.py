"""Expected points per shot attempt (xPTS).

Predicts P(make) per attempt and converts to expected points via the attempt's own value
(2 or 3). Two models are fit as a ladder so the gain from the flexible model is measurable
rather than assumed:

  1. logistic regression on a small numeric design  - the interpretable baseline
  2. gradient-boosted trees on the full feature set - the working model
  3. isotonic calibration on a held-out season      - because raw GBM probabilities are
     systematically over-confident at the tails, and every downstream use (possession value,
     win probability, market comparison) needs calibrated probabilities, not just ranked ones

**Splits are always by season, never random.** A random split leaks: shots from the same game
and possession appear on both sides, and the shooter-prior features are built from season
aggregates. Evaluation asserts this.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

BASELINE_NUMERIC = [
    "SHOT_DISTANCE",
    "SHOT_ANGLE",
    "SHOT_CLOCK",
    "IS_3",
    "PRIOR_ZONE_FG_PCT",
]

GBM_NUMERIC = [
    "SHOT_DISTANCE",
    "LOC_X",
    "LOC_Y",
    "SHOT_ANGLE",
    # CLOCK_ELAPSED is deliberately absent: it is exactly 24 - SHOT_CLOCK, and including
    # both makes permutation importance report each as worthless because permuting one
    # leaves its perfect substitute in place.
    "SHOT_CLOCK",
    "PERIOD",
    "GAME_SECONDS_REMAINING",
    "IS_CLUTCH",
    "SCORE_MARGIN",
    "IS_3",
    "PRIOR_ZONE_FG_PCT",
    "PRIOR_FGA",
]

GBM_CATEGORICAL = [
    "SHOT_ZONE_BASIC",
    "SHOT_ZONE_AREA",
    "SHOT_ZONE_RANGE",
    "ACTION_TYPE",
    "CHANCE_START_TYPE",
]


@dataclass
class SeasonSplit:
    """Time-ordered split. Train on the past, tune on the middle, report on the future."""

    train: tuple[int, int]
    valid: int
    test: tuple[int, int]

    def assert_ordered(self) -> None:
        assert self.train[1] < self.valid < self.test[0], (
            f"split is not time-ordered: {self}"
        )


DEFAULT_SPLIT = SeasonSplit(train=(2015, 2022), valid=2023, test=(2024, 2024))


@dataclass
class XPtsResult:
    metrics: pd.DataFrame
    calibration: pd.DataFrame
    feature_importance: pd.DataFrame = field(default_factory=pd.DataFrame)
    models: dict = field(default_factory=dict)


def _prepare(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df[columns].copy()
    for col in out.columns:
        if str(out[col].dtype) == "category":
            continue
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _split_frames(df: pd.DataFrame, split: SeasonSplit):
    split.assert_ordered()
    train = df[df.SEASON.between(*split.train)]
    valid = df[split.valid == df.SEASON]
    test = df[df.SEASON.between(*split.test)]
    return train, valid, test


def _score(name: str, y: np.ndarray, p: np.ndarray, pts_value: np.ndarray) -> dict:
    """Probability metrics plus the points-scale error that actually matters downstream."""
    xpts = p * pts_value
    actual = y * pts_value
    return {
        "model": name,
        "n": len(y),
        "log_loss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)),
        "brier": brier_score_loss(y, p),
        "auc": roc_auc_score(y, p),
        "xpts_mean": xpts.mean(),
        "actual_pts_mean": actual.mean(),
        "xpts_bias": xpts.mean() - actual.mean(),
    }


def _permutation_importance(
    model, test: pd.DataFrame, cols: list[str], y_te: np.ndarray, seed: int, sample: int = 60_000
) -> pd.DataFrame:
    """Permutation importance in log-loss units: how much worse the model gets when a
    feature is shuffled. Tree-internal split gains are biased toward high-cardinality
    features, which would flatter ACTION_TYPE here; permutation on held-out data is not."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(test), size=min(sample, len(test)), replace=False)
    x = _prepare(test.iloc[idx], cols)
    y = y_te[idx]

    base = log_loss(y, np.clip(model.predict_proba(x)[:, 1], 1e-6, 1 - 1e-6))
    rows = []
    for col in cols:
        shuffled = x.copy()
        shuffled[col] = shuffled[col].to_numpy()[rng.permutation(len(shuffled))]
        score = log_loss(y, np.clip(model.predict_proba(shuffled)[:, 1], 1e-6, 1 - 1e-6))
        rows.append({"feature": col, "logloss_increase": score - base})
    return (
        pd.DataFrame(rows).sort_values("logloss_increase", ascending=False).reset_index(drop=True)
    )


def train_xpts(
    df: pd.DataFrame, split: SeasonSplit = DEFAULT_SPLIT, seed: int = 0
) -> XPtsResult:
    """Fit the ladder and report out-of-sample metrics on the test seasons."""
    train, valid, test = _split_frames(df, split)
    if not len(valid) or not len(test):
        raise ValueError("empty validation or test split — check season coverage")

    y_tr, y_va, y_te = (f.SHOT_MADE_FLAG.to_numpy() for f in (train, valid, test))
    pts_te = (2 + test.IS_3).to_numpy()
    rows = []

    # --- baseline 0: league average, the number to beat before any modelling ---
    p_const = np.full(len(test), y_tr.mean())
    rows.append(_score("league_mean", y_te, p_const, pts_te))

    # --- baseline 1: logistic regression ---
    scaler = StandardScaler()
    x_tr = scaler.fit_transform(_prepare(train, BASELINE_NUMERIC).fillna(0.0))
    x_te = scaler.transform(_prepare(test, BASELINE_NUMERIC).fillna(0.0))
    logit = LogisticRegression(max_iter=1000, random_state=seed).fit(x_tr, y_tr)
    p_logit = logit.predict_proba(x_te)[:, 1]
    rows.append(_score("logistic", y_te, p_logit, pts_te))

    # --- model 2: gradient-boosted trees ---
    cols = GBM_NUMERIC + [c for c in GBM_CATEGORICAL if c in df.columns]
    gbm = HistGradientBoostingClassifier(
        max_iter=500,
        learning_rate=0.06,
        max_leaf_nodes=63,
        min_samples_leaf=200,
        l2_regularization=1.0,
        categorical_features="from_dtype",
        early_stopping=True,
        validation_fraction=0.1,  # carved out of train only; never touches valid/test
        n_iter_no_change=30,
        random_state=seed,
    )
    gbm.fit(_prepare(train, cols), y_tr)
    p_gbm = gbm.predict_proba(_prepare(test, cols))[:, 1]
    rows.append(_score("gbm", y_te, p_gbm, pts_te))

    # --- model 3: isotonic calibration, fitted on the validation season only ---
    p_va = gbm.predict_proba(_prepare(valid, cols))[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(p_va, y_va)
    p_cal = iso.predict(p_gbm)
    rows.append(_score("gbm_calibrated", y_te, p_cal, pts_te))

    frac_pos, mean_pred = calibration_curve(y_te, p_cal, n_bins=20, strategy="quantile")
    calibration = pd.DataFrame({"mean_predicted": mean_pred, "fraction_positive": frac_pos})

    importance = _permutation_importance(gbm, test, cols, y_te, seed)

    return XPtsResult(
        metrics=pd.DataFrame(rows),
        calibration=calibration,
        feature_importance=importance,
        models={"logistic": logit, "scaler": scaler, "gbm": gbm, "isotonic": iso},
    )


def evaluate_xpts(result: XPtsResult) -> pd.DataFrame:
    """Metrics relative to the league-mean baseline, which is how they should be read."""
    metrics = result.metrics.set_index("model")
    base = metrics.loc["league_mean"]
    out = metrics.copy()
    out["logloss_gain_pct"] = (1 - metrics.log_loss / base.log_loss) * 100
    out["brier_gain_pct"] = (1 - metrics.brier / base.brier) * 100
    return out.reset_index()


def ablate(
    df: pd.DataFrame,
    groups: dict[str, list[str]],
    split: SeasonSplit = DEFAULT_SPLIT,
    seed: int = 0,
) -> pd.DataFrame:
    """Refit the model with each feature group removed and report the loss it costs.

    This is the honest way to value a feature that has correlated substitutes in the design.
    Permutation importance answers "what if this column were noise, holding the rest fixed";
    ablation answers "what if I never had this information at all", which is the question
    that matters for a feature we went to considerable trouble to construct.
    """
    train, valid, test = _split_frames(df, split)
    y_tr, y_te = train.SHOT_MADE_FLAG.to_numpy(), test.SHOT_MADE_FLAG.to_numpy()
    all_cols = GBM_NUMERIC + [c for c in GBM_CATEGORICAL if c in df.columns]

    rows = []
    for name, dropped in {"full_model": [], **groups}.items():
        cols = [c for c in all_cols if c not in dropped]
        model = HistGradientBoostingClassifier(
            max_iter=500,
            learning_rate=0.06,
            max_leaf_nodes=63,
            min_samples_leaf=200,
            l2_regularization=1.0,
            categorical_features="from_dtype",
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=30,
            random_state=seed,
        ).fit(_prepare(train, cols), y_tr)
        p = model.predict_proba(_prepare(test, cols))[:, 1]
        rows.append(
            {
                "removed": name,
                "log_loss": log_loss(y_te, np.clip(p, 1e-6, 1 - 1e-6)),
                "brier": brier_score_loss(y_te, p),
                "auc": roc_auc_score(y_te, p),
            }
        )

    out = pd.DataFrame(rows)
    base = out.loc[out.removed == "full_model"].iloc[0]
    out["logloss_cost"] = out.log_loss - base.log_loss
    out["auc_cost"] = base.auc - out.auc
    return out


def predict_xpts(result: XPtsResult, df: pd.DataFrame) -> np.ndarray:
    """Calibrated expected points for arbitrary rows, using the fitted ladder."""
    cols = GBM_NUMERIC + [c for c in GBM_CATEGORICAL if c in df.columns]
    p = result.models["gbm"].predict_proba(_prepare(df, cols))[:, 1]
    p = result.models["isotonic"].predict(p)
    return p * (2 + df.IS_3.to_numpy())
