"""Command-line entry points for the data pipeline.

    python -m possval.pipeline ingest   --season 2024
    python -m possval.pipeline clock    --season 2024
    python -m possval.pipeline validate --season 2024
"""

from __future__ import annotations

import argparse

import pandas as pd

from possval.clock import reconstruct_season
from possval.clock import validate as V
from possval.ingest import load_season
from possval.paths import PROCESSED, ensure_dirs

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


def cmd_clock(season: int) -> None:
    ensure_dirs()
    pbp = load_season("nbastats", season)
    recon = reconstruct_season(pbp, season)
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="possval.pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("ingest", "clock", "validate"):
        p = sub.add_parser(name)
        p.add_argument("--season", type=int, default=2024, help="season start year")

    args = parser.parse_args()
    {"ingest": cmd_ingest, "clock": cmd_clock, "validate": cmd_validate}[args.command](
        args.season
    )


if __name__ == "__main__":
    main()
