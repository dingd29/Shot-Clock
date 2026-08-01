"""Command-line entry points for the data pipeline.

    python -m possval.pipeline ingest   --season 2024
    python -m possval.pipeline clock    --season 2024
    python -m possval.pipeline validate --season 2024
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from possval.clock import reconstruct_season
from possval.clock import validate as V
from possval.ingest import load_season
from possval.paths import PROCESSED, REPORTS, ensure_dirs

CLOCK_COLUMNS = [
    "GAME_ID", "EVENTNUM", "SHOT_CLOCK", "CHANCE_ID",
    "CHANCE_START_TYPE", "CLOCK_CONFIDENCE", "OFF_TEAM_ID",
]


def pbp_clock_path(season: int):
    return PROCESSED / f"pbp_clock_{season}.parquet"


def shots_clock_path(season: int):
    return PROCESSED / f"shots_clock_{season}.parquet"


def cmd_ingest(season: int) -> None:
    ensure_dirs()
    for dataset in ("nbastats", "shotdetail"):
        df = load_season(dataset, season)
        print(f"{dataset} {season}: {len(df):,} rows x {df.shape[1]} cols")


def cmd_clock(season: int, calibrate: bool = True) -> None:
    """Reconstruct one season. Calibration is re-run per season by default: the 14-second
    rule arrives in 2018-19 and feed conventions drift, so a delay fitted on one era should
    not be assumed to hold in another."""
    ensure_dirs()
    pbp = load_season("nbastats", season)

    delays = None
    if calibrate:
        from possval.clock.calibrate import estimate_delays

        delays, _ = estimate_delays(pbp, season)
        print(f"  calibrated delays: { {k: round(v, 1) for k, v in delays.items() if v} }")

    recon = reconstruct_season(pbp, season, delays=delays)
    recon.to_parquet(pbp_clock_path(season), index=False, compression="zstd")

    shots = load_season("shotdetail", season)
    clock = recon[CLOCK_COLUMNS].rename(columns={"EVENTNUM": "GAME_EVENT_ID"})
    merged = shots.merge(clock, on=["GAME_ID", "GAME_EVENT_ID"], how="left")
    usable = merged[merged.SHOT_CLOCK.notna()]
    usable.to_parquet(shots_clock_path(season), index=False, compression="zstd")

    print(f"events {len(recon):,} | shots {len(merged):,} | usable {len(usable):,} "
          f"({len(usable) / len(merged):.1%})")


def cmd_validate(season: int) -> None:
    if season != 2024:
        raise SystemExit("Official reference aggregates exist for 2024-25 only.")
    shots = pd.read_parquet(shots_clock_path(season))
    league, player = V.report(shots)

    pd.set_option("display.width", 200)
    print("=== league-wide: reconstructed vs official ===")
    print(
        league[
            ["BUCKET", "FGA_SHARE_recon", "FGA_SHARE_official",
             "SHARE_DIFF_PP", "FG_PCT_DIFF_PP", "EFG_DIFF_PP"]
        ].round(4).to_string(index=False)
    )
    print(f"\nmean |share error|: {league.SHARE_DIFF_PP.abs().mean():.3f} pp")
    print(f"mean |eFG error|:   {league.EFG_DIFF_PP.abs().mean():.3f} pp")

    print("\n=== per-player agreement ===")
    for key, value in player.items():
        print(f"  {key}: {value:.4f}" if isinstance(value, float) else f"  {key}: {value}")


def load_all_shots(first: int = 2015, last: int = 2024) -> pd.DataFrame:
    """Every reconstructed season stacked, with game state attached."""
    from possval.features.shots import attach_game_state

    frames = []
    for season in range(first, last + 1):
        path = shots_clock_path(season)
        if not path.exists():
            continue
        shots = pd.read_parquet(path)
        pbp = pd.read_parquet(
            pbp_clock_path(season),
            columns=[
                "GAME_ID", "EVENTNUM", "SCOREMARGIN",
                "PLAYER1_TEAM_ID", "PLAYER1_TEAM_ABBREVIATION",
            ],
        )
        # shotdetail carries TEAM_NAME but no abbreviation; play-by-play has both, so the
        # mapping is recovered from there rather than hard-coded.
        teams = (
            pbp[["PLAYER1_TEAM_ID", "PLAYER1_TEAM_ABBREVIATION"]]
            .dropna()
            .drop_duplicates("PLAYER1_TEAM_ID")
            .rename(
                columns={
                    "PLAYER1_TEAM_ID": "TEAM_ID",
                    "PLAYER1_TEAM_ABBREVIATION": "TEAM_ABBREVIATION",
                }
            )
        )
        shots = shots.merge(teams, on="TEAM_ID", how="left")
        shots["IS_HOME"] = (shots.TEAM_ABBREVIATION == shots.HTM).astype(int)
        frames.append(attach_game_state(shots, pbp))
    if not frames:
        raise SystemExit("no reconstructed seasons found — run `make clock` first")
    return pd.concat(frames, ignore_index=True)


def cmd_train(first: int, last: int) -> None:
    from possval.features import build_shot_features
    from possval.models.xpts import evaluate_xpts, train_xpts

    shots = load_all_shots(first, last)
    print(f"shots: {len(shots):,} across seasons {shots.SEASON.min()}-{shots.SEASON.max()}")

    features = build_shot_features(shots)
    result = train_xpts(features)

    pd.set_option("display.width", 200)
    print("\n=== out-of-sample performance (test = 2024-25) ===")
    print(evaluate_xpts(result).round(4).to_string(index=False))
    print("\n=== top features by gain ===")
    print(result.feature_importance.head(15).to_string(index=False))
    print("\n=== calibration (should track the diagonal) ===")
    print(result.calibration.round(4).to_string(index=False))

    out = PROCESSED / "xpts_metrics.csv"
    evaluate_xpts(result).to_csv(out, index=False)
    result.feature_importance.to_csv(PROCESSED / "xpts_importance.csv", index=False)
    print(f"\nwrote {out}")


def cmd_score(first: int, last: int) -> None:
    """Train xPTS, score every shot, and write the graded player tables."""
    from possval.features import build_shot_features
    from possval.models.grade import grade_by_clock, grade_players, late_clock_specialists
    from possval.models.xpts import predict_xpts, train_xpts

    shots = load_all_shots(first, last)
    features = build_shot_features(shots)
    result = train_xpts(features)

    features["XPTS"] = predict_xpts(result, features)
    keep = [
        "PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "SEASON", "GAME_ID",
        "SHOT_CLOCK", "CHANCE_START_TYPE", "SHOT_ZONE_BASIC", "SHOT_DISTANCE",
        "IS_3", "IS_HOME", "SHOT_MADE_FLAG", "PTS", "XPTS",
    ]
    # Fail loudly rather than filtering: quietly dropping an absent column is how
    # TEAM_ABBREVIATION went missing here once already, taking IS_HOME down with it.
    missing = [c for c in keep if c not in features.columns]
    if missing:
        raise SystemExit(f"scored output is missing expected columns: {missing}")
    scored = features[keep]
    scored.to_parquet(PROCESSED / "shots_scored.parquet", index=False, compression="zstd")

    test = scored[scored.SEASON == 2024]
    grade_players(test, by_season=False).to_csv(PROCESSED / "grade_players_2024.csv", index=False)
    grade_by_clock(test).to_csv(PROCESSED / "grade_by_clock_2024.csv", index=False)
    late_clock_specialists(test).to_csv(PROCESSED / "late_clock_2024.csv", index=False)

    print(f"scored {len(scored):,} shots; wrote grade tables for 2024-25")


def lineups_path(season: int):
    return PROCESSED / f"lineups_{season}.parquet"


def cmd_lineups(first: int, last: int) -> None:
    """Derive on-court lineups for each season and validate the result."""
    from possval.features.lineups import lineups_for_season, validate_lineups

    for season in range(first, last + 1):
        if not pbp_clock_path(season).exists():
            continue
        pbp = load_season("nbastats", season)
        lineups = lineups_for_season(pbp)
        report = validate_lineups(lineups)
        lineups.to_parquet(lineups_path(season), index=False, compression="zstd")
        failed = len(lineups.attrs.get("failed_games", []))
        print(
            f"{season}: {len(lineups):,} events | ten distinct on "
            f"{report['pct_ten_distinct']:.2%} | unresolved games {failed}",
            flush=True,
        )


def cmd_lineup_test(first: int, last: int) -> None:
    """Retest the creation-overlap hypothesis at five-man lineup level."""
    from possval.models.creation import creation_profiles
    from possval.models.lineup_synergy import (
        build_lineup_panel,
        lineup_efficiency,
        offensive_lineups,
        player_team_map,
        specification_curve,
    )

    shots = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    profiles = {
        season: creation_profiles(shots[shots.SEASON == season], min_attempts=150)
        for season in range(first, last + 1)
        if (shots.SEASON == season).any()
    }

    frames = []
    for season in range(first, last + 1):
        if not lineups_path(season).exists():
            continue
        lineups = pd.read_parquet(lineups_path(season))
        pbp = pd.read_parquet(
            pbp_clock_path(season),
            columns=[
                "GAME_ID", "EVENTNUM", "EVENTMSGTYPE", "PERIOD", "CHANCE_ID",
                "OFF_TEAM_ID", "PLAYER1_ID", "PLAYER1_TEAM_ID", "HOMEDESCRIPTION",
                "VISITORDESCRIPTION",
            ],
        )
        merged = pbp.merge(lineups, on=["GAME_ID", "EVENTNUM"], how="inner")
        merged["SEASON"] = season
        # Shot value and free-throw result are derived inside `event_points`, from the same
        # descriptions, so they are no longer precomputed here.
        frames.append(offensive_lineups(merged, player_team_map(pbp)))
        print(f"  {season}: {len(merged):,} events with lineups", flush=True)

    events = pd.concat(frames, ignore_index=True)
    efficiency = lineup_efficiency(events)
    print(f"\nlineup-seasons with >=100 chances: {len(efficiency):,}")

    prior = (
        shots.groupby(["PLAYER_ID", "SEASON"])
        .agg(PTS=("PTS", "sum"), FGA=("PTS", "size"))
        .reset_index()
    )
    prior["PRIOR_PPA"] = prior.PTS / prior.FGA
    prior_lookup = prior.set_index("PLAYER_ID").PRIOR_PPA.groupby(level=0).mean().to_frame()

    panel = build_lineup_panel(efficiency, profiles, prior_lookup)
    panel.to_parquet(PROCESSED / "lineup_panel.parquet", index=False)
    print(f"panel rows: {len(panel):,}")

    # A single specification would be misleading here: the headline estimate is significant
    # under some reasonable choices and not others, and that fragility is the actual result.
    # The whole curve is printed so a reader sees the spread rather than the best cell.
    curve = specification_curve(panel)
    print(f"\n=== lineup-level overlap test — specification curve "
          f"(mean {np.average(panel.PTS_PER_CHANCE, weights=panel.CHANCES):.4f} pts/chance) ===")
    print(curve.round(4).to_string(index=False))
    curve.to_csv(REPORTS / "lineup_overlap_specifications.csv", index=False)
    print(f"\nwritten: {REPORTS / 'lineup_overlap_specifications.csv'}")


def cmd_backfill(first: int, last: int) -> None:
    """Ingest + reconstruct every season in [first, last]."""
    for season in range(first, last + 1):
        print(f"=== {season}-{str(season + 1)[-2:]} ===", flush=True)
        try:
            cmd_clock(season)
        except Exception as exc:  # keep going; one bad season shouldn't kill the backfill
            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="possval.pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("ingest", "clock", "validate"):
        p = sub.add_parser(name)
        p.add_argument("--season", type=int, default=2024, help="season start year")
    for name in ("backfill", "train", "score", "lineups", "lineup-test"):
        p = sub.add_parser(name)
        p.add_argument("--first", type=int, default=2015)
        p.add_argument("--last", type=int, default=2024)

    args = parser.parse_args()
    ranged = {
        "backfill": cmd_backfill,
        "train": cmd_train,
        "score": cmd_score,
        "lineups": cmd_lineups,
        "lineup-test": cmd_lineup_test,
    }
    if args.command in ranged:
        ranged[args.command](args.first, args.last)
        return
    {"ingest": cmd_ingest, "clock": cmd_clock, "validate": cmd_validate}[args.command](
        args.season
    )


if __name__ == "__main__":
    main()
