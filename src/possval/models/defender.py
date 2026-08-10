"""Closest-defender extraction from the public 2015-16 SportVU game archives.

The source repository contains one compressed JSON game file, a play-by-play event index, and a
precomputed release-time table.  Raw tracking coordinates remain outside this repository.  This
module turns only the release frame into a compact, auditable shot table; it does not retain player
trajectories or realized information from later in the possession.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold


def archive_path(source: Path, shot: pd.Series) -> Path:
    """Resolve the public archive name from the shot date and away/home abbreviations."""
    date = pd.to_datetime(str(int(shot.GAME_DATE)), format="%Y%m%d").strftime("%m.%d.%Y")
    return source / "data" / f"{date}.{shot.VTM}.at.{shot.HTM}.7z"


def release_frame(
    events: dict[int, dict],
    event_id: int,
    event_clock: float,
    shooter_id: int,
    possession_radius: float = 3.0,
) -> list | None:
    """Last shooter-possession frame before the logged shot result.

    The source repository's `SHOT_TIME` is an apex-adjacent proxy and is not used: its published
    indexing formula often selects a frame after the ball has left the shooter.  We search the
    shot event and predecessor from 0.5 seconds after to 5 seconds before the PBP timestamp.  A
    release candidate has the ball within three horizontal feet of the shooter, at shooting
    height, followed 0.2 seconds later by both rising height and separation.  The closest such
    candidate to the logged result is the final possession boundary.
    """
    candidates = []
    for candidate_id in (event_id - 1, event_id):
        event = events.get(candidate_id)
        if event is not None:
            candidates.extend(event.get("moments", []))
    records = []
    for moment in candidates:
        if len(moment) < 6 or moment[2] is None or not moment[5]:
            continue
        if not event_clock - 0.5 <= float(moment[2]) <= event_clock + 5.0:
            continue
        ball = next((row for row in moment[5] if int(row[0]) == -1), None)
        shooter = next((row for row in moment[5] if int(row[1]) == shooter_id), None)
        if ball is None or shooter is None:
            continue
        distance = float(
            np.hypot(float(ball[2]) - float(shooter[2]), float(ball[3]) - float(shooter[3]))
        )
        records.append((float(moment[2]), distance, float(ball[4]), moment))
    # Overlapping SportVU events duplicate frames. Keep one frame per clock tick in real-time
    # order (the game clock descends as the play progresses).
    records = sorted({record[0]: record for record in records}.values(), reverse=True)
    if not records:
        return None
    rising = []
    for at, record in enumerate(records[:-5]):
        future = records[at + 5]
        in_possession = record[1] <= possession_radius and 3.0 <= record[2] <= 13.0
        separates = future[1] >= record[1] + 0.5
        rises = future[2] >= record[2] + 0.5
        if in_possession and separates and rises:
            rising.append(record)
    # Dunks and tracking noise need a transparent fallback: the final close, shooting-height
    # frame. It is still a release-proximity observation, but the match-quality report exposes
    # how often the rising/separating rule itself succeeded.
    used_fallback = False
    if not rising:
        rising = [
            record
            for record in records
            if record[1] <= possession_radius and 3.0 <= record[2] <= 13.0
        ]
        used_fallback = True
    if not rising:
        return None
    selected = min(rising, key=lambda record: abs(record[0] - event_clock))
    selected[3].append({"release_fallback": used_fallback})
    return selected[3]


def defender_at_release(
    moment: list,
    shooter_id: int,
    shooter_team_id: int,
) -> dict | None:
    """Shooter, ball, and nearest opposing player in one SportVU frame."""
    coordinates = moment[5]
    ball = next((row for row in coordinates if int(row[0]) == -1), None)
    shooter = next((row for row in coordinates if int(row[1]) == shooter_id), None)
    defenders = [
        row
        for row in coordinates
        if int(row[0]) not in (-1, shooter_team_id) and int(row[1]) != -1
    ]
    if ball is None or shooter is None or not defenders:
        return None
    distances = np.asarray(
        [np.hypot(float(row[2]) - float(shooter[2]), float(row[3]) - float(shooter[3]))
         for row in defenders]
    )
    closest_at = int(np.argmin(distances))
    closest = defenders[closest_at]
    metadata = moment[6] if len(moment) > 6 and isinstance(moment[6], dict) else {}
    return {
        "RELEASE_GAME_CLOCK": float(moment[2]),
        "RELEASE_SHOT_CLOCK": float(moment[3]) if moment[3] is not None else np.nan,
        "RELEASE_FRAME_MS": int(moment[1]),
        "SHOOTER_X": float(shooter[2]),
        "SHOOTER_Y": float(shooter[3]),
        "BALL_X": float(ball[2]),
        "BALL_Y": float(ball[3]),
        "BALL_Z": float(ball[4]),
        "BALL_SHOOTER_DISTANCE": float(
            np.hypot(float(ball[2]) - float(shooter[2]), float(ball[3]) - float(shooter[3]))
        ),
        "CLOSE_DEFENDER_ID": int(closest[1]),
        "CLOSE_DEFENDER_TEAM_ID": int(closest[0]),
        "CLOSE_DEFENDER_DISTANCE": float(distances[closest_at]),
        "N_DEFENDERS": len(defenders),
        "RELEASE_FALLBACK": bool(metadata.get("release_fallback", False)),
    }


def extract_game(archive: Path, fixed_shots: pd.DataFrame) -> pd.DataFrame:
    """Extract release-frame defender distance for every fixed shot in one archive."""
    raw = subprocess.check_output(["/usr/bin/bsdtar", "-xOf", str(archive)])
    game = json.loads(raw)
    events = {int(event["eventId"]): event for event in game["events"]}
    rows = []
    for shot in fixed_shots.itertuples(index=False):
        moment = release_frame(
            events,
            int(shot.GAME_EVENT_ID),
            float(shot.EVENTTIME),
            int(shot.PLAYER_ID),
        )
        detail = (
            defender_at_release(moment, int(shot.PLAYER_ID), int(shot.TEAM_ID))
            if moment is not None
            else None
        )
        row = {
            "GAME_ID": str(shot.GAME_ID).zfill(10),
            "GAME_EVENT_ID": int(shot.GAME_EVENT_ID),
            "PLAYER_ID": int(shot.PLAYER_ID),
            "TEAM_ID": int(shot.TEAM_ID),
            "APEX_PROXY_TIME": float(shot.SHOT_TIME),
            "PBP_EVENT_CLOCK": float(shot.EVENTTIME),
            "TRACKING_MATCHED": detail is not None,
        }
        if detail is not None:
            row.update(detail)
            row["RELEASE_BEFORE_EVENT_SECONDS"] = (
                detail["RELEASE_GAME_CLOCK"] - row["PBP_EVENT_CLOCK"]
            )
        rows.append(row)
    return pd.DataFrame(rows)


def extract_all(source: Path, output_dir: Path) -> pd.DataFrame:
    """Checkpointed extraction over all games represented in `shots_fixed.csv`."""
    fixed = pd.read_csv(source / "data" / "shots" / "shots_fixed.csv", dtype={"GAME_ID": str})
    fixed["GAME_ID"] = fixed.GAME_ID.str.zfill(10)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    games = list(fixed.groupby("GAME_ID", sort=True))
    for at, (game_id, game_shots) in enumerate(games, start=1):
        checkpoint = output_dir / f"{game_id}.csv"
        if checkpoint.exists():
            outputs.append(pd.read_csv(checkpoint, dtype={"GAME_ID": str}))
            continue
        archive = archive_path(source, game_shots.iloc[0])
        if not archive.exists():
            frame = game_shots[
                ["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "TEAM_ID", "SHOT_TIME", "EVENTTIME"]
            ].copy()
            frame = frame.rename(
                columns={"SHOT_TIME": "APEX_PROXY_TIME", "EVENTTIME": "PBP_EVENT_CLOCK"}
            )
            frame["TRACKING_MATCHED"] = False
            frame["MISSING_ARCHIVE"] = True
        else:
            frame = extract_game(archive, game_shots)
            frame["MISSING_ARCHIVE"] = False
        frame.to_csv(checkpoint, index=False)
        outputs.append(frame)
        if at == 1 or at % 10 == 0 or at == len(games):
            matched = sum(int(part.TRACKING_MATCHED.sum()) for part in outputs)
            total = sum(len(part) for part in outputs)
            print(f"SportVU {at}/{len(games)} games | {matched:,}/{total:,} matched", flush=True)
    return pd.concat(outputs, ignore_index=True)


def join_tracking_shots(shots: pd.DataFrame, tracking: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Unique-key join and complete match accounting; no easy-match filtering."""
    keys = ["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID"]
    left = shots.copy()
    right = tracking.copy()
    left["GAME_ID"] = left.GAME_ID.astype(str).str.zfill(10)
    right["GAME_ID"] = right.GAME_ID.astype(str).str.zfill(10)
    right_duplicate = right.duplicated(keys, keep=False)
    right_duplicate_rows = int(right_duplicate.sum())
    eligible_games = pd.Index(right.GAME_ID.unique())
    eligible = left[left.GAME_ID.isin(eligible_games)].copy()
    left_duplicate = eligible.duplicated(keys, keep=False)
    left_duplicate_rows = int(left_duplicate.sum())
    # Ambiguous rows stay in the match denominator but never enter the modelling table.
    unambiguous_left = eligible[~left_duplicate]
    unambiguous_right = right[~right_duplicate]
    joined = unambiguous_left.merge(
        unambiguous_right,
        on=keys,
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    joined["AMBIGUOUS"] = False
    if left_duplicate_rows:
        ambiguous = eligible[left_duplicate].copy()
        ambiguous["_merge"] = "left_only"
        ambiguous["TRACKING_MATCHED"] = False
        ambiguous["AMBIGUOUS"] = True
        joined = pd.concat([joined, ambiguous], ignore_index=True, sort=False)
    tracking_matched = joined.TRACKING_MATCHED.eq(True)
    uniquely_matched = joined._merge.eq("both") & tracking_matched
    metrics = {
        "N_SOURCE_SHOTS": len(right),
        "N_ELIGIBLE_RECONSTRUCTED_FGA": len(eligible),
        "N_UNIQUE_KEY_JOINS": int(joined._merge.eq("both").sum()),
        "N_TRACKING_MATCHED": int(uniquely_matched.sum()),
        "UNIQUE_KEY_JOIN_RATE": float(joined._merge.eq("both").sum() / len(eligible)),
        "TRACKING_MATCH_RATE": float(uniquely_matched.sum() / len(eligible)),
        "N_AMBIGUOUS": left_duplicate_rows + right_duplicate_rows,
        "N_AMBIGUOUS_RECONSTRUCTED": left_duplicate_rows,
        "N_AMBIGUOUS_TRACKING": right_duplicate_rows,
    }
    return joined.drop(columns="_merge"), metrics


def _defender_design(frame: pd.DataFrame, include_defender: bool) -> pd.DataFrame:
    columns = ["BASE_PROB", "SHOT_DISTANCE", "SHOT_CLOCK", "IS_3", "SHOT_ZONE_BASIC"]
    if include_defender:
        columns.append("CLOSE_DEFENDER_DISTANCE")
    design = frame[columns].copy()
    design["SHOT_ZONE_BASIC"] = design.SHOT_ZONE_BASIC.astype("category")
    return design


def crossfit_defender_value(
    matched: pd.DataFrame,
    n_splits: int = 5,
    seed: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Game-folded xPTS recalibration, with and without closest-defender distance."""
    frame = matched.dropna(
        subset=[
            "XPTS", "SHOT_MADE_FLAG", "IS_3", "SHOT_DISTANCE", "SHOT_CLOCK",
            "SHOT_ZONE_BASIC", "CLOSE_DEFENDER_DISTANCE", "GAME_ID",
        ]
    ).copy()
    frame["BASE_PROB"] = (frame.XPTS / (2 + frame.IS_3)).clip(0.001, 0.999)
    frame["CLOSE_DEFENDER_DISTANCE"] = frame.CLOSE_DEFENDER_DISTANCE.clip(0, 30)
    y = frame.SHOT_MADE_FLAG.to_numpy(dtype=int)
    groups = frame.GAME_ID.to_numpy()
    fold = GroupKFold(n_splits=n_splits)
    predictions = {
        "baseline": np.full(len(frame), np.nan),
        "defender-aware": np.full(len(frame), np.nan),
    }
    for train_at, test_at in fold.split(frame, y, groups):
        for label, include_defender in (("baseline", False), ("defender-aware", True)):
            model = HistGradientBoostingClassifier(
                max_iter=250,
                learning_rate=0.05,
                max_leaf_nodes=31,
                min_samples_leaf=150,
                l2_regularization=1.0,
                early_stopping=True,
                validation_fraction=0.1,
                n_iter_no_change=20,
                categorical_features="from_dtype",
                random_state=seed,
            )
            model.fit(_defender_design(frame.iloc[train_at], include_defender), y[train_at])
            predictions[label][test_at] = model.predict_proba(
                _defender_design(frame.iloc[test_at], include_defender)
            )[:, 1]
    rows = []
    for label, predicted in predictions.items():
        frame[f"P_{label.upper().replace('-', '_')}"] = predicted
        rows.append(
            {
                "MODEL": label,
                "N": len(frame),
                "LOG_LOSS": log_loss(y, np.clip(predicted, 1e-6, 1 - 1e-6)),
                "BRIER": brier_score_loss(y, predicted),
                "AUC": roc_auc_score(y, predicted),
                "BIAS": float((predicted - y).mean()),
            }
        )
    frame["DEFENDER_XPTS"] = frame.P_DEFENDER_AWARE * (2 + frame.IS_3)
    return frame, pd.DataFrame(rows)


def paired_game_bootstrap_improvement(
    crossfit: pd.DataFrame,
    n_draws: int = 2_000,
    seed: int = 0,
) -> pd.DataFrame:
    """Paired game-cluster intervals for baseline minus defender-aware scoring loss."""
    y = crossfit.SHOT_MADE_FLAG.to_numpy(dtype=float)
    base = np.clip(crossfit.P_BASELINE.to_numpy(), 1e-6, 1 - 1e-6)
    aware = np.clip(crossfit.P_DEFENDER_AWARE.to_numpy(), 1e-6, 1 - 1e-6)
    losses = pd.DataFrame(
        {
            "GAME_ID": crossfit.GAME_ID.to_numpy(),
            "N": 1,
            "LOGLOSS_GAIN": -(y * np.log(base) + (1 - y) * np.log(1 - base))
            + (y * np.log(aware) + (1 - y) * np.log(1 - aware)),
            "BRIER_GAIN": (base - y) ** 2 - (aware - y) ** 2,
        }
    ).groupby("GAME_ID").agg(
        N=("N", "sum"),
        LOGLOSS_GAIN=("LOGLOSS_GAIN", "sum"),
        BRIER_GAIN=("BRIER_GAIN", "sum"),
    )
    values = losses[["N", "LOGLOSS_GAIN", "BRIER_GAIN"]].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(n_draws, len(values)))
    totals = values[indices].sum(axis=1)
    rows = []
    for at, metric in ((1, "LOG_LOSS"), (2, "BRIER")):
        draws = totals[:, at] / totals[:, 0]
        estimate = values[:, at].sum() / values[:, 0].sum()
        rows.append(
            {
                "METRIC": metric,
                "IMPROVEMENT": estimate,
                "LOW": np.quantile(draws, 0.025),
                "HIGH": np.quantile(draws, 0.975),
                "N_DRAWS": n_draws,
            }
        )
    return pd.DataFrame(rows)


def open_shot_case_control(
    scored_baseline: pd.DataFrame,
    scored_aware: pd.DataFrame,
    seed: int = 0,
) -> pd.DataFrame:
    """Match baseline flags to controls within open-shot basketball contexts."""
    keys = ["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID"]
    aware = scored_aware[keys + ["BELOW", "EXPOSURE"]].rename(
        columns={"BELOW": "AWARE_BELOW", "EXPOSURE": "AWARE_EXPOSURE"}
    )
    frame = scored_baseline.merge(aware, on=keys, how="inner", validate="one_to_one")
    frame = frame[frame.CLOSE_DEFENDER_DISTANCE.ge(4)].copy()
    frame["DEFENDER_BAND"] = np.where(
        frame.CLOSE_DEFENDER_DISTANCE.ge(6), "wide open (6+ ft)", "open (4-6 ft)"
    )
    frame["CLOCK_PHASE_MATCH"] = pd.cut(
        frame.SECOND,
        [-1, 7, 15, 24],
        labels=["late", "middle", "early"],
        include_lowest=True,
    )
    zones = frame.SHOT_ZONE_BASIC.astype("string")
    frame["SHOT_FAMILY_MATCH"] = np.select(
        [
            zones.eq("Restricted Area"),
            zones.eq("In The Paint (Non-RA)"),
            zones.eq("Mid-Range"),
            zones.str.contains("3", regex=False),
        ],
        ["rim", "paint (non-RA)", "mid-range", "three"],
        default="other",
    )
    strata = ["TEAM_ABBREVIATION", "CLOCK_PHASE_MATCH", "SHOT_FAMILY_MATCH", "DEFENDER_BAND"]
    rng = np.random.default_rng(seed)
    selected = []
    for _, cell in frame.groupby(strata, observed=True):
        cases = cell[cell.BELOW]
        controls = cell[~cell.BELOW]
        n = min(len(cases), len(controls))
        if n:
            selected.append(cases.sample(n=n, random_state=int(rng.integers(2**31))))
            selected.append(controls.sample(n=n, random_state=int(rng.integers(2**31))))
    matched = pd.concat(selected, ignore_index=True) if selected else frame.iloc[0:0]
    return (
        matched.groupby(["DEFENDER_BAND", "BELOW"], observed=True)
        .agg(
            N=("AWARE_BELOW", "size"),
            AWARE_BELOW=("AWARE_BELOW", "mean"),
            AWARE_EXPOSURE=("AWARE_EXPOSURE", "mean"),
        )
        .reset_index()
        .rename(columns={"BELOW": "BASELINE_CASE"})
    )
