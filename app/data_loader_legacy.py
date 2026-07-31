from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd


DATA_PATH = Path(__file__).resolve().parent.parent / "nba_shotclock_data.csv"


def map_action_to_play_type(action_type: str) -> str:
    """Map ACTION_TYPE to play_type categories."""
    action_lower = action_type.lower()
    
    # Pick and Roll Ball Handler
    if any(x in action_lower for x in ['pullup', 'step back', 'running pull']):
        return "PnR Ball Handler"
    
    # Pick and Roll Roll Man
    if any(x in action_lower for x in ['cutting', 'alley oop', 'putback', 'tip']):
        return "PnR Roll Man"
    
    # Isolation
    if any(x in action_lower for x in ['fadeaway', 'turnaround', 'isolation']):
        return "Isolation"
    
    # Drive & Kick
    if any(x in action_lower for x in ['driving', 'floating', 'finger roll', 'reverse layup']):
        return "Drive & Kick"
    
    # Spot-Up (default for jump shots)
    if 'jump shot' in action_lower or 'shot' in action_lower:
        return "Spot-Up"
    
    # Default fallback
    return "Other"


def estimate_shot_clock_phase(minutes: int, seconds: int, period: int) -> str:
    """
    Estimate shot clock phase from game clock.
    This is a rough approximation - actual shot clock data would be better.
    """
    # Very rough heuristic: later in shot clock = later in game clock
    # This is not accurate but provides some grouping
    total_seconds = minutes * 60 + seconds
    
    # In early periods, shots tend to be earlier in shot clock
    # In late periods, more late shot clock situations
    if period <= 2:
        # Early game - assume more early shot clock
        if total_seconds > 600:  # > 10 min
            return "17-24"
        elif total_seconds > 300:  # > 5 min
            return "9-16"
        else:
            return "0-8"
    else:
        # Late game - assume more late shot clock
        if total_seconds > 600:
            return "0-8"
        elif total_seconds > 300:
            return "9-16"
        else:
            return "17-24"


@lru_cache(maxsize=1)
def load_shot_clock_data() -> pd.DataFrame:
    """Load shot clock data from CSV."""
    df = pd.read_csv(DATA_PATH)
    
    # Clean column names (remove leading/trailing spaces)
    df.columns = df.columns.str.strip()
    
    # Ensure SHOT_CLOCK_RANGE is treated as categorical with proper order
    shot_clock_order = ["24-22", "22-18", "18-15", "15-7", "7-4", "4-0"]
    df["SHOT_CLOCK_RANGE"] = pd.Categorical(
        df["SHOT_CLOCK_RANGE"], 
        categories=shot_clock_order, 
        ordered=True
    )
    
    # Fill NaN values in numeric columns with 0
    numeric_cols = ['FGM', 'FGA', 'FG3M', 'FG3A', 'FG2M', 'FG2A', 'GP', 'G']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Calculate points per game (approximate from FGM and FG3M)
    # Points = 2 * FG2M + 3 * FG3M
    df["POINTS"] = 2 * df["FG2M"] + 3 * df["FG3M"]
    
    return df


@lru_cache(maxsize=1)
def get_team_data() -> pd.DataFrame:
    """Aggregate data by team and shot clock range."""
    df = load_shot_clock_data()
    
    # Group by team and shot clock range
    team_data = df.groupby(["PLAYER_LAST_TEAM_ABBREVIATION", "SHOT_CLOCK_RANGE"], as_index=False, observed=True).agg(
        TOTAL_FGM=("FGM", "sum"),
        TOTAL_FGA=("FGA", "sum"),
        TOTAL_FG3M=("FG3M", "sum"),
        TOTAL_FG3A=("FG3A", "sum"),
        TOTAL_FG2M=("FG2M", "sum"),
        TOTAL_FG2A=("FG2A", "sum"),
        TOTAL_POINTS=("POINTS", "sum"),
        NUM_PLAYERS=("PLAYER_ID", "nunique"),
        TOTAL_GP=("GP", "sum"),
    )
    
    # Calculate percentages
    team_data["FG_PCT"] = (team_data["TOTAL_FGM"] / team_data["TOTAL_FGA"]).fillna(0)
    team_data["FG3_PCT"] = (team_data["TOTAL_FG3M"] / team_data["TOTAL_FG3A"]).fillna(0)
    team_data["EFG_PCT"] = (
        (team_data["TOTAL_FGM"] + 0.5 * team_data["TOTAL_FG3M"]) / team_data["TOTAL_FGA"]
    ).fillna(0)
    
    # Points per attempt (approximate efficiency metric)
    team_data["PTS_PER_FGA"] = (team_data["TOTAL_POINTS"] / team_data["TOTAL_FGA"]).fillna(0)
    
    return team_data


@lru_cache(maxsize=1)
def get_player_data() -> pd.DataFrame:
    """Get player-level data with shot clock ranges."""
    df = load_shot_clock_data()
    
    # Calculate additional metrics
    df["PTS_PER_FGA"] = (df["POINTS"] / df["FGA"]).fillna(0)
    
    # Filter out players with very few attempts for meaningful analysis
    df = df[df["FGA"] >= 0.5].copy()  # At least 0.5 FGA per game (minimum threshold)
    
    return df
