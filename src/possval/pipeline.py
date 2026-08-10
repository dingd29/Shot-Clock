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
        # Carried so downstream consumers can drop buzzer-beater heaves without
        # re-deriving the rule. See features/shots.EXPIRING_SECONDS.
        "PERIOD_SECONDS_REMAINING", "GAME_CLOCK_EXPIRING",
        # Game state, so the stopping model can condition on it: an unconditional V(t) has
        # blowouts and late-game fouling folded into it.
        "PERIOD", "SCORE_MARGIN",
        # Keys back to the chance and the play-by-play event, so shots can be joined to
        # on-court lineups without re-deriving anything.
        "GAME_EVENT_ID", "CHANCE_ID",
    ]
    # Fail loudly rather than filtering: quietly dropping an absent column is how
    # TEAM_ABBREVIATION went missing here once already, taking IS_HOME down with it.
    missing = [c for c in keep if c not in features.columns]
    if missing:
        raise SystemExit(f"scored output is missing expected columns: {missing}")
    scored = features[keep]
    scored.to_parquet(PROCESSED / "shots_scored.parquet", index=False, compression="zstd")

    test = scored[scored.SEASON == 2024]
    # Both clock-conditioned tables drop buzzer-beater heaves, matching cmd_stopping and the
    # rule in features/shots.EXPIRING_SECONDS. A third of shots at <=1s on the shot clock also
    # have <3s of game clock, so leaving them in loads the late-clock bucket with attempts that
    # were never shot-clock decisions. grade_players is unconditioned and keeps them.
    live = test[test.GAME_CLOCK_EXPIRING == 0]
    grade_players(test, by_season=False).to_csv(PROCESSED / "grade_players_2024.csv", index=False)
    grade_by_clock(live).to_csv(PROCESSED / "grade_by_clock_2024.csv", index=False)
    late_clock_specialists(live).to_csv(PROCESSED / "late_clock_2024.csv", index=False)

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


def cmd_synergy(first: int, last: int) -> None:
    """Creation overlap against offensive efficiency, at team-season level.

    This is the test finding 11 reports first, and it previously had no entry point at all:
    `make synergy` ran the *lineup* version, so the team-season table could not be reproduced
    from the repo and which outcome column produced it was not recoverable. Every outcome is
    printed here rather than one, because the choice between them is exactly the degree of
    freedom a reader should be able to see.
    """
    from possval.models.synergy import fit_overlap_effect, team_possessions, team_season_panel

    shots = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    shots = shots[(shots.SEASON >= first) & (shots.SEASON <= last)]

    frames = []
    for season in range(first, last + 1):
        path = pbp_clock_path(season)
        if not path.exists():
            continue
        pbp = pd.read_parquet(
            path,
            columns=[
                "GAME_ID", "CHANCE_ID", "CHANCE_START_TYPE", "EVENTMSGTYPE",
                "OFF_TEAM_ID", "PLAYER1_TEAM_ID", "PLAYER1_TEAM_ABBREVIATION",
                "HOMEDESCRIPTION", "VISITORDESCRIPTION",
            ],
        )
        # `shots_scored.parquet` carries the abbreviation but not TEAM_ID, so joining
        # possessions on TEAM_ID silently produced an all-NaN column and ORTG_FG was never
        # computed at all. The mapping comes from play-by-play, which has both.
        abbreviations = (
            pbp[["PLAYER1_TEAM_ID", "PLAYER1_TEAM_ABBREVIATION"]]
            .dropna()
            .drop_duplicates("PLAYER1_TEAM_ID")
            .set_index("PLAYER1_TEAM_ID")
            .PLAYER1_TEAM_ABBREVIATION
        )
        counts = team_possessions(pbp).assign(SEASON=season)
        counts["TEAM_ABBREVIATION"] = counts.TEAM_ID.map(abbreviations)
        frames.append(counts.dropna(subset=["TEAM_ABBREVIATION"]))
        print(f"  {season}: possessions for {len(frames[-1])} teams", flush=True)
    possessions = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    pd.set_option("display.width", 200)
    tables = []
    for top_n in (3, 4, 8):
        panel = team_season_panel(shots, possessions, top_n=top_n)
        rows = []
        for outcome in ("PTS_PER_FGA", "PTS_VS_XPTS", "ORTG_FG"):
            if outcome not in panel or panel[outcome].notna().sum() < 30:
                continue
            fit = fit_overlap_effect(panel, outcome=outcome)
            overlap = fit["coefficients"].set_index("term").loc["overlap"]
            rows.append(
                {
                    "top_n": top_n,
                    "outcome": outcome,
                    "n": fit["n"],
                    "r2": fit["r2"],
                    # Per +1 SD of overlap, so the three outcomes are on comparable footing.
                    "per_sd": overlap.estimate * fit["overlap_sd"],
                    "estimate": overlap.estimate,
                    "std_error": overlap.std_error,
                    "t": overlap.t,
                }
            )
        table = pd.DataFrame(rows)
        print(f"\n=== top-{top_n} creators: {len(panel)} team-seasons ===")
        print(table.round(4).to_string(index=False))
        tables.append(table)
        if top_n == 8:
            panel.to_csv(REPORTS / "synergy_team_season_panel.csv", index=False)

    curve = pd.concat(tables, ignore_index=True)
    curve.to_csv(REPORTS / "synergy_team_season.csv", index=False)

    hits = curve[curve.t.abs() >= 2]
    print(f"\n{len(hits)} of {len(curve)} specifications reach |t| = 2 on overlap.")
    if not hits.empty:
        # Sign matters more than significance here. The redundancy hypothesis predicts
        # *negative*: more overlap, worse offense. Positive is what the construction produces
        # on its own, since similar players concentrate early in the clock and early chances
        # score better. See findings 11.
        print(f"  signs: {sorted(np.sign(hits.estimate).unique().tolist())} "
              f"(the hypothesis predicts negative)")
    print(f"written: {REPORTS / 'synergy_team_season.csv'}, "
          f"{REPORTS / 'synergy_team_season_panel.csv'}")


def cmd_lineup_test(first: int, last: int) -> None:
    """Retest the creation-overlap hypothesis at five-man lineup level."""
    from possval.models.creation import creation_profiles
    from possval.models.lineup_synergy import (
        build_lineup_panel,
        head_to_head,
        lineup_efficiency,
        offensive_lineups,
        player_team_map,
        specification_curve,
        usage_rates,
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

    # Points per attempt over strictly *earlier* seasons, matching synergy.py's team-season
    # version. An earlier build here grouped over every season including the outcome season and
    # then collapsed to one scalar per player, which made the only quality control in the
    # specification curve both contemporaneous with its outcome and constant over a decade.
    by_season = (
        shots.groupby(["PLAYER_ID", "SEASON"])
        .agg(PTS=("PTS", "sum"), FGA=("PTS", "size"))
        .reset_index()
        .sort_values(["PLAYER_ID", "SEASON"])
    )
    cumulative = by_season.groupby("PLAYER_ID")[["PTS", "FGA"]].cumsum() - by_season[
        ["PTS", "FGA"]
    ]
    by_season["PRIOR_PPA"] = (cumulative.PTS / cumulative.FGA.replace(0, np.nan)).to_numpy()
    prior_lookup = (
        by_season.dropna(subset=["PRIOR_PPA"])
        .set_index(["PLAYER_ID", "SEASON"])[["PRIOR_PPA"]]
    )

    panel = build_lineup_panel(efficiency, profiles, prior_lookup, usage=usage_rates(events))
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

    # The project's actual claim: that *when* players want the ball carries information the
    # incumbent *how much* measure does not. Racing them needs identical rows.
    race = head_to_head(panel, fixed_effects="team_season", cluster="TEAM_SEASON")
    print("\n=== head-to-head: creation profiles vs the incumbent usage measure ===")
    print("(coefficients are points per chance per +1 SD; team-season FE, clustered)")
    print(race.round(4).to_string(index=False))
    race.to_csv(REPORTS / "lineup_overlap_head_to_head.csv", index=False)
    print(f"\nwritten: {REPORTS / 'lineup_overlap_specifications.csv'}, "
          f"{REPORTS / 'lineup_overlap_head_to_head.csv'}")


def cmd_backfill(first: int, last: int) -> None:
    """Ingest + reconstruct every season in [first, last]."""
    for season in range(first, last + 1):
        print(f"=== {season}-{str(season + 1)[-2:]} ===", flush=True)
        try:
            cmd_clock(season)
        except Exception as exc:  # keep going; one bad season shouldn't kill the backfill
            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)


def cmd_ablate(first: int, last: int) -> None:
    """Value feature groups by refitting without them."""
    from possval.features import build_shot_features
    from possval.models.xpts import ABLATION_GROUPS, ABLATION_GROUPS_FINE, ablate_seeds

    features = build_shot_features(load_all_shots(first, last))
    groups = {**ABLATION_GROUPS, **ABLATION_GROUPS_FINE}
    result = ablate_seeds(features, groups)
    seeds = result.attrs["seeds"]

    base = result[result.removed == "full_model"].iloc[0]
    result["share_of_gain"] = result.logloss_cost / result[
        result.removed.isin(ABLATION_GROUPS)
    ].logloss_cost.sum()

    pd.set_option("display.width", 200)
    print(f"\n=== ablation (test = 2024-25, full-model log loss {base.log_loss:.5f}) ===")
    print(f"mean over {len(seeds)} seeds; sd is across seeds, not a sampling interval.")
    print("share_of_gain is over the four coarse groups only; the fine rows overlap them.")
    coarse = result[result.removed.isin(ABLATION_GROUPS)]
    fine = result[result.removed.isin(ABLATION_GROUPS_FINE)]
    cols = ["removed", "logloss_cost", "logloss_cost_sd", "auc_cost", "share_of_gain"]
    print("\ncoarse groups:")
    print(coarse[cols].sort_values("logloss_cost", ascending=False)
          .round(5).to_string(index=False))
    print("\nfine detail (overlapping; not comparable across groups):")
    print(fine[cols[:-1]].sort_values("logloss_cost", ascending=False)
          .round(5).to_string(index=False))
    result.attrs["per_seed"].to_csv(REPORTS / "ablation_by_seed.csv", index=False)

    out = REPORTS / "ablation.csv"
    result.to_csv(out, index=False)
    print(f"\nwritten: {out}")


def cmd_stopping(first: int, last: int, n_null_draws: int = 50) -> None:
    """Shooting as optimal stopping: continuation value, exercise boundary, relaxation."""
    from possval.models.stopping import (
        chance_panel,
        continuation_value,
        exercise_boundary,
        exercise_gap,
        free_throw_bias,
        player_exercise,
        relaxation,
        robustness,
        start_clip_diagnostic,
        team_relaxation,
        team_relaxation_null,
    )

    pd.set_option("display.width", 200)
    panel_path = PROCESSED / "chance_panel.parquet"
    if panel_path.exists():
        panel = pd.read_parquet(panel_path)
    else:
        panel = chance_panel(first, last)
        panel.to_parquet(panel_path, index=False)
    print(f"chances: {len(panel):,}")

    shots = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    shots = shots[shots.GAME_CLOCK_EXPIRING == 0]

    values = continuation_value(panel)
    print("\n=== continuation value V(t): expected points from declining to shoot ===")
    print(values.round(4).to_string(index=False))

    gap = exercise_gap(shots, values)
    print("\n=== taken shots against the value they gave up ===")
    print(gap.round(4).to_string(index=False))

    boundary = exercise_boundary(shots, values)
    print("\n=== implied exercise boundary (5th pct of accepted) vs optimal ===")
    print(boundary.round(4).to_string(index=False))

    ratios = relaxation(shots, values)
    print("\n=== does the boundary relax as fast as V(t) collapses? ===")
    print("(the boundary's *level* is not identified — its shape is; hence every quantile)")
    print(ratios.round(4).to_string(index=False))

    # The null costs a minute and is not optional: two thirds of the raw team spread is the
    # noise of splitting one dataset thirty ways, and the raw ranking is misleading without it.
    # 50 rather than 20: the null is itself an estimate, and the repo's own sensitivity showed
    # it still moving between 10 and 20 draws.
    null = team_relaxation_null(shots, panel, n_draws=n_null_draws)
    teams = team_relaxation(shots, panel, null_sd=null["null_mean"])
    print(f"\n=== relaxation ratio by team (null spread {null['null_mean']:.4f} from "
          f"{n_null_draws} permutations; signal share {teams.attrs['signal_share']:.0%}) ===")
    print(f"null spread {null['null_mean']:.4f} +/- {null['null_sd']:.4f} across draws "
          f"(5th-95th {null['null_p05']:.4f}-{null['null_p95']:.4f})")
    print(pd.concat([teams.head(5), teams.tail(5)]).round(3).to_string(index=False))
    teams.to_csv(REPORTS / "stopping_team_relaxation.csv", index=False)

    checks = robustness(shots, panel)
    print("\n=== robustness: is it garbage time, or one season? ===")
    print(checks.round(3).to_string(index=False))
    checks.to_csv(REPORTS / "stopping_robustness.csv", index=False)

    players = player_exercise(shots[shots.SEASON == shots.SEASON.max()], values)
    print(f"\n=== per-player late-clock surplus (shrunk; signal share "
          f"{players.attrs['signal_share']:.2f}) ===")
    print("high scores track rim share, not judgment; see findings 7")
    print(pd.concat([players.head(5), players.tail(3)])[
        ["PLAYER_NAME", "FGA_LATE", "SURPLUS", "SHRUNK_SURPLUS"]
    ].round(3).to_string(index=False))
    players.to_csv(REPORTS / "stopping_player_exercise.csv", index=False)

    uplift = free_throw_bias(panel)
    print(f"\nfree-throw uplift to V(t): mean {uplift.FT_UPLIFT.mean():+.4f} points "
          "(excluded from the headline, which makes it conservative)")

    clip = start_clip_diagnostic(panel)
    print(f"\nchance-start clock: {clip['clipped_pct']:.1f}% land on the 24 clip, of which "
          f"{clip['beyond_delay_pct']:.2f}% sit beyond what the 2s inbound delay explains "
          f"(max {clip['max']:.0f}s). The second figure is the one that would signal a "
          "non-adjacent predecessor.")

    for name, frame in [
        ("stopping_continuation_value", values), ("stopping_exercise_gap", gap),
        ("stopping_boundary", boundary), ("stopping_relaxation", ratios),
    ]:
        frame.to_csv(REPORTS / f"{name}.csv", index=False)
    print(f"\nwritten: {REPORTS}/stopping_*.csv")


def cmd_scorecard(season: int) -> None:
    """Score the pre-registered projection against results so far."""
    from datetime import date

    from possval.models.scorecard import scorecard

    pd.set_option("display.width", 200)
    result = scorecard(season)
    print(f"completed games: {result['n_games']:,}")
    if result["n_games"] == 0:
        print("\nSeason has not started. The harness is wired and will score from game one.")
        return

    print("\n=== game-level scores ===")
    print(result["scores"].round(4).to_string(index=False))
    print("\n=== calibration ===")
    print(result["calibration"].round(3).to_string(index=False))
    print("\n=== win totals: projected against current pace ===")
    print(result["win_totals"].round(1).to_string(index=False))

    # Appended rather than overwritten: the point of a pre-registration is the running record,
    # and a file that only holds the latest number cannot show whether it moved.
    log = REPORTS / "scorecard_log.csv"
    row = result["scores"].assign(date=date.today().isoformat(), season=season)
    header = not log.exists()
    row.to_csv(log, mode="a", header=header, index=False)
    result["calibration"].to_csv(REPORTS / "scorecard_calibration.csv", index=False)
    result["win_totals"].to_csv(REPORTS / "scorecard_win_totals.csv", index=False)
    print(f"\nappended to {log}")


def cmd_winprob(first: int, last: int) -> None:
    """Does the reconstructed shot clock add anything to a live win-probability model?"""
    from possval.models.winprob import (
        bootstrap_difference,
        compare,
        compare_seeds,
        load_state,
    )

    pd.set_option("display.width", 200)
    path = PROCESSED / "winprob_state.parquet"
    if path.exists():
        state = pd.read_parquet(path)
    else:
        state = load_state(first, last)
        state.to_parquet(path, index=False)
    print(f"events: {len(state):,} over {state.SEASON.nunique()} seasons")

    scores = compare(state)
    print("\n=== live win probability, with and without shot clock (test = 2024-25) ===")
    print(scores.round(5).to_string(index=False))

    base = scores[scores.model == "base"].iloc[0]
    with_clock = scores[scores.model == "base + shot clock"].iloc[0]
    gain = base.log_loss - with_clock.log_loss
    print(f"\nlog-loss improvement {gain:+.6f} ({100 * gain / base.log_loss:+.3f}%)")

    across = compare_seeds(state)
    print(f"\nrefit over {len(across)} seeds: gain {across.attrs['gain_mean']:+.6f} "
          f"+/- {across.attrs['gain_sd']:.6f}, positive in {across.attrs['share_positive']:.0%}")
    across.to_csv(REPORTS / "winprob_by_seed.csv", index=False)

    interval = bootstrap_difference(state, n_boot=300)
    print(f"game-clustered bootstrap over {interval['n_games']} games: "
          f"95% CI [{interval['ci_low']:+.6f}, {interval['ci_high']:+.6f}], "
          f"{interval['share_positive']:.0%} of draws positive")
    print("\nReliably non-zero and practically nil; see findings 9.")

    scores.to_csv(REPORTS / "winprob_comparison.csv", index=False)
    pd.DataFrame([interval]).to_csv(REPORTS / "winprob_bootstrap.csv", index=False)
    print(f"\nwritten: {REPORTS}/winprob_*.csv")


def cmd_project(n_sims: int, games: int | None, rating_sd: float | None) -> None:
    """Calibrate DPM onto the rating scale, then simulate 2026-27 for all thirty teams."""
    from possval.models.dpm_calibration import calibrate, calibration_panel, slopes_differ
    from possval.models.league import (
        CONFERENCES,
        PHILADELPHIA,
        aging_sensitivity,
        project_league,
    )

    pd.set_option("display.width", 200)
    fits = calibrate()
    print("=== DPM -> rating calibration (2025-26, n=30) ===")
    print(fits.round(3).to_string(index=False))

    test = slopes_differ(calibration_panel())
    print(
        f"\noffence and defence against a common target: {test['offence_slope']:.3f} vs "
        f"{test['defence_slope']:.3f}, F={test['f']:.2f}, p={test['p']:.3f} "
        "-> one slope, applied to the total"
    )

    result = project_league(n_sims=n_sims, games=games, extra_rating_sd=rating_sd)
    summary = result["summary"]
    summary.insert(0, "CONF", [CONFERENCES[team] for team in summary.index])

    label = "minutes as played" if games is None else f"health-adjusted to {games} games"
    print(f"\n=== projected 2026-27 ({label}, rating_sd={result['rating_sd']:.2f}, "
          f"{result['n_sims']:,} sims) ===")
    print(summary.round(3).to_string())

    philadelphia = summary.loc[PHILADELPHIA]
    print(
        f"\n{PHILADELPHIA}: rating {philadelphia.RATING:+.2f} | "
        f"wins {philadelphia.WINS:.1f} ({philadelphia.WINS_P10:.0f}-{philadelphia.WINS_P90:.0f}) | "
        f"title {philadelphia.TITLE:.1%} | "
        f"rank {list(summary.index).index(PHILADELPHIA) + 1} of 30"
    )

    # No aging is applied — see `aging_sensitivity` for why — so the question of whether
    # that omission changes the answer is settled by sweeping it rather than asserted.
    sweep = aging_sensitivity(games=games)
    print("\n=== if LeBron declines (no aging is applied; this is the sensitivity) ===")
    print(sweep.round(3).to_string(index=False))

    out = REPORTS / "league_projection_2026_27.csv"
    summary.to_csv(out)
    sweep.to_csv(REPORTS / "aging_sensitivity.csv", index=False)
    print(f"\nwritten: {out}, {REPORTS / 'aging_sensitivity.csv'}")


def cmd_rulechange(first: int, last: int) -> None:
    """The 2018-19 shot-clock rule as a difference-in-differences."""
    from possval.models.rulechange import report

    pd.set_option("display.width", 200)
    result = report(first, last)
    print(f"chances: {result['n_chances']:,} ({result['n_treated']:,} treated)"
          f"; dropped seasons: {result['dropped_seasons'] or 'none'}")

    print("\n=== difference-in-differences (season-clustered) ===")
    print(result["estimates"].round(4).to_string(index=False))

    print("\n=== play-by-play timestamp granularity (the 2017-18 artifact) ===")
    print(result["timestamp_granularity"].round(2).to_string())
    result["timestamp_granularity"].to_csv(REPORTS / "rulechange_timestamps.csv")

    print("\n=== sensitivity to the pre-period baseline ===")
    print(result["baseline_sensitivity"].round(4).to_string())

    for outcome, study in result["event_studies"].items():
        print(f"\n=== event study: {outcome} ===")
        print(study.round(4).to_string(index=False))
        study.to_csv(REPORTS / f"rulechange_event_study_{outcome.lower()}.csv", index=False)

    result["estimates"].to_csv(REPORTS / "rulechange_did.csv", index=False)
    print(f"\nwritten: {REPORTS / 'rulechange_did.csv'} and event studies")


def cmd_ratings(first: int, last: int) -> None:
    """Season SRS for every team, written where the projection and scorecard expect it.

    `srs_ratings.parquet` is read by `league.py`, `dpm_calibration.py` and `scorecard.py` and
    was previously written by nothing, so a clean checkout could not run `project` or
    `scorecard` at all. This is the missing step; it belongs before both of them.

    `last` runs one season past the clock reconstruction by default. 2025-26 has no
    `pbp_clock_*` file and comes from the v3 feed, and the projection needs it as the prior
    season.
    """
    from possval.models.ratings import all_game_results, season_ratings

    games = all_game_results(first, last)
    ratings = season_ratings(games)

    out = PROCESSED / "srs_ratings.parquet"
    ratings.to_parquet(out, index=False, compression="zstd")
    games.to_parquet(PROCESSED / "game_results.parquet", index=False, compression="zstd")

    pd.set_option("display.width", 200)
    print(f"{len(games):,} games over {games.SEASON.nunique()} seasons")
    print("\n=== SRS spread by season ===")
    spread = ratings.groupby("SEASON").SRS.agg(["min", "max", "std"]).round(2)
    print(spread.to_string())
    print(f"\nwritten: {out}")


def cmd_rebound(first: int, last: int) -> None:
    """Conditional rebound rates, and what pricing the rebound option does to finding 7.

    `stopping.py` compares a shot's `XPTS` against `V(t)`. An offensive rebound starts a new
    chance, so the points it goes on to produce sit in neither side of that comparison. This
    prices the option on both sides and reports how far the headline moves.
    """
    from possval.models.rebound import (
        LOOKUP_KEYS,
        lookup_stability,
        possession_panel,
        published_comparison,
        rebound_rates,
        reprice_shots,
        retention_lookup,
        second_chance_by_clock,
        second_chance_value,
        shot_outcomes,
        start_type_advantage,
    )
    from possval.models.stopping import continuation_value, exercise_boundary, relaxation

    pd.set_option("display.width", 200)
    outcomes_path = PROCESSED / "shot_outcomes.parquet"
    if outcomes_path.exists():
        outcomes = pd.read_parquet(outcomes_path)
    else:
        outcomes = shot_outcomes(first, last)
        outcomes.to_parquet(outcomes_path, index=False, compression="zstd")
    print(f"attempts: {len(outcomes):,} | resolved: {outcomes.RESOLVED.mean():.2%}")

    print("\n=== the two rates, and how they compare to published ORB% ===")
    print(published_comparison(outcomes).round(4).to_string(index=False))
    print("these are different quantities; see the docstring for why neither is wrong")

    for keys in (["SHOT_ZONE_BASIC"], ["CLOCK_BAND"]):
        table = rebound_rates(outcomes, keys)
        print(f"\n=== rebound rates by {', '.join(keys)} ===")
        print(table.round(4).to_string(index=False))
        table.to_csv(REPORTS / f"rebound_by_{'_'.join(keys).lower()}.csv", index=False)

    cells = rebound_rates(outcomes, LOOKUP_KEYS)
    cells.to_csv(REPORTS / "rebound_lookup.csv", index=False)
    stability = lookup_stability(outcomes)
    print(f"\nlookup stability (fit through 2022-23, scored on 2023-24 and 2024-25): "
          f"{stability['n_cells']} cells, mean |error| {stability['mean_abs_error_pp']:.2f}pp, "
          f"max {stability['max_abs_error_pp']:.2f}pp, r = {stability['correlation']:.3f}")

    panel = possession_panel(pd.read_parquet(PROCESSED / "chance_panel.parquet"))
    values = second_chance_value(panel)
    live = panel[(panel.START_TYPE == "off_rebound") & ~panel.PERIOD_EXPIRED]
    second_chance = float(live.PTS_POSS.mean())
    print("\n=== what a second chance is worth ===")
    print(f"off-rebound chance: {values['v_off_rebound']:.4f} pts from a mean start of "
          f"{values['mean_start_sc_off_rebound']:.1f}s")
    print(f"fresh possession:   {values['v_fresh']:.4f} pts from a mean start of "
          f"{values['mean_start_sc_fresh']:.1f}s")
    print(f"off-rebound chance including its own further rebounds: {second_chance:.4f}")

    print("\n=== is a second chance worth more than a fresh possession? ===")
    print("only at the same start clock; the raw gap is composition, not advantage")
    advantage = start_type_advantage(panel[~panel.PERIOD_EXPIRED])
    print(advantage.round(4).to_string(index=False))
    advantage.to_csv(REPORTS / "rebound_start_type_advantage.csv", index=False)

    print("\n=== value of a second chance by the clock it gets (post-2018) ===")
    by_clock = second_chance_by_clock(panel[~panel.PERIOD_EXPIRED])
    print(by_clock.round(4).to_string(index=False))
    by_clock.to_csv(REPORTS / "rebound_second_chance_by_clock.csv", index=False)

    shots = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    shots = shots[shots.GAME_CLOCK_EXPIRING == 0]
    priced = reprice_shots(shots, retention_lookup(outcomes), second_chance)

    chance_level = continuation_value(panel, outcome="PTS_FG")
    possession_level = continuation_value(panel, outcome="PTS_POSS")
    published = relaxation(priced, chance_level, value_column="XPTS")
    repriced = relaxation(priced, possession_level, value_column="FULL_VALUE")
    comparison = pd.DataFrame(
        {
            "quantile": published["quantile"].to_numpy(),
            "ratio_published": published.relaxation_ratio.to_numpy(),
            "ratio_repriced": repriced.relaxation_ratio.to_numpy(),
            "value_drop_published": published.value_drop.to_numpy(),
            "value_drop_repriced": repriced.value_drop.to_numpy(),
        }
    )
    print("\n=== finding 7's relaxation ratio, with the rebound option priced ===")
    print(comparison.round(4).to_string(index=False))
    print(f"published: {published.relaxation_ratio.min():.3f}-"
          f"{published.relaxation_ratio.max():.3f}  ->  "
          f"re-priced: {repriced.relaxation_ratio.min():.3f}-"
          f"{repriced.relaxation_ratio.max():.3f}")
    comparison.to_csv(REPORTS / "rebound_repriced_relaxation.csv", index=False)

    boundary = exercise_boundary(priced, possession_level, value_column="FULL_VALUE")
    boundary.to_csv(REPORTS / "rebound_repriced_boundary.csv", index=False)


# The pre-registered split, hard-coded rather than passed in. A window that can be chosen at
# the command line is a window that can be chosen after seeing a result.
SITUATIONAL_WINDOWS = {"explore": (2015, 2021), "holdout": (2022, 2023)}


def cmd_twoforone(window: str) -> None:
    """H6 from `reports/preregistration_twoforone.md`.

    Run `--window explore` first. `--window holdout` is a one-shot confirmation.
    """
    from possval.models.rebound import possession_panel
    from possval.models.stopping import chance_panel, continuation_value
    from possval.models.twoforone import (
        FEASIBLE_FROM,
        cost_of_shooting_early,
        discontinuity,
        profile,
        threshold_sweep,
    )
    from possval.models.twoforone import window as build_window

    first, last = SITUATIONAL_WINDOWS[window]
    pd.set_option("display.width", 200)
    print(f"=== window: {window} ({first}-{str(first + 1)[-2:]} to "
          f"{last}-{str(last + 1)[-2:]}) ===")

    panel_path = PROCESSED / "chance_panel.parquet"
    panel = pd.read_parquet(panel_path) if panel_path.exists() else chance_panel(2015, 2024)
    panel = panel[panel.SEASON.between(first, last)]
    built = build_window(panel)
    print(f"{len(built):,} end-of-period chances in the 24-45s window, "
          f"{built.GAME_ID.nunique():,} games")

    print("\n=== the picture: clock used and net points against when the ball was gained ===")
    shape = profile(built)
    print(shape.round(3).to_string(index=False))
    shape.to_csv(REPORTS / f"twoforone_profile_{window}.csv", index=False)

    print(f"\n=== H6a and H6b at the registered threshold ({FEASIBLE_FROM:.0f}s) ===")
    main = discontinuity(built)
    print(main.round(4).to_string(index=False))
    main.to_csv(REPORTS / f"twoforone_discontinuity_{window}.csv", index=False)

    print("\n=== registered sensitivity: every threshold from 28 to 36 ===")
    sweep = threshold_sweep(built)
    local = sweep[sweep.estimator == "local linear"]
    print(local.pivot(index="threshold", columns="outcome",
                     values=["difference", "t"]).round(4).to_string())
    sweep.to_csv(REPORTS / f"twoforone_sweep_{window}.csv", index=False)

    print("\n=== H6c, descriptive: what the early shot gives up ===")
    values = continuation_value(possession_panel(panel), outcome="PTS_POSS")
    for key, value in cost_of_shooting_early(built, values).items():
        print(f"  {key}: {value:,.4f}" if isinstance(value, float) else f"  {key}: {value:,}")


def cmd_value(window: str) -> None:
    """The possession valuation curve, its held-out calibration, and the team decomposition.

    H7 is registered in `reports/preregistration_deviation.md` for the holdout only —
    exploration had already been examined when it was written, and it says so.
    """
    from scipy import stats

    from possval.models.rebound import possession_panel
    from possval.models.team_profiles import (
        player_diagnostics,
        score_against_team_curve,
        team_clock_bands,
        team_context_decomposition,
        team_diagnostics,
    )
    from possval.models.value import (
        calibration,
        calibration_summary,
        possession_curve,
        premature_null,
        premature_share,
        shot_value,
        team_curves,
        team_shot_timing,
    )

    first, last = SITUATIONAL_WINDOWS[window]
    pd.set_option("display.width", 200)
    print(f"=== window: {window} ({first}-{str(first + 1)[-2:]} to "
          f"{last}-{str(last + 1)[-2:]}) ===")

    panel = pd.read_parquet(PROCESSED / "chance_panel.parquet")
    shots = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    shots = shots[shots.GAME_CLOCK_EXPIRING == 0]
    outcomes = pd.read_parquet(PROCESSED / "shot_outcomes.parquet")

    window_panel = panel[panel.SEASON.between(first, last)]
    chained = possession_panel(window_panel)
    chained = chained[~chained.PERIOD_EXPIRED]
    second_chance = float(chained[chained.START_TYPE == "off_rebound"].PTS_POSS.mean())

    curve = possession_curve(window_panel)
    curve.to_csv(REPORTS / f"value_curve_{window}.csv", index=False)
    print("\n=== V(t) by start group ===")
    print(curve.pivot(index="SECOND", columns="GROUP", values="V").round(3).to_string())

    if window == "explore":
        held = panel[panel.SEASON.between(*SITUATIONAL_WINDOWS["holdout"])]
        table = calibration(window_panel, held)
        table.to_csv(REPORTS / "value_calibration.csv", index=False)
        print("\n=== held-out calibration: fit on explore, score on holdout ===")
        for label, shift in (("raw", False), ("after one league level shift", True)):
            summary = calibration_summary(table, level_shift=shift)
            print(f"  {label}: mean |error| {summary['mean_abs_error']:.4f} pts, "
                  f"bias {summary['bias']:+.4f}, shift {summary['level_shift']:+.4f}")
        print("  the shape transfers; the level does not, and should not")

    valued = shot_value(shots[shots.SEASON.between(first, last)], outcomes, second_chance)
    curves = team_curves(chained, min_possessions=5_000)
    curves.to_csv(REPORTS / f"value_team_curves_{window}.csv", index=False)

    print("\n=== 1. where teams sit on the curve (style) ===")
    timing = team_shot_timing(valued, min_shots=2_000)
    timing.to_csv(REPORTS / f"value_team_timing_{window}.csv", index=False)
    print(pd.concat([timing.head(4), timing.tail(4)]).round(3).to_string(index=False))

    print("\n=== 2. deviation from a team's OWN curve (decision quality) ===")
    observed = premature_share(valued, curves, min_shots=2_000)
    observed.to_csv(REPORTS / f"value_premature_{window}.csv", index=False)
    print(pd.concat([observed.head(4), observed.tail(4)]).round(4).to_string(index=False))

    scored = score_against_team_curve(valued, curves)
    diagnostics = team_diagnostics(valued, curves, chained, min_shots=2_000)
    bands = team_clock_bands(scored)
    context_summary, context_details = team_context_decomposition(scored)
    players = player_diagnostics(scored, min_shots=300)
    diagnostics.to_csv(REPORTS / f"value_team_diagnostics_{window}.csv", index=False)
    bands.to_csv(REPORTS / f"value_team_clock_bands_{window}.csv", index=False)
    context_summary.to_csv(
        REPORTS / f"value_team_context_summary_{window}.csv", index=False
    )
    context_details.to_csv(
        REPORTS / f"value_team_context_details_{window}.csv", index=False
    )
    players.to_csv(REPORTS / f"value_player_diagnostics_{window}.csv", index=False)
    print("\n=== review queue: bottom-third offense + top-third exposure ===")
    review = diagnostics[diagnostics.REVIEW_FLAG]
    columns = [
        "TEAM_ABBREVIATION", "OFFENSE_RANK", "PPP", "PREMATURE",
        "EXPOSURE_PER_SHOT", "MEAN_SECOND",
    ]
    print(review[columns].round(4).to_string(index=False) if len(review) else "  none")

    null = premature_null(valued, chained, n_draws=50, min_possessions=5_000)
    variance = observed.PREMATURE.var(ddof=1)
    signal = max(variance - null["null_mean"] ** 2, 0.0) / variance
    print(f"observed SD {np.sqrt(variance):.5f} vs permutation null {null['null_mean']:.5f} "
          f"(p95 {null['null_p95']:.5f})  ->  signal share {signal:.3f}")

    other = "holdout" if window == "explore" else "explore"
    path = REPORTS / f"value_premature_{other}.csv"
    if path.exists():
        previous = pd.read_csv(path).set_index("TEAM_ABBREVIATION").PREMATURE
        current = observed.set_index("TEAM_ABBREVIATION").PREMATURE
        shared = current.index.intersection(previous.index)
        rho, p_value = stats.spearmanr(current[shared], previous[shared])
        print("\n=== H7b: does the ranking persist across windows? ===")
        print(f"  {len(shared)} franchises | Spearman rho {rho:+.3f}, "
              f"one-sided p {p_value / 2:.4f}")


def cmd_prospective() -> None:
    """Exploratory: does current premature share predict the next 20 games?"""
    from possval.models.prospective import (
        fixed_effect_regression,
        prospective_panel,
        prospective_specifications,
    )

    panel = pd.read_parquet(PROCESSED / "chance_panel.parquet")
    shots = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    outcomes = pd.read_parquet(PROCESSED / "shot_outcomes.parquet")
    result = prospective_panel(panel, shots, outcomes)
    specifications = prospective_specifications(result)

    result.to_csv(REPORTS / "value_prospective_panel.csv", index=False)
    specifications.to_csv(REPORTS / "value_prospective_specifications.csv", index=False)

    controls = ("PPP", "MEAN_SHOT_VALUE", "MEAN_SECOND")
    robustness = []
    for games_per_block in (15, 20, 25):
        sized = result if games_per_block == 20 else prospective_panel(
            panel, shots, outcomes, games_per_block=games_per_block
        )
        robustness.append(
            {
                "check": "block_length",
                "games_per_block": games_per_block,
                "omitted_season": np.nan,
                **fixed_effect_regression(sized, controls),
            }
        )
    for omitted in sorted(result.SEASON.unique()):
        robustness.append(
            {
                "check": "leave_one_season_out",
                "games_per_block": 20,
                "omitted_season": omitted,
                **fixed_effect_regression(result[result.SEASON != omitted], controls),
            }
        )
    robustness = pd.DataFrame(robustness)
    robustness.to_csv(REPORTS / "value_prospective_robustness.csv", index=False)

    print("=== premature share now -> offensive efficiency in the next 20 games ===")
    print(f"{len(result)} team-blocks, {result.TEAM.nunique()} teams, "
          f"{result.SEASON.nunique()} seasons")
    print(specifications.round(5).to_string(index=False))
    final = specifications.iloc[-1]
    print("\nThe first row asks whether the measure predicts at all. The last asks whether it ")
    print("adds information beyond current efficiency, shot value, and timing.")
    print(f"Fully controlled: {final.effect_per_1pp:+.5f} next-block points/possession "
          f"per +1pp premature share (p={final.p:.3f}).")
    print("\n=== exploratory robustness, fully controlled ===")
    print(robustness[[
        "check", "games_per_block", "omitted_season", "estimate", "std_error", "p"
    ]].round(5).to_string(index=False))
    print("Exploratory: the design and historical result were first produced together.")


def cmd_mechanisms() -> None:
    """Exploratory: context, roster, game-state, and sequence anatomy of team profiles."""
    from possval.models.mechanisms import (
        game_state_profiles,
        mover_pairs,
        persistence_summary,
        possession_sequence_profiles,
        season_profiles,
    )
    from possval.models.rebound import possession_panel
    from possval.models.team_profiles import score_against_team_curve
    from possval.models.value import shot_value, team_curves

    panel = pd.read_parquet(PROCESSED / "chance_panel.parquet")
    shots = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    outcomes = pd.read_parquet(PROCESSED / "shot_outcomes.parquet")
    chained = possession_panel(panel)
    chained = chained[~chained.PERIOD_EXPIRED]

    team_seasons, player_seasons = season_profiles(chained, shots, outcomes)
    movers = mover_pairs(team_seasons, player_seasons)
    persistence = persistence_summary(team_seasons, movers)
    team_seasons.to_csv(REPORTS / "mechanism_team_seasons.csv", index=False)
    player_seasons.to_csv(REPORTS / "mechanism_player_seasons.csv", index=False)
    movers.to_csv(REPORTS / "mechanism_movers.csv", index=False)
    persistence.to_csv(REPORTS / "mechanism_persistence.csv", index=False)

    first, last = SITUATIONAL_WINDOWS["holdout"]
    held_panel = chained[chained.SEASON.between(first, last)]
    held_shots = shots[shots.SEASON.between(first, last) & shots.GAME_CLOCK_EXPIRING.eq(0)]
    second_chance = float(
        held_panel.loc[held_panel.START_TYPE.eq("off_rebound"), "PTS_POSS"].mean()
    )
    valued = shot_value(
        held_shots,
        outcomes[outcomes.SEASON.between(first, last)],
        second_chance,
    )
    scored = score_against_team_curve(
        valued,
        team_curves(held_panel, min_possessions=5_000),
    )
    states = game_state_profiles(scored)
    states.to_csv(REPORTS / "mechanism_game_states_holdout.csv", index=False)

    sequence_league, sequence_teams = possession_sequence_profiles(held_panel, held_shots)
    sequence_league.to_csv(REPORTS / "mechanism_sequence_league_holdout.csv", index=False)
    sequence_teams.to_csv(REPORTS / "mechanism_sequence_teams_holdout.csv", index=False)

    print("=== roster and system persistence ===")
    print(persistence.round(4).to_string(index=False))
    print("\n=== close fourth-quarter profiles: review teams ===")
    close = states[
        states.GAME_PHASE.eq("fourth quarter")
        & states.SCORE_STATE.astype(str).eq("within 3")
        & states.TEAM_ABBREVIATION.isin(["HOU", "ORL"])
    ]
    print(close[[
        "TEAM_ABBREVIATION", "N_SHOTS", "EXPOSURE_PER_SHOT", "LEAGUE_EXPOSURE",
        "MEAN_SECOND", "LEAGUE_CLOCK",
    ]].round(4).to_string(index=False))
    print("\n=== previous possession result -> next first shot ===")
    print(sequence_league.round(4).to_string(index=False))
    print("\nExploratory mechanism search; none of these tables is a causal coaching grade.")


def cmd_team_validation(n_null_draws: int = 50) -> None:
    """Gate 1: put shots, shooting fouls, and continuation in consistent point units."""
    from possval.models.foul_value import (
        foul_repriced_actions,
        historical_foul_premium,
        shooting_foul_events,
    )
    from possval.models.rebound import possession_panel
    from possval.models.team_profiles import (
        score_against_team_curve,
        team_context_decomposition,
    )
    from possval.models.team_validation import (
        accounting_comparisons,
        foul_counts,
        location_exposure_bounds,
        team_accounting_profile,
    )
    from possval.models.value import (
        calibration,
        calibration_summary,
        premature_null,
        shot_value,
        team_curves,
    )

    ensure_dirs()
    panel = pd.read_parquet(PROCESSED / "chance_panel.parquet")
    shots_all = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    shots = shots_all[shots_all.GAME_CLOCK_EXPIRING.eq(0)]
    outcomes = pd.read_parquet(PROCESSED / "shot_outcomes.parquet")

    foul_frames = []
    for season in sorted(panel.SEASON.unique()):
        path = PROCESSED / f"pbp_clock_{season}.parquet"
        if path.exists():
            foul_frames.append(shooting_foul_events(pd.read_parquet(path)))
    fouls = pd.concat(foul_frames, ignore_index=True)
    counts = foul_counts(fouls, shots_all)
    counts.to_csv(REPORTS / "team_validation_foul_counts.csv", index=False)

    holdout = panel[panel.SEASON.between(2022, 2023)]
    fg_chained = possession_panel(holdout, points_column="PTS_FG")
    all_chained = possession_panel(holdout, points_column="PTS_ALL")
    fg_chained = fg_chained[~fg_chained.PERIOD_EXPIRED]
    all_chained = all_chained[~all_chained.PERIOD_EXPIRED]
    fg_second_chance = float(
        fg_chained[fg_chained.START_TYPE.eq("off_rebound")].PTS_POSS.mean()
    )
    all_second_chance = float(
        all_chained[all_chained.START_TYPE.eq("off_rebound")].PTS_POSS.mean()
    )
    fg_curves = team_curves(fg_chained, min_possessions=5_000)
    all_curves = team_curves(all_chained, min_possessions=5_000)
    held_shots = shots[shots.SEASON.between(2022, 2023)]
    fg_valued = shot_value(held_shots, outcomes, fg_second_chance)
    all_valued = shot_value(held_shots, outcomes, all_second_chance)

    foul_only = fouls[~fouls.AND_ONE].copy()
    # Match the period-expiry exclusion applied to official FGA.  Missing reconstructed shot
    # clocks are reported in the count table but cannot enter a clock-conditioned comparison.
    held_foul_only = foul_only[
        foul_only.SEASON.between(2022, 2023)
        & foul_only.SHOT_CLOCK.notna()
        & foul_only.GAME_CLOCK.ge(3)
    ].copy()
    action_denominator = pd.concat(
        [shots_all[["PLAYER_ID", "SEASON"]], foul_only[["PLAYER_ID", "SEASON"]]],
        ignore_index=True,
    )
    premiums = historical_foul_premium(
        action_denominator,
        fouls,
        train_through=2021,
        prior_strength=200,
    )
    fga_with_premium = all_valued.copy()
    player_premium = premiums.set_index("PLAYER_ID").FOUL_PREMIUM
    league_premium = float(premiums.LEAGUE_FOUL_PREMIUM.iloc[0])
    fga_with_premium["FOUL_PREMIUM"] = (
        fga_with_premium.PLAYER_ID.map(player_premium).fillna(league_premium)
    )
    fga_with_premium["SHOT_VALUE"] += fga_with_premium.FOUL_PREMIUM
    repriced = foul_repriced_actions(all_valued, held_foul_only, premiums)

    specifications = pd.concat(
        [
            team_accounting_profile("A: FG-only baseline", fg_valued, fg_curves),
            team_accounting_profile("B: all-points curve only", fg_valued, all_curves),
            team_accounting_profile("C: + all-points rebound option", all_valued, all_curves),
            team_accounting_profile(
                "D: + historical foul premium", fga_with_premium, all_curves
            ),
            team_accounting_profile("E: + foul-only exercises", repriced, all_curves),
        ],
        ignore_index=True,
    )
    comparisons = accounting_comparisons(specifications)
    specifications.to_csv(
        REPORTS / "team_validation_accounting_specifications.csv", index=False
    )
    comparisons.to_csv(REPORTS / "team_validation_accounting_comparisons.csv", index=False)

    calibration_rows = []
    train = panel[panel.SEASON.between(2015, 2021)]
    test = panel[panel.SEASON.between(2022, 2023)]
    for label, points in (("field-goal points", "PTS_FG"), ("all points", "PTS_ALL")):
        table = calibration(train, test, points_column=points)
        table.insert(0, "POINTS_UNIT", label)
        table.to_csv(
            REPORTS / f"team_validation_calibration_{points.lower()}.csv", index=False
        )
        for shifted in (False, True):
            calibration_rows.append(
                {
                    "POINTS_UNIT": label,
                    "LEVEL_SHIFTED": shifted,
                    **calibration_summary(table, level_shift=shifted),
                }
            )
    pd.DataFrame(calibration_rows).to_csv(
        REPORTS / "team_validation_calibration_summary.csv", index=False
    )

    scored_baseline = score_against_team_curve(fg_valued, fg_curves)
    scored_repriced = score_against_team_curve(repriced, all_curves)
    bounds = pd.concat(
        [
            location_exposure_bounds(scored_baseline).assign(
                SPECIFICATION="A: FG-only baseline"
            ),
            location_exposure_bounds(scored_repriced).assign(
                SPECIFICATION="E: + foul-only exercises"
            ),
        ],
        ignore_index=True,
    )
    bounds.to_csv(REPORTS / "team_validation_location_bounds.csv", index=False)
    context, context_cells = team_context_decomposition(scored_repriced)
    context.to_csv(REPORTS / "team_validation_context_summary.csv", index=False)
    context_cells.to_csv(REPORTS / "team_validation_context_cells.csv", index=False)

    final_profile = specifications[
        specifications.SPECIFICATION.eq("E: + foul-only exercises")
    ]
    variance = float(final_profile.PREMATURE.var(ddof=1))
    null = premature_null(
        repriced,
        all_chained,
        n_draws=n_null_draws,
        min_possessions=5_000,
    )
    signal_share = max(variance - null["null_mean"] ** 2, 0.0) / variance
    rank_row = comparisons[
        comparisons.SPECIFICATION.eq("E: + foul-only exercises")
        & comparisons.METRIC.eq("EXPOSURE_PER_ACTION")
    ].iloc[0]
    baseline_profile = specifications[
        specifications.SPECIFICATION.eq("A: FG-only baseline")
    ]
    baseline_excess = float(
        baseline_profile.set_index("TEAM_ABBREVIATION").loc["HOU", "EXPOSURE_PER_ACTION"]
        - baseline_profile.EXPOSURE_PER_ACTION.mean()
    )
    repriced_excess = float(
        final_profile.set_index("TEAM_ABBREVIATION").loc["HOU", "EXPOSURE_PER_ACTION"]
        - final_profile.EXPOSURE_PER_ACTION.mean()
    )
    correction_fraction = abs(repriced_excess - baseline_excess) / abs(baseline_excess)
    hou_context_rank = int(
        context.set_index("TEAM_ABBREVIATION").loc["HOU", "WITHIN_CONTEXT_RANK"]
    )
    paint = bounds[
        bounds.SPECIFICATION.eq("E: + foul-only exercises")
        & bounds.SHOT_FAMILY.eq("paint (non-RA)")
    ].iloc[0]
    summary = pd.DataFrame(
        [
            {
                "CONDITION": "baseline vs all-points exposure rank rho >= 0.60",
                "ESTIMATE": rank_row.SPEARMAN_RHO,
                "THRESHOLD": 0.60,
                "STATUS": "PASS" if rank_row.SPEARMAN_RHO >= 0.60 else "FAIL",
            },
            {
                "CONDITION": "all-points signal share >= 0.50",
                "ESTIMATE": signal_share,
                "THRESHOLD": 0.50,
                "STATUS": "PASS" if signal_share >= 0.50 else "FAIL",
            },
            {
                "CONDITION": "Houston context-adjusted rank <= 10",
                "ESTIMATE": hou_context_rank,
                "THRESHOLD": 10,
                "STATUS": "PASS" if hou_context_rank <= 10 else "FAIL",
            },
            {
                "CONDITION": "foul repricing explains <= 0.50 of Houston excess",
                "ESTIMATE": correction_fraction,
                "THRESHOLD": 0.50,
                "STATUS": "PASS" if correction_fraction <= 0.50 else "FAIL",
            },
            {
                "CONDITION": "non-RA paint conclusion bounded for missing locations",
                "ESTIMATE": paint.SHARE_LOWER,
                "THRESHOLD": np.nan,
                "STATUS": (
                    "PASS"
                    if np.isclose(paint.SHARE_LOWER, paint.SHARE_UPPER)
                    else "NARROWED"
                ),
            },
        ]
    )
    summary["NULL_SD_MEAN"] = null["null_mean"]
    summary["NULL_SD_P95"] = null["null_p95"]
    summary["NON_RA_SHARE_UPPER"] = paint.SHARE_UPPER
    summary.to_csv(REPORTS / "team_validation_gate1_summary.csv", index=False)

    print("=== Gate 1: foul and points accounting ===")
    print(summary.round(4).to_string(index=False))
    print("\n=== aligned exposure-rank comparisons ===")
    print(
        comparisons[comparisons.METRIC.eq("EXPOSURE_PER_ACTION")]
        .round(4)
        .to_string(index=False)
    )
    print("\n=== repriced leaders ===")
    print(
        final_profile[
            ["TEAM_ABBREVIATION", "N_ACTIONS", "PREMATURE", "EXPOSURE_PER_ACTION", "EXPOSURE_RANK"]
        ].head(10).round(4).to_string(index=False)
    )


def cmd_defender_extract(source: str, output: str) -> None:
    """Build a compact release-frame table from an external raw SportVU checkout."""
    from pathlib import Path

    from possval.models.defender import extract_all

    if not source or not output:
        raise SystemExit("--source and --output are required")
    output_path = Path(output)
    checkpoints = output_path / "games"
    table = extract_all(Path(source), checkpoints)
    combined = output_path / "sportvu_defender_distance.csv.gz"
    table.to_csv(combined, index=False, compression="gzip")
    print(f"wrote {len(table):,} release-frame rows to {combined}")


def cmd_team_temporal_validation(n_null_draws: int = 50) -> None:
    """Gate 3: one-season-ahead replication plus registered specification checks."""
    from possval.models.foul_value import (
        foul_repriced_actions,
        historical_foul_premium,
        shooting_foul_events,
    )
    from possval.models.rebound import possession_panel
    from possval.models.team_profiles import add_basketball_context, score_against_team_curve
    from possval.models.team_validation import (
        aligned_rank_correlation,
        team_accounting_profile,
        team_game_bootstrap,
        temporal_team_game_null,
    )
    from possval.models.value import shot_value, team_curves

    ensure_dirs()
    panel = pd.read_parquet(PROCESSED / "chance_panel.parquet")
    shots_all = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    shots = shots_all[shots_all.GAME_CLOCK_EXPIRING.eq(0)]
    outcomes = pd.read_parquet(PROCESSED / "shot_outcomes.parquet")
    fouls = pd.concat(
        [
            shooting_foul_events(
                pd.read_parquet(PROCESSED / f"pbp_clock_{season}.parquet")
            )
            for season in range(2015, 2025)
        ],
        ignore_index=True,
    )
    foul_only = fouls[~fouls.AND_ONE].copy()
    action_denominator = pd.concat(
        [shots_all[["PLAYER_ID", "SEASON"]], foul_only[["PLAYER_ID", "SEASON"]]],
        ignore_index=True,
    )

    def forward_profile(score_season: int, train_seasons: list[int]):
        training = panel[panel.SEASON.isin(train_seasons)]
        chained = possession_panel(training, points_column="PTS_ALL")
        chained = chained[~chained.PERIOD_EXPIRED]
        curves = team_curves(chained, min_possessions=5_000)
        second_chance = float(
            chained[chained.START_TYPE.eq("off_rebound")].PTS_POSS.mean()
        )
        official = shot_value(
            shots[shots.SEASON.eq(score_season)],
            outcomes[outcomes.SEASON.isin(train_seasons)],
            second_chance,
        )
        premiums = historical_foul_premium(
            action_denominator,
            fouls,
            train_through=max(train_seasons),
            prior_strength=200,
        )
        foul = foul_only[
            foul_only.SEASON.eq(score_season)
            & foul_only.SHOT_CLOCK.notna()
            & foul_only.GAME_CLOCK.ge(3)
        ]
        valued = foul_repriced_actions(official, foul, premiums)
        profile = team_accounting_profile(
            f"score {score_season}; train {min(train_seasons)}-{max(train_seasons)}",
            valued,
            curves,
        )
        return profile, valued, curves, chained

    profile_2023, _, _, _ = forward_profile(2023, [2022])
    profile_2024, valued_2024, curves_2024, train_chain = forward_profile(
        2024, [2022, 2023]
    )
    profiles = pd.concat([profile_2023, profile_2024], ignore_index=True)
    profiles.to_csv(REPORTS / "team_validation_temporal_profiles.csv", index=False)
    temporal_rank = aligned_rank_correlation(
        profile_2023,
        profile_2024,
        "EXPOSURE_PER_ACTION",
    )
    observed_sd = float(profile_2024.PREMATURE.std(ddof=1))
    null = temporal_team_game_null(
        valued_2024,
        train_chain,
        n_draws=n_null_draws,
        min_possessions=5_000,
        min_shots=5_000,
    )
    signal_share = max(observed_sd**2 - null["null_mean"] ** 2, 0.0) / observed_sd**2

    # Registered 2022-24 specification grid, using the foul-consistent Gate-1 estimator.
    held = panel[panel.SEASON.between(2022, 2023)]
    held_chain = possession_panel(held, points_column="PTS_ALL")
    held_chain = held_chain[~held_chain.PERIOD_EXPIRED]
    held_curves = team_curves(held_chain, min_possessions=5_000)
    second_chance = float(
        held_chain[held_chain.START_TYPE.eq("off_rebound")].PTS_POSS.mean()
    )
    held_official = shot_value(
        shots[shots.SEASON.between(2022, 2023)],
        outcomes[outcomes.SEASON.between(2022, 2023)],
        second_chance,
    )
    held_premiums = historical_foul_premium(
        action_denominator,
        fouls,
        train_through=2021,
        prior_strength=200,
    )
    held_foul = foul_only[
        foul_only.SEASON.between(2022, 2023)
        & foul_only.SHOT_CLOCK.notna()
        & foul_only.GAME_CLOCK.ge(3)
    ]
    held_valued = foul_repriced_actions(held_official, held_foul, held_premiums)
    reference = team_accounting_profile("reference", held_valued, held_curves)
    robustness = [reference]
    for threshold in (3_000, 5_000, 8_000):
        curves = team_curves(held_chain, min_possessions=threshold)
        robustness.append(
            team_accounting_profile(
                f"minimum {threshold} team possessions", held_valued, curves
            )
        )
    for rule, operation in (
        ("floor", np.floor),
        ("nearest", np.rint),
        ("ceiling", np.ceil),
    ):
        valued = held_valued.copy()
        valued["SECOND"] = operation(valued.SHOT_CLOCK).clip(0, 24).astype(int)
        robustness.append(team_accounting_profile(f"clock {rule}", valued, held_curves))
    for cutoff in (2, 3, 5, 8):
        valued = held_valued[held_valued.PERIOD_SECONDS_REMAINING.ge(cutoff)]
        robustness.append(
            team_accounting_profile(f"exclude period clock < {cutoff}s", valued, held_curves)
        )
    contextual = add_basketball_context(held_valued)
    for family in ("rim", "paint (non-RA)", "mid-range", "three"):
        robustness.append(
            team_accounting_profile(
                f"remove {family}",
                contextual[~contextual.SHOT_FAMILY.eq(family)],
                held_curves,
            )
        )
    for curve_season, shot_season in ((2022, 2023), (2023, 2022)):
        chain = possession_panel(
            panel[panel.SEASON.eq(curve_season)], points_column="PTS_ALL"
        )
        chain = chain[~chain.PERIOD_EXPIRED]
        curves = team_curves(chain, min_possessions=3_000)
        robustness.append(
            team_accounting_profile(
                f"curve {curve_season}; actions {shot_season}",
                held_valued[held_valued.SEASON.eq(shot_season)],
                curves,
            )
        )

    # Negative control: preserve team, season, broad clock phase, and shot family while
    # destroying the exact pairing between a shot's value and its second/reference value.
    control = contextual.copy()
    control["CLOCK_PHASE_CONTROL"] = pd.cut(
        control.SECOND,
        [-1, 7, 15, 24],
        labels=["late", "middle", "early"],
        include_lowest=True,
    )
    rng = np.random.default_rng(0)
    strata = ["TEAM_ABBREVIATION", "SEASON", "CLOCK_PHASE_CONTROL", "SHOT_FAMILY"]
    control["SHOT_VALUE"] = control.groupby(strata, observed=True).SHOT_VALUE.transform(
        lambda values: rng.permutation(values.to_numpy())
    )
    robustness.append(team_accounting_profile("negative control", control, held_curves))

    robustness_table = pd.concat(robustness, ignore_index=True)
    robustness_table.to_csv(
        REPORTS / "team_validation_specification_profiles.csv", index=False
    )
    comparison_rows = []
    for name, current in robustness_table.groupby("SPECIFICATION", sort=False):
        correlation = aligned_rank_correlation(reference, current, "EXPOSURE_PER_ACTION")
        indexed = current.set_index("TEAM_ABBREVIATION")
        comparison_rows.append(
            {
                "SPECIFICATION": name,
                **correlation,
                "TEAM_SD": current.PREMATURE.std(ddof=1),
                "HOU_RANK": (
                    indexed.loc["HOU", "EXPOSURE_RANK"]
                    if "HOU" in indexed.index
                    else np.nan
                ),
                "ORL_RANK": (
                    indexed.loc["ORL", "EXPOSURE_RANK"]
                    if "ORL" in indexed.index
                    else np.nan
                ),
            }
        )
    comparisons = pd.DataFrame(comparison_rows)
    comparisons.to_csv(
        REPORTS / "team_validation_specification_comparisons.csv", index=False
    )

    scored_held = score_against_team_curve(held_valued, held_curves)
    intervals = team_game_bootstrap(scored_held, n_draws=1_000, seed=0)
    median = float(reference.EXPOSURE_PER_ACTION.median())
    intervals["LEAGUE_MEDIAN_EXPOSURE"] = median
    intervals["INTERVAL_ABOVE_MEDIAN"] = intervals.EXPOSURE_LOW > median
    intervals.to_csv(REPORTS / "team_validation_team_game_bootstrap.csv", index=False)

    temporal_summary = pd.DataFrame(
        [
            {
                "CONDITION": "2024-25 signal share >= 0.50",
                "ESTIMATE": signal_share,
                "THRESHOLD": 0.50,
                "STATUS": "PASS" if signal_share >= 0.50 else "FAIL",
            },
            {
                "CONDITION": "2023-24 to 2024-25 exposure-rank rho >= 0.30",
                "ESTIMATE": temporal_rank["SPEARMAN_RHO"],
                "THRESHOLD": 0.30,
                "STATUS": "PASS" if temporal_rank["SPEARMAN_RHO"] >= 0.30 else "FAIL",
            },
        ]
    )
    temporal_summary["OBSERVED_SD"] = observed_sd
    temporal_summary["NULL_SD_MEAN"] = null["null_mean"]
    temporal_summary["NULL_SD_P95"] = null["null_p95"]
    temporal_summary.to_csv(
        REPORTS / "team_validation_gate3_temporal_summary.csv", index=False
    )
    print("=== Gate 3 temporal replication ===")
    print(temporal_summary.round(4).to_string(index=False))
    print("\n=== specification comparisons ===")
    print(comparisons.round(4).to_string(index=False))
    print("\n=== candidate bootstrap intervals ===")
    print(
        intervals[intervals.TEAM_ABBREVIATION.isin(["HOU", "ORL"])]
        .round(4)
        .to_string(index=False)
    )


def cmd_defender_validation(tracking_path: str) -> None:
    """Gate 2: does closest-defender distance absorb the below-curve exposure signal?"""
    from possval.models.defender import (
        crossfit_defender_value,
        join_tracking_shots,
        open_shot_case_control,
        paired_game_bootstrap_improvement,
    )
    from possval.models.rebound import possession_panel
    from possval.models.team_profiles import score_against_team_curve
    from possval.models.team_validation import (
        aligned_rank_correlation,
        team_accounting_profile,
    )
    from possval.models.value import shot_value, team_curves

    if not tracking_path:
        raise SystemExit("--tracking is required")
    ensure_dirs()
    tracking = pd.read_csv(tracking_path, dtype={"GAME_ID": str})
    shots = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    shots = shots[shots.SEASON.eq(2015) & shots.GAME_CLOCK_EXPIRING.eq(0)]
    joined, match_metrics = join_tracking_shots(shots, tracking)
    basket_left = np.hypot(joined.SHOOTER_X - 5.25, joined.SHOOTER_Y - 25.0)
    basket_right = np.hypot(joined.SHOOTER_X - 88.75, joined.SHOOTER_Y - 25.0)
    joined["TRACKING_SHOT_DISTANCE"] = np.minimum(basket_left, basket_right)
    joined["SHOT_DISTANCE_ERROR"] = joined.TRACKING_SHOT_DISTANCE - joined.SHOT_DISTANCE
    joined["ABS_SHOT_DISTANCE_ERROR"] = joined.SHOT_DISTANCE_ERROR.abs()
    pd.DataFrame([match_metrics]).to_csv(
        REPORTS / "team_validation_defender_match_summary.csv", index=False
    )
    release_quality = joined.groupby("TRACKING_MATCHED", dropna=False).agg(
        N=("GAME_ID", "size"),
        MEDIAN_RELEASE_BEFORE_EVENT=("RELEASE_BEFORE_EVENT_SECONDS", "median"),
        P95_RELEASE_BEFORE_EVENT=(
            "RELEASE_BEFORE_EVENT_SECONDS", lambda value: value.quantile(0.95)
        ),
        MEDIAN_BALL_SHOOTER_DISTANCE=("BALL_SHOOTER_DISTANCE", "median"),
        MEDIAN_DEFENDERS=("N_DEFENDERS", "median"),
        FALLBACK_SHARE=("RELEASE_FALLBACK", "mean"),
        MEDIAN_ABS_SHOT_DISTANCE_ERROR=("ABS_SHOT_DISTANCE_ERROR", "median"),
        P95_ABS_SHOT_DISTANCE_ERROR=(
            "ABS_SHOT_DISTANCE_ERROR", lambda value: value.quantile(0.95)
        ),
    ).reset_index()
    release_quality.to_csv(
        REPORTS / "team_validation_defender_release_quality.csv", index=False
    )
    matched = joined[joined.TRACKING_MATCHED.eq(True)].copy()
    crossfit, model_metrics = crossfit_defender_value(matched, n_splits=5, seed=0)
    improvement = paired_game_bootstrap_improvement(crossfit, n_draws=2_000, seed=0)
    model_metrics.to_csv(REPORTS / "team_validation_defender_model_metrics.csv", index=False)
    improvement.to_csv(
        REPORTS / "team_validation_defender_model_improvement.csv", index=False
    )

    panel = pd.read_parquet(PROCESSED / "chance_panel.parquet")
    chained = possession_panel(panel[panel.SEASON.eq(2015)], points_column="PTS_FG")
    chained = chained[~chained.PERIOD_EXPIRED]
    curves = team_curves(chained, min_possessions=5_000)
    second_chance = float(
        chained[chained.START_TYPE.eq("off_rebound")].PTS_POSS.mean()
    )
    outcomes = pd.read_parquet(PROCESSED / "shot_outcomes.parquet")
    outcomes = outcomes[outcomes.SEASON.eq(2015)]
    original_valued = shot_value(crossfit, outcomes, second_chance)
    baseline_input = crossfit.copy()
    baseline_input["XPTS"] = baseline_input.P_BASELINE * (2 + baseline_input.IS_3)
    baseline_valued = shot_value(baseline_input, outcomes, second_chance)
    aware_input = crossfit.copy()
    aware_input["XPTS"] = aware_input.DEFENDER_XPTS
    aware_valued = shot_value(aware_input, outcomes, second_chance)
    scored_original = score_against_team_curve(original_valued, curves)
    scored_baseline = score_against_team_curve(baseline_valued, curves)
    scored_aware = score_against_team_curve(aware_valued, curves)
    original_profile = team_accounting_profile("published xPTS", original_valued, curves)
    baseline_profile = team_accounting_profile(
        "cross-fitted baseline xPTS", baseline_valued, curves
    )
    aware_profile = team_accounting_profile("defender-aware xPTS", aware_valued, curves)
    profiles = pd.concat(
        [original_profile, baseline_profile, aware_profile], ignore_index=True
    )
    profiles.to_csv(REPORTS / "team_validation_defender_team_profiles.csv", index=False)
    rank = aligned_rank_correlation(
        baseline_profile, aware_profile, "EXPOSURE_PER_ACTION"
    )
    published_rank = aligned_rank_correlation(
        original_profile, aware_profile, "EXPOSURE_PER_ACTION"
    )

    baseline_total = float(scored_baseline.EXPOSURE.sum())
    aware_total = float(scored_aware.EXPOSURE.sum())
    exposure_retained = aware_total / baseline_total
    paint_baseline = scored_baseline.SHOT_ZONE_BASIC.eq("In The Paint (Non-RA)")
    paint_aware = scored_aware.SHOT_ZONE_BASIC.eq("In The Paint (Non-RA)")
    paint_retained = (
        scored_aware.loc[paint_aware, "EXPOSURE"].sum()
        / scored_baseline.loc[paint_baseline, "EXPOSURE"].sum()
    )
    context = pd.DataFrame(
        [
            {
                "CONTEXT": "all matched shots",
                "BASELINE_EXPOSURE": baseline_total,
                "DEFENDER_AWARE_EXPOSURE": aware_total,
                "EXPOSURE_RETAINED": exposure_retained,
            },
            {
                "CONTEXT": "published xPTS sensitivity",
                "BASELINE_EXPOSURE": scored_original.EXPOSURE.sum(),
                "DEFENDER_AWARE_EXPOSURE": aware_total,
                "EXPOSURE_RETAINED": aware_total / scored_original.EXPOSURE.sum(),
            },
            {
                "CONTEXT": "paint (non-RA)",
                "BASELINE_EXPOSURE": scored_baseline.loc[paint_baseline, "EXPOSURE"].sum(),
                "DEFENDER_AWARE_EXPOSURE": scored_aware.loc[paint_aware, "EXPOSURE"].sum(),
                "EXPOSURE_RETAINED": paint_retained,
            },
        ]
    )
    context.to_csv(REPORTS / "team_validation_defender_context.csv", index=False)
    open_control = open_shot_case_control(scored_baseline, scored_aware, seed=0)
    open_control.to_csv(
        REPORTS / "team_validation_defender_open_controls.csv", index=False
    )

    logloss = improvement[improvement.METRIC.eq("LOG_LOSS")].iloc[0]
    materially_improves = logloss.IMPROVEMENT >= 0.0005 and logloss.LOW > 0
    open_wide_differences = []
    for _, frame in open_control.groupby("DEFENDER_BAND", observed=True):
        rates = frame.set_index("BASELINE_CASE").AWARE_BELOW
        if True in rates.index and False in rates.index:
            open_wide_differences.append(float(rates.loc[True] - rates.loc[False]))
    open_survives = bool(open_wide_differences) and min(open_wide_differences) > 0
    summary = pd.DataFrame(
        [
            {
                "CONDITION": "unique tracking match rate >= 0.80",
                "ESTIMATE": match_metrics["TRACKING_MATCH_RATE"],
                "THRESHOLD": 0.80,
                "STATUS": "PASS" if match_metrics["TRACKING_MATCH_RATE"] >= 0.80 else "FAIL",
            },
            {
                "CONDITION": "defender log-loss gain >= 0.0005 with CI above zero",
                "ESTIMATE": logloss.IMPROVEMENT,
                "THRESHOLD": 0.0005,
                "STATUS": "PASS" if materially_improves else "UNINFORMATIVE",
            },
            {
                "CONDITION": "positive exposure retained >= 0.50",
                "ESTIMATE": exposure_retained,
                "THRESHOLD": 0.50,
                "STATUS": "PASS" if exposure_retained >= 0.50 else "FAIL",
            },
            {
                "CONDITION": "team exposure-rank rho >= 0.50",
                "ESTIMATE": rank["SPEARMAN_RHO"],
                "THRESHOLD": 0.50,
                "STATUS": "PASS" if rank["SPEARMAN_RHO"] >= 0.50 else "FAIL",
            },
            {
                "CONDITION": "open and wide-open cases exceed matched controls",
                "ESTIMATE": min(open_wide_differences) if open_wide_differences else np.nan,
                "THRESHOLD": 0.0,
                "STATUS": "PASS" if open_survives else "FAIL",
            },
        ]
    )
    summary["LOGLOSS_CI_LOW"] = logloss.LOW
    summary["LOGLOSS_CI_HIGH"] = logloss.HIGH
    summary["PAINT_EXPOSURE_RETAINED"] = paint_retained
    summary["PUBLISHED_TO_AWARE_RANK_RHO"] = published_rank["SPEARMAN_RHO"]
    summary.to_csv(REPORTS / "team_validation_gate2_summary.csv", index=False)
    print("=== Gate 2: closest-defender distance ===")
    print(summary.round(5).to_string(index=False))
    print("\n=== model calibration ===")
    print(model_metrics.round(5).to_string(index=False))
    print(improvement.round(5).to_string(index=False))
    print("\n=== open-shot matched controls ===")
    print(open_control.round(5).to_string(index=False))


def cmd_team_review_sample() -> None:
    """Build the frozen, private 200-possession worksheet for human Gate-4 coding."""
    from pathlib import Path

    from possval.models.foul_value import (
        foul_repriced_actions,
        historical_foul_premium,
        shooting_foul_events,
    )
    from possval.models.rebound import possession_panel
    from possval.models.review import select_review_sample
    from possval.models.team_profiles import score_against_team_curve
    from possval.models.value import shot_value, team_curves

    panel = pd.read_parquet(PROCESSED / "chance_panel.parquet")
    shots_all = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    shots = shots_all[shots_all.GAME_CLOCK_EXPIRING.eq(0)]
    outcomes = pd.read_parquet(PROCESSED / "shot_outcomes.parquet")
    held = panel[panel.SEASON.between(2022, 2023)]
    chained = possession_panel(held, points_column="PTS_ALL")
    chained = chained[~chained.PERIOD_EXPIRED]
    curves = team_curves(chained, min_possessions=5_000)
    second_chance = float(
        chained[chained.START_TYPE.eq("off_rebound")].PTS_POSS.mean()
    )
    official = shot_value(
        shots[shots.SEASON.between(2022, 2023)],
        outcomes[outcomes.SEASON.between(2022, 2023)],
        second_chance,
    )
    fouls = pd.concat(
        [
            shooting_foul_events(
                pd.read_parquet(PROCESSED / f"pbp_clock_{season}.parquet")
            )
            for season in range(2015, 2024)
        ],
        ignore_index=True,
    )
    foul_only = fouls[~fouls.AND_ONE]
    denominator = pd.concat(
        [shots_all[["PLAYER_ID", "SEASON"]], foul_only[["PLAYER_ID", "SEASON"]]],
        ignore_index=True,
    )
    premiums = historical_foul_premium(
        denominator,
        fouls,
        train_through=2021,
        prior_strength=200,
    )
    held_foul = foul_only[
        foul_only.SEASON.between(2022, 2023)
        & foul_only.SHOT_CLOCK.notna()
        & foul_only.GAME_CLOCK.ge(3)
    ]
    valued = foul_repriced_actions(official, held_foul, premiums)
    scored = score_against_team_curve(valued, curves)
    worksheet, key = select_review_sample(scored)
    private = Path(".review")
    private.mkdir(exist_ok=True)
    worksheet.to_csv(private / "team_review_worksheet.csv", index=False)
    key.to_csv(private / "team_review_key.csv", index=False)
    print("wrote blinded worksheet and closed key under .review/ (gitignored)")
    print(key.SAMPLE_GROUP.value_counts().to_string())



def cmd_endgame(window: str) -> None:
    """Is there a sawtooth in end-of-period possession value for a 2-for-1 to exploit?

    Exploratory and **post hoc** relative to `preregistration_twoforone.md`, which registered
    H6a-c and nothing here. Labelled as such wherever it is reported.
    """
    from scipy import stats

    from possval.models.endgame import (
        ball_value,
        flatness,
        handover_behaviour,
        handover_identity,
        mechanical_benchmark,
        possession_level,
        selection_bias,
    )
    from possval.models.twoforone import window as build_window

    first, last = SITUATIONAL_WINDOWS[window]
    pd.set_option("display.width", 200)
    print(f"=== window: {window} ({first}-{str(first + 1)[-2:]} to "
          f"{last}-{str(last + 1)[-2:]}) — POST HOC, not pre-registered ===")

    panel = pd.read_parquet(PROCESSED / "chance_panel.parquet")
    panel = panel[panel.SEASON.between(first, last)]
    poss = possession_level(panel)
    print(f"{len(poss):,} possessions")

    values = ball_value(poss)
    values.to_csv(REPORTS / f"endgame_ball_value_{window}.csv", index=False)
    print("\nV_ball(S), net points to the buzzer for the team holding the ball:")
    print(f"  range {values.V_BALL.min():.3f}-{values.V_BALL.max():.3f}, "
          f"mean {values.V_BALL.mean():.3f}, per-bin SE {values.SE.mean():.4f}")

    identity = handover_identity(poss, values)
    print(f"accounting check (ending at S should be worth -V_ball(S)): "
          f"r={identity['correlation']:.3f}, bias={identity['bias']:+.3f}")

    shape = flatness(values)
    p_value = 1 - stats.chi2.cdf(shape["chi_square"], shape["dof"])
    print(f"\nstructure beyond a smooth trend: chi2={shape['chi_square']:.1f} on "
          f"{shape['dof']} dof, p={p_value:.4f}")
    print(f"  amplitude {shape['structure_amplitude']:.4f} pts against a noise floor of "
          f"{shape['noise_floor']:.4f}")

    mechanical = mechanical_benchmark(poss).set_index("S").V_MECHANICAL.loc[6:45]
    print(f"  the alternating-possession model predicts "
          f"{mechanical.max() - mechanical.min():.3f} pts of sawtooth "
          f"(peak S={mechanical.idxmax()}, trough S={mechanical.idxmin()}) — it does not "
          f"survive validation; see its docstring")

    behaviour = handover_behaviour(poss, values)
    behaviour.to_csv(REPORTS / f"endgame_handover_{window}.csv", index=False)

    print("\n=== the observational answer, which is wrong ===")
    rows = []
    for band in ((28, 32), (32, 36), (36, 40)):
        rows.append(selection_bias(build_window(panel), band))
    table = pd.DataFrame(rows)
    print(table.round(3).to_string(index=False))
    table.to_csv(REPORTS / f"endgame_selection_bias_{window}.csv", index=False)
    print("set against the quasi-experimental estimate in twoforone: +0.009 / +0.044")


def cmd_situational(window: str, n_null_draws: int = 50) -> None:
    """H4 and H5 from `reports/preregistration_situational.md`.

    Run `--window explore` first. `--window holdout` is a one-shot confirmation and running it
    before the hypotheses are frozen would defeat the entire protocol.
    """
    from possval.models.situational import (
        band_quantile_sweep,
        band_signal_share,
        concentration_panel,
        fit_concentration,
        team_band_relaxation,
    )
    from possval.models.stopping import chance_panel, continuation_value

    first, last = SITUATIONAL_WINDOWS[window]
    pd.set_option("display.width", 200)
    print(f"=== window: {window} ({first}-{str(first + 1)[-2:]} to "
          f"{last}-{str(last + 1)[-2:]}) ===")

    panel_path = PROCESSED / "chance_panel.parquet"
    panel = pd.read_parquet(panel_path) if panel_path.exists() else chance_panel(2015, 2024)
    panel = panel[panel.SEASON.between(first, last)]

    shots = pd.read_parquet(PROCESSED / "shots_scored.parquet")
    shots = shots[(shots.GAME_CLOCK_EXPIRING == 0) & shots.SEASON.between(first, last)]
    print(f"{len(panel):,} chances, {len(shots):,} shots")

    values = continuation_value(panel)

    print("\n=== H4a: league relaxation by band, every boundary quantile ===")
    sweep = band_quantile_sweep(shots, values)
    print(sweep.round(4).to_string(index=False))
    sweep.to_csv(REPORTS / f"situational_band_league_{window}.csv", index=False)

    print("\n=== H4b: per-team band ratios, and how much of the spread is real ===")
    teams = team_band_relaxation(shots, panel)
    teams.to_csv(REPORTS / f"situational_band_teams_{window}.csv", index=False)
    signal = band_signal_share(shots, panel, n_draws=n_null_draws)
    print(signal.round(4).to_string(index=False))
    signal.to_csv(REPORTS / f"situational_band_signal_{window}.csv", index=False)

    late = signal[signal.BAND == "late"].signal_share
    early = signal[signal.BAND == "early"].signal_share
    if len(late) and len(early):
        held = float(late.iloc[0]) > float(early.iloc[0])
        verdict = "as predicted" if held else "PREDICTION FAILS"
        print(f"\nH4 prediction (late > early): {float(late.iloc[0]):.3f} vs "
              f"{float(early.iloc[0]):.3f} — {verdict}")

    print("\n=== H5: does concentrating the late clock pay? ===")
    concentration = concentration_panel(shots, panel)
    concentration.to_csv(REPORTS / f"situational_concentration_panel_{window}.csv", index=False)
    print(f"{len(concentration)} team-seasons; "
          f"HHI_LATE {concentration.HHI_LATE.min():.3f}-{concentration.HHI_LATE.max():.3f}, "
          f"FUNNEL {concentration.FUNNEL.min():+.3f} to {concentration.FUNNEL.max():+.3f}")

    # The two registered specifications, then the placebo. The placebo is **post hoc** — it was
    # written after H5 confirmed, and the protocol requires saying so wherever it appears. It
    # asks the question a confirmation has to survive: if concentrating the late clock is a
    # late-clock effect, concentration must *not* predict efficiency on the chances that ended
    # before the late clock. Swapping outcome and control does exactly that.
    specifications = [
        ("registered", "HHI_LATE", "PPC_LATE", "PPC_EARLY"),
        ("registered", "FUNNEL", "PPC_LATE", "PPC_EARLY"),
        ("post hoc placebo", "HHI_LATE", "PPC_EARLY", "PPC_LATE"),
        ("post hoc placebo", "FUNNEL", "PPC_EARLY", "PPC_LATE"),
    ]
    fits = pd.DataFrame(
        [
            {"spec": spec, **fit_concentration(concentration, treatment=t, outcome=o, control=c)}
            for spec, t, o, c in specifications
        ]
    )
    print(fits.round(4).to_string(index=False))
    fits.to_csv(REPORTS / f"situational_concentration_{window}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="possval.pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("ingest", "clock", "validate", "scorecard"):
        p = sub.add_parser(name)
        p.add_argument("--season", type=int, default=2024, help="season start year")
    for name in ("backfill", "train", "score", "lineups", "lineup-test", "synergy",
                 "rulechange", "ablate", "stopping", "winprob", "rebound"):
        p = sub.add_parser(name)
        p.add_argument("--first", type=int, default=2015)
        p.add_argument("--last", type=int, default=2024)

    # Ratings run one season past the rest: the projection needs 2025-26 as its prior season,
    # and that season has no clock reconstruction behind it.
    ratings = sub.add_parser("ratings")
    ratings.add_argument("--first", type=int, default=2015)
    ratings.add_argument("--last", type=int, default=2025)

    project = sub.add_parser("project")
    project.add_argument("--sims", type=int, default=20_000)
    project.add_argument(
        "--games", type=int, default=None,
        help="project every player to this many games; omit to keep 2025-26 minutes as played",
    )
    project.add_argument(
        "--rating-sd", type=float, default=None,
        help="rating uncertainty; defaults to the year-over-year figure (3.95)",
    )

    for name in ("situational", "twoforone", "endgame", "value"):
        p = sub.add_parser(name)
        p.add_argument("--window", choices=sorted(SITUATIONAL_WINDOWS), default="explore")

    sub.add_parser("prospective")
    sub.add_parser("mechanisms")
    validation = sub.add_parser("team-validation")
    validation.add_argument("--null-draws", type=int, default=50)
    temporal = sub.add_parser("team-temporal-validation")
    temporal.add_argument("--null-draws", type=int, default=50)
    defender = sub.add_parser("defender-extract")
    defender.add_argument("--source", required=True)
    defender.add_argument("--output", required=True)
    defender_validation = sub.add_parser("defender-validation")
    defender_validation.add_argument("--tracking", required=True)
    sub.add_parser("team-review-sample")

    args = parser.parse_args()
    if args.command == "project":
        cmd_project(args.sims, args.games, args.rating_sd)
        return
    if args.command == "prospective":
        cmd_prospective()
        return
    if args.command == "mechanisms":
        cmd_mechanisms()
        return
    if args.command == "team-validation":
        cmd_team_validation(args.null_draws)
        return
    if args.command == "team-temporal-validation":
        cmd_team_temporal_validation(args.null_draws)
        return
    if args.command == "defender-extract":
        cmd_defender_extract(args.source, args.output)
        return
    if args.command == "defender-validation":
        cmd_defender_validation(args.tracking)
        return
    if args.command == "team-review-sample":
        cmd_team_review_sample()
        return
    if args.command in ("situational", "twoforone", "endgame", "value"):
        {
            "situational": cmd_situational,
            "twoforone": cmd_twoforone,
            "endgame": cmd_endgame,
            "value": cmd_value,
        }[args.command](args.window)
        return

    ranged = {
        "backfill": cmd_backfill,
        "train": cmd_train,
        "score": cmd_score,
        "lineups": cmd_lineups,
        "lineup-test": cmd_lineup_test,
        "synergy": cmd_synergy,
        "rulechange": cmd_rulechange,
        "ablate": cmd_ablate,
        "stopping": cmd_stopping,
        "rebound": cmd_rebound,
        "winprob": cmd_winprob,
        "ratings": cmd_ratings,
    }
    if args.command in ranged:
        ranged[args.command](args.first, args.last)
        return
    {
        "ingest": cmd_ingest,
        "clock": cmd_clock,
        "validate": cmd_validate,
        "scorecard": cmd_scorecard,
    }[args.command](args.season)


if __name__ == "__main__":
    main()
