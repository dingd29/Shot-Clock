"""Reproducible, blinded possession-review sample for the team-profile validation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from possval.models.team_profiles import add_basketball_context

CASE_TEAMS = ("HOU", "ORL", "BOS")
MATCH_KEYS = [
    "SEASON",
    "CLOCK_PHASE_REVIEW",
    "SHOT_FAMILY",
    "POSSESSION_CONTEXT",
    "SCORE_STATE_REVIEW",
]


def _review_context(scored: pd.DataFrame) -> pd.DataFrame:
    frame = add_basketball_context(scored)
    frame["CLOCK_PHASE_REVIEW"] = pd.cut(
        frame.SECOND,
        [-1, 7, 15, 23],
        labels=["late", "middle", "early"],
        include_lowest=True,
    )
    margin = frame.SCORE_MARGIN.fillna(0.0)
    frame["SCORE_STATE_REVIEW"] = np.select(
        [margin <= -4, margin >= 4], ["behind 4+", "ahead 4+"], default="within 3"
    )
    return frame


def select_review_sample(
    scored: pd.DataFrame,
    n_per_case_team: int = 50,
    n_controls: int = 50,
    seed: int = 20260809,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Three 50-possession case groups plus 50 exact-context low-exposure controls.

    Boston is fixed as the strong-offense/high-capability comparison before film review: it was
    first in held-out offense and has the highest registered positive exposure. Cases are sampled
    from each team's upper quartile of positive early/middle-clock exposure, avoiding repeated
    shot events. Controls have zero exposure and match the registered coarse contexts exactly.
    """
    frame = _review_context(scored)
    frame = frame[
        frame.SECOND.between(8, 23)
        & frame.GAME_EVENT_ID.notna()
        & frame.GAME_ID.notna()
        & frame.PLAYER_ID.notna()
    ].copy()
    frame = frame.drop_duplicates(["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID"])
    rng = np.random.default_rng(seed)
    cases = []
    for team in CASE_TEAMS:
        team_pool = frame[frame.TEAM_ABBREVIATION.eq(team) & frame.EXPOSURE.gt(0)].copy()
        threshold = team_pool.EXPOSURE.quantile(0.75)
        team_pool = team_pool[team_pool.EXPOSURE.ge(threshold)]
        if len(team_pool) < n_per_case_team:
            raise ValueError(f"{team} has only {len(team_pool)} eligible high-exposure cases")
        selected = team_pool.sample(
            n=n_per_case_team,
            random_state=int(rng.integers(2**31)),
        ).copy()
        selected["SAMPLE_GROUP"] = f"case: {team}"
        cases.append(selected)
    case_table = pd.concat(cases, ignore_index=True)

    # Match controls to a random subset of the cases, without replacement. If an exact cell has
    # no control, that case is skipped and the deficit is filled by another case; match failures
    # are never relaxed silently.
    controls_pool = frame[frame.EXPOSURE.eq(0)].copy()
    used = set()
    controls = []
    shuffled_cases = case_table.iloc[rng.permutation(len(case_table))]
    for case in shuffled_cases.itertuples(index=False):
        mask = np.ones(len(controls_pool), dtype=bool)
        for key in MATCH_KEYS:
            mask &= controls_pool[key].astype(str).to_numpy() == str(getattr(case, key))
        candidates = controls_pool[mask & ~controls_pool.index.isin(used)]
        if candidates.empty:
            continue
        chosen = candidates.sample(n=1, random_state=int(rng.integers(2**31))).iloc[0]
        used.add(chosen.name)
        row = chosen.copy()
        row["SAMPLE_GROUP"] = "matched low-exposure control"
        row["MATCHED_CASE_TEAM"] = case.TEAM_ABBREVIATION
        controls.append(row)
        if len(controls) == n_controls:
            break
    if len(controls) != n_controls:
        raise ValueError(f"only {len(controls)} exact-context controls found")
    controls = pd.DataFrame(controls)
    sample = pd.concat([case_table, controls], ignore_index=True, sort=False)
    sample = sample.iloc[rng.permutation(len(sample))].reset_index(drop=True)
    sample.insert(0, "REVIEW_ID", [f"SC-{at:03d}" for at in range(1, len(sample) + 1)])
    season_label = sample.SEASON.astype(int).astype(str) + "-" + (
        (sample.SEASON.astype(int) + 1) % 100
    ).astype(str).str.zfill(2)
    sample["VIDEO_URL"] = (
        "https://www.nba.com/stats/events?CFID=&CFPARAMS=&GameEventID="
        + sample.GAME_EVENT_ID.astype(int).astype(str)
        + "&GameID="
        + sample.GAME_ID.astype(str).str.zfill(10)
        + "&Season="
        + season_label
        + "&flag=1"
    )

    key_columns = [
        "REVIEW_ID", "SAMPLE_GROUP", "MATCHED_CASE_TEAM", "TEAM_ABBREVIATION",
        "PLAYER_ID", "PLAYER_NAME", "SEASON", "GAME_ID", "PERIOD", "GAME_EVENT_ID",
        "VIDEO_URL", "SECOND", "CLOCK_PHASE_REVIEW", "SHOT_FAMILY",
        "POSSESSION_CONTEXT", "SCORE_STATE_REVIEW", "SHOT_VALUE", "REFERENCE", "GAP",
        "EXPOSURE",
    ]
    for column in key_columns:
        if column not in sample:
            sample[column] = np.nan
    key = sample[key_columns].copy()
    worksheet = sample[["REVIEW_ID", "VIDEO_URL"]].copy()
    for column in (
        "CODER_ID",
        "LIVE_ADVANTAGE_REMAINED",
        "CREDIBLE_CONTINUATION_AVAILABLE",
        "OPEN_TEAMMATE_OR_NEXT_ACTION",
        "BAILOUT_AFTER_FAILED_ACTION",
        "DEFENSIVE_PRESSURE_BLOCKED_CONTINUATION",
        "PRIMARY_ISSUE",
        "CONFIDENCE_1_TO_5",
        "NOTES",
    ):
        worksheet[column] = ""
    return worksheet, key


def score_review_labels(
    labels: pd.DataFrame,
    key: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Coder agreement and case-control differences after the key is unblinded."""
    binary = "CREDIBLE_CONTINUATION_AVAILABLE"
    frame = labels.merge(key[["REVIEW_ID", "SAMPLE_GROUP"]], on="REVIEW_ID", validate="many_to_one")
    overlap = frame.groupby("REVIEW_ID").filter(lambda group: group.CODER_ID.nunique() >= 2)
    pivot = overlap.pivot_table(
        index="REVIEW_ID", columns="CODER_ID", values=binary, aggfunc="first"
    )
    agreement_rows = []
    if pivot.shape[1] >= 2:
        from sklearn.metrics import cohen_kappa_score

        first, second = pivot.columns[:2]
        paired = pivot[[first, second]].dropna()
        agreement_rows.append(
            {
                "CODER_1": first,
                "CODER_2": second,
                "N_OVERLAP": len(paired),
                "COHEN_KAPPA": cohen_kappa_score(paired[first], paired[second]),
            }
        )
    adjudicated = frame.sort_values("CODER_ID").drop_duplicates("REVIEW_ID", keep="last")
    result = adjudicated.groupby("SAMPLE_GROUP").agg(
        N=(binary, "size"),
        CREDIBLE_CONTINUATION_RATE=(binary, "mean"),
    ).reset_index()
    return pd.DataFrame(agreement_rows), result
