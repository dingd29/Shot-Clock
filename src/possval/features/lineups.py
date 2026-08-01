"""On-court lineups, derived from play-by-play substitutions.

Needed to retest the creation-overlap null (`models/synergy.py`) at the level where
redundancy would actually bite. The team-season test found nothing, but a team's top
creators do not share the floor for all their minutes, so a real effect could wash out
there and still exist five-on-five.

Derivation is delegated to `nba_on_court` (same author as the bulk archives, so it takes
the `nbastats` schema unchanged). It reads each period's substitutions backwards to recover
who started the period, then walks forward.

**Compatibility note.** nba-on-court 0.2.1 declares `numpy<2` and means it: it calls
`np.in1d`, removed in numpy 2.0. Downgrading numpy is not an option here because scipy
>=1.18 and scikit-learn require numpy 2. `np.in1d` was deprecated *in favour of* `np.isin`
with identical semantics for the 1-D integer arrays used, so the alias is restored below
rather than pinning the whole project backwards. Correctness is not assumed — it is checked
by `validate_lineups`, which asserts ten distinct players, five per side, on every row.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ON_COURT_COLUMNS = [f"{side}_PLAYER{i}" for side in ("HOME", "AWAY") for i in range(1, 6)]


def _patch_numpy_aliases() -> None:
    """Restore numpy aliases nba-on-court depends on. See module docstring."""
    if not hasattr(np, "in1d"):
        np.in1d = np.isin


def lineups_for_game(game_events: pd.DataFrame, keys_only: bool = False) -> pd.DataFrame:
    """Attach the ten on-court player ids to every event of one game.

    `keys_only` returns just GAME_ID, EVENTNUM and the ten columns. Prefer it: the library
    rewrites some passed-through columns (PCTIMESTRING comes back as elapsed seconds rather
    than the original clock string), so merging the ids back onto our own frame by
    (GAME_ID, EVENTNUM) is safer than trusting everything it hands back.
    """
    _patch_numpy_aliases()
    import nba_on_court as noc

    # The library indexes positionally into the frame it is given, so a slice carrying its
    # parent's index raises KeyError: 0. Only the first game of a season survives without
    # this reset — which is exactly how the bug hid.
    out = noc.players_on_court(game_events.reset_index(drop=True).copy())
    derived = [c for c in out.columns if c not in game_events.columns]
    out = out.rename(columns=dict(zip(derived, ON_COURT_COLUMNS[: len(derived)], strict=False)))
    if keys_only:
        return out[["GAME_ID", "EVENTNUM", *ON_COURT_COLUMNS]]
    return out


def validate_lineups(lineups: pd.DataFrame) -> dict:
    """Check the derivation rather than trusting it.

    Two properties must hold on every event: exactly ten distinct players on court, and
    five from each team. A period-start inference that guessed wrong shows up here.
    """
    cols = [c for c in ON_COURT_COLUMNS if c in lineups.columns]
    if len(cols) != 10:
        return {"ok": False, "reason": f"expected 10 on-court columns, found {len(cols)}"}

    values = lineups[cols].to_numpy()
    distinct = np.array([len(set(row)) for row in values])
    home_zero = (values[:, :5] == 0).any(axis=1)
    away_zero = (values[:, 5:] == 0).any(axis=1)

    return {
        "ok": bool((distinct == 10).all() and not home_zero.any() and not away_zero.any()),
        "n_events": len(lineups),
        "pct_ten_distinct": float((distinct == 10).mean()),
        "n_with_missing_player": int((home_zero | away_zero).sum()),
    }


def lineups_for_season(
    pbp: pd.DataFrame, progress: bool = True, max_failed_share: float = 0.02
) -> pd.DataFrame:
    """Run the derivation across a season.

    Raises rather than returning a thin result if too many games fail: a silently truncated
    lineup table would poison every downstream regression while looking healthy.
    """
    games = list(pbp.groupby("GAME_ID", sort=True))
    if progress:
        try:
            from tqdm import tqdm

            games = tqdm(games, desc="lineups")
        except ImportError:
            pass

    frames, failed, errors = [], [], {}
    for game_id, events in games:
        try:
            frames.append(lineups_for_game(events, keys_only=True))
        except Exception as exc:
            failed.append(game_id)
            # Keep the reason. Swallowing it silently once made a 100% failure rate look
            # like a handful of unresolvable games.
            reason = f"{type(exc).__name__}: {exc}"
            errors[reason] = errors.get(reason, 0) + 1

    total = len(frames) + len(failed)
    if len(failed) > max_failed_share * total:
        raise RuntimeError(
            f"{len(failed)} of {total} games failed to resolve, above the "
            f"{max_failed_share:.0%} tolerance. Errors: {errors}"
        )

    result = pd.concat(frames, ignore_index=True)
    result.attrs["failed_games"] = failed
    result.attrs["errors"] = errors
    return result


def stint_table(lineups: pd.DataFrame) -> pd.DataFrame:
    """Collapse events into stints: a contiguous run with the same ten players on court.

    The unit a lineup-level analysis actually wants — one row per (game, period, lineup),
    carrying the possessions and points that occurred while those ten were together.
    """
    cols = [c for c in ON_COURT_COLUMNS if c in lineups.columns]
    df = lineups.copy()
    key = df[cols].astype(str).agg("|".join, axis=1)
    df["LINEUP_KEY"] = key
    df["STINT_ID"] = (key != key.shift()).cumsum()

    return (
        df.groupby(["GAME_ID", "PERIOD", "STINT_ID", "LINEUP_KEY"], observed=True)
        .agg(N_EVENTS=("EVENTNUM", "size"), FIRST_EVENT=("EVENTNUM", "min"))
        .reset_index()
    )
