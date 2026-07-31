"""Bulk ingest of pre-scraped NBA data from github.com/shufinskiy/nba_data.

Why bulk rather than scraping: the archives are already-collected stats.nba.com responses,
so a full 10-season backfill is a few hundred MB of HTTP instead of ~12k rate-limited API
calls. The previous Selenium scraper in this repo took minutes per shot-clock bucket for one
season and broke whenever nba.com changed its markup.

Season keys are *start* years: the 2024-25 season is `2024`.

Datasets used here:
  nbastats    - stats.nba.com playbyplayv2, one row per PBP event   (1996-2024)
  shotdetail  - stats.nba.com shotchartdetail, one row per FGA      (1996-2025)
"""

from __future__ import annotations

import io
import tarfile
import time
from pathlib import Path

import pandas as pd
import requests

from possval.paths import PROCESSED, RAW

BASE_URL = "https://github.com/shufinskiy/nba_data/raw/main/datasets"

# Dataset -> (first season with data, last season with data)
COVERAGE = {
    "nbastats": (1996, 2024),
    "shotdetail": (1996, 2025),
    "pbpstats": (2000, 2024),
    "nbastatsv3": (1996, 2025),
    "matchups": (2017, 2025),
}


def seasons_available(dataset: str) -> range:
    lo, hi = COVERAGE[dataset]
    return range(lo, hi + 1)


def season_label(season: int) -> str:
    """2024 -> '2024-25', matching NBA's own season string."""
    return f"{season}-{str(season + 1)[-2:]}"


def _archive_url(dataset: str, season: int, playoffs: bool = False) -> str:
    suffix = "_po" if playoffs else ""
    return f"{BASE_URL}/{dataset}{suffix}_{season}.tar.xz"


def download_archive(
    dataset: str, season: int, playoffs: bool = False, attempts: int = 4
) -> Path:
    """Download a .tar.xz to data/raw/, skipping if already present.

    Retries on truncated responses: GitHub's raw endpoint intermittently closes a connection
    mid-body, which surfaces as ChunkedEncodingError and killed a season of a 10-year
    backfill. The download is written to a .partial file and only renamed on success, so a
    failed attempt can never be mistaken for a complete archive.
    """
    if season not in seasons_available(dataset):
        lo, hi = COVERAGE[dataset]
        raise ValueError(f"{dataset} covers {lo}-{hi}; asked for {season}")

    RAW.mkdir(parents=True, exist_ok=True)
    suffix = "_po" if playoffs else ""
    dest = RAW / f"{dataset}{suffix}_{season}.tar.xz"
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    url = _archive_url(dataset, season, playoffs)
    tmp = dest.with_suffix(".partial")
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            with requests.get(url, stream=True, timeout=300) as resp:
                resp.raise_for_status()
                expected = int(resp.headers.get("Content-Length", 0))
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
            written = tmp.stat().st_size
            if expected and written != expected:
                raise OSError(f"truncated: got {written} of {expected} bytes")
            tmp.rename(dest)
            return dest
        except (requests.RequestException, OSError) as exc:
            last_error = exc
            tmp.unlink(missing_ok=True)
            if attempt < attempts:
                time.sleep(2**attempt)

    raise RuntimeError(f"failed to download {url} after {attempts} attempts") from last_error


def read_archive(path: Path) -> pd.DataFrame:
    """Extract the single CSV inside a .tar.xz into a DataFrame (in memory, no temp files)."""
    with tarfile.open(path, "r:xz") as tar:
        members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(".csv")]
        if not members:
            raise ValueError(f"no CSV inside {path}")
        frames = []
        for member in members:
            fh = tar.extractfile(member)
            if fh is None:
                continue
            frames.append(pd.read_csv(io.BytesIO(fh.read()), low_memory=False))
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


def load_season(
    dataset: str,
    season: int,
    playoffs: bool = False,
    refresh: bool = False,
) -> pd.DataFrame:
    """Download (if needed), parse, and cache one season as Parquet. Returns the frame.

    Parquet cache lives in data/processed/<dataset>/season=<year>/data.parquet so DuckDB
    can read the whole backfill with a single glob and Hive-style partition discovery.
    """
    part_dir = PROCESSED / dataset / f"season={season}{'_po' if playoffs else ''}"
    parquet = part_dir / "data.parquet"

    if parquet.exists() and not refresh:
        return pd.read_parquet(parquet)

    archive = download_archive(dataset, season, playoffs)
    df = read_archive(archive)
    df["SEASON"] = season
    df["SEASON_LABEL"] = season_label(season)
    df["IS_PLAYOFFS"] = playoffs

    part_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet, index=False, compression="zstd")
    return df
