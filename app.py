from __future__ import annotations

import math
from typing import Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.data_loader import load_shot_clock_data, get_team_data, get_player_data

SHOT_CLOCK_ORDER: Sequence[str] = ("24-22", "22-18", "18-15", "15-7", "7-4", "4-0")
SHOT_CLOCK_LABELS = {
    "24-22": "24-22s (Very Early)",
    "22-18": "22-18s (Very Early)",
    "18-15": "18-15s (Early)",
    "15-7": "15-7s (Average)",
    "7-4": "7-4s (Late)",
    "4-0": "4-0s (Very Late)"
}


def main() -> None:
    st.set_page_config(
        page_title="NBA Shot-Clock Performance Dashboard",
        page_icon="https://upload.wikimedia.org/wikipedia/en/thumb/0/03/National_Basketball_Association_logo.svg/529px-National_Basketball_Association_logo.svg.png",
        layout="wide",
    )
    st.title("NBA Shot-Clock Performance Dashboard")
    st.caption(
        "Analyze how teams and players perform across different shot clock scenarios. "
        "Data from 2024-25 Regular Season."
    )

    # Load data
    with st.spinner("Loading data..."):
        raw_df = load_shot_clock_data()
        team_df = get_team_data()
        player_df = get_player_data()

    # Sidebar filters
    st.sidebar.header("📊 Filters")
    
    # Shot clock range filter
    selected_ranges = st.sidebar.multiselect(
        "Shot Clock Ranges",
        options=list(SHOT_CLOCK_ORDER),
        default=list(SHOT_CLOCK_ORDER),
        format_func=lambda x: SHOT_CLOCK_LABELS.get(x, x)
    )
    
    # Team filter
    all_teams = sorted(team_df["PLAYER_LAST_TEAM_ABBREVIATION"].unique())
    selected_teams = st.sidebar.multiselect(
        "Teams",
        options=all_teams,
        default=all_teams
    )
    
    # Player filter (with search)
    all_players = sorted(player_df["PLAYER_NAME"].unique())
    player_search = st.sidebar.text_input("🔍 Search Player", "")
    if player_search:
        filtered_players = [p for p in all_players if player_search.lower() in p.lower()]
    else:
        filtered_players = all_players
    
    selected_players = st.sidebar.multiselect(
        "Players",
        options=filtered_players,
        default=[]
    )
    
    # Minimum attempts filter for players
    min_fga = st.sidebar.slider(
        "Minimum FGA per Game (Player Analysis)",
        min_value=0.0,
        max_value=5.0,
        value=1.0,
        step=0.1
    )

    # Filter data
    team_filtered = team_df[
        (team_df["SHOT_CLOCK_RANGE"].isin(selected_ranges)) &
        (team_df["PLAYER_LAST_TEAM_ABBREVIATION"].isin(selected_teams))
    ].copy()
    
    player_filtered = player_df[
        (player_df["SHOT_CLOCK_RANGE"].isin(selected_ranges)) &
        (player_df["FGA"] >= min_fga)
    ].copy()
    
    if selected_players:
        player_filtered = player_filtered[player_filtered["PLAYER_NAME"].isin(selected_players)]

    # Main tabs
    tab1, tab2, tab3, tab4 = st.tabs(["Team Performance", "Player Performance", "Top Performers", "Detailed Data"])

    with tab1:
        st.header("Team Performance by Shot Clock Range")
        
        if team_filtered.empty:
            st.warning("No team data matches your filters.")
        else:
            # Team efficiency metrics
            col1, col2, col3, col4 = st.columns(4)
            
            total_fga = team_filtered["TOTAL_FGA"].sum()
            total_fgm = team_filtered["TOTAL_FGM"].sum()
            total_points = team_filtered["TOTAL_POINTS"].sum()
            
            overall_fg_pct = (total_fgm / total_fga * 100) if total_fga > 0 else 0
            overall_efg_pct = (
                (total_fgm + 0.5 * team_filtered["TOTAL_FG3M"].sum()) / total_fga * 100
                if total_fga > 0 else 0
            )
            overall_pts_per_fga = (total_points / total_fga) if total_fga > 0 else 0
            
            col1.metric("Total FGA", f"{total_fga:,.0f}")
            col2.metric("FG%", f"{overall_fg_pct:.1f}%")
            col3.metric("eFG%", f"{overall_efg_pct:.1f}%")
            col4.metric("Pts/FGA", f"{overall_pts_per_fga:.2f}")

            st.divider()

            # Team efficiency by shot clock range
            team_by_range = team_filtered.groupby("SHOT_CLOCK_RANGE", as_index=False, observed=True).agg({
                "TOTAL_FGM": "sum",
                "TOTAL_FGA": "sum",
                "TOTAL_FG3M": "sum",
                "TOTAL_POINTS": "sum",
                "EFG_PCT": "mean"
            })
            team_by_range["FG_PCT"] = (team_by_range["TOTAL_FGM"] / team_by_range["TOTAL_FGA"] * 100).fillna(0)
            team_by_range["PTS_PER_FGA"] = (team_by_range["TOTAL_POINTS"] / team_by_range["TOTAL_FGA"]).fillna(0)
            team_by_range["EFG_PCT"] = team_by_range["EFG_PCT"] * 100
            
            # Ensure SHOT_CLOCK_RANGE is categorical and sorted correctly
            team_by_range["SHOT_CLOCK_RANGE"] = pd.Categorical(
                team_by_range["SHOT_CLOCK_RANGE"],
                categories=SHOT_CLOCK_ORDER,
                ordered=True
            )
            team_by_range = team_by_range.sort_values("SHOT_CLOCK_RANGE")
            
            # Chart 1: FG% by shot clock range
            fig1 = px.bar(
                team_by_range,
                x="SHOT_CLOCK_RANGE",
                y="FG_PCT",
                title="Field Goal Percentage by Shot Clock Range",
                labels={"SHOT_CLOCK_RANGE": "Shot Clock Range", "FG_PCT": "FG%"},
                text_auto=".1f",
                color="FG_PCT",
                color_continuous_scale="RdYlGn",
                category_orders={"SHOT_CLOCK_RANGE": list(SHOT_CLOCK_ORDER)}
            )
            fig1.update_layout(
                showlegend=False,
                yaxis_title="FG%",
                xaxis_type="category"
            )
            st.plotly_chart(fig1, use_container_width=True)
            
            # Chart 2: Points per FGA by shot clock range
            fig2 = px.bar(
                team_by_range,
                x="SHOT_CLOCK_RANGE",
                y="PTS_PER_FGA",
                title="Points per Field Goal Attempt by Shot Clock Range",
                labels={"SHOT_CLOCK_RANGE": "Shot Clock Range", "PTS_PER_FGA": "Points per FGA"},
                text_auto=".2f",
                color="PTS_PER_FGA",
                color_continuous_scale="RdYlGn",
                category_orders={"SHOT_CLOCK_RANGE": list(SHOT_CLOCK_ORDER)}
            )
            fig2.update_layout(
                showlegend=False,
                yaxis_title="Points per FGA",
                xaxis_type="category"
            )
            st.plotly_chart(fig2, use_container_width=True)
            
            # Team comparison heatmap
            st.subheader("Team Efficiency Heatmap")
            team_heatmap_data = team_filtered.pivot_table(
                index="PLAYER_LAST_TEAM_ABBREVIATION",
                columns="SHOT_CLOCK_RANGE",
                values="EFG_PCT",
                aggfunc="mean"
            ) * 100
            
            # Reorder columns to match SHOT_CLOCK_ORDER
            # Convert column names to strings to ensure proper ordering
            available_cols = [str(col) for col in team_heatmap_data.columns]
            ordered_cols = [col for col in SHOT_CLOCK_ORDER if col in available_cols]
            team_heatmap_data = team_heatmap_data[ordered_cols]
            team_heatmap_data = team_heatmap_data.sort_index()
            
            fig3 = px.imshow(
                team_heatmap_data,
                labels=dict(x="Shot Clock Range", y="Team", color="eFG%"),
                title="Team Effective FG% by Shot Clock Range",
                color_continuous_scale="RdYlGn",
                aspect="auto",
                text_auto=".1f"
            )
            fig3.update_layout(
                height=600,
                xaxis=dict(
                    type='category',
                    categoryorder='array',
                    categoryarray=ordered_cols
                )
            )
            st.plotly_chart(fig3, use_container_width=True)
            
            # Team comparison chart
            st.subheader("Team Comparison")
            team_comparison = team_filtered.groupby("PLAYER_LAST_TEAM_ABBREVIATION", as_index=False).agg({
                "TOTAL_FGM": "sum",
                "TOTAL_FGA": "sum",
                "TOTAL_POINTS": "sum"
            })
            team_comparison["FG_PCT"] = (team_comparison["TOTAL_FGM"] / team_comparison["TOTAL_FGA"] * 100).fillna(0)
            team_comparison["PTS_PER_FGA"] = (team_comparison["TOTAL_POINTS"] / team_comparison["TOTAL_FGA"]).fillna(0)
            team_comparison = team_comparison.sort_values("PTS_PER_FGA", ascending=False)
            
            fig4 = px.bar(
                team_comparison.head(15),
                x="PLAYER_LAST_TEAM_ABBREVIATION",
                y="PTS_PER_FGA",
                title="Top 15 Teams by Points per FGA",
                labels={"PLAYER_LAST_TEAM_ABBREVIATION": "Team", "PTS_PER_FGA": "Points per FGA"},
        text_auto=".2f",
                color="PTS_PER_FGA",
                color_continuous_scale="RdYlGn"
            )
            fig4.update_layout(showlegend=False, xaxis_tickangle=-45)
            st.plotly_chart(fig4, use_container_width=True)

    with tab2:
        st.header("Player Performance by Shot Clock Range")
        
        if player_filtered.empty:
            st.warning("No player data matches your filters. Try adjusting the minimum FGA threshold.")
        else:
            # Player efficiency by shot clock range
            player_by_range = player_filtered.groupby("SHOT_CLOCK_RANGE", as_index=False, observed=True).agg({
                "FGM": "sum",
                "FGA": "sum",
                "FG3M": "sum",
                "POINTS": "sum",
                "EFG_PCT": "mean"
            })
            player_by_range["FG_PCT"] = (player_by_range["FGM"] / player_by_range["FGA"] * 100).fillna(0)
            player_by_range["PTS_PER_FGA"] = (player_by_range["POINTS"] / player_by_range["FGA"]).fillna(0)
            player_by_range["EFG_PCT"] = player_by_range["EFG_PCT"] * 100
            
            # Ensure SHOT_CLOCK_RANGE is categorical and sorted correctly
            player_by_range["SHOT_CLOCK_RANGE"] = pd.Categorical(
                player_by_range["SHOT_CLOCK_RANGE"],
                categories=SHOT_CLOCK_ORDER,
                ordered=True
            )
            player_by_range = player_by_range.sort_values("SHOT_CLOCK_RANGE")
            
            # Overall player metrics
            col1, col2, col3, col4 = st.columns(4)
            total_player_fga = player_by_range["FGA"].sum()
            total_player_fgm = player_by_range["FGM"].sum()
            total_player_points = player_by_range["POINTS"].sum()
            
            player_fg_pct = (total_player_fgm / total_player_fga * 100) if total_player_fga > 0 else 0
            player_efg_pct = (
                (total_player_fgm + 0.5 * player_by_range["FG3M"].sum()) / total_player_fga * 100
                if total_player_fga > 0 else 0
            )
            player_pts_per_fga = (total_player_points / total_player_fga) if total_player_fga > 0 else 0
            
            col1.metric("Total FGA", f"{total_player_fga:,.0f}")
            col2.metric("FG%", f"{player_fg_pct:.1f}%")
            col3.metric("eFG%", f"{player_efg_pct:.1f}%")
            col4.metric("Pts/FGA", f"{player_pts_per_fga:.2f}")
            
            st.divider()
            
            # Player efficiency by shot clock range
            fig5 = px.bar(
                player_by_range,
                x="SHOT_CLOCK_RANGE",
                y="FG_PCT",
                title="Player Field Goal Percentage by Shot Clock Range",
                labels={"SHOT_CLOCK_RANGE": "Shot Clock Range", "FG_PCT": "FG%"},
                text_auto=".1f",
                color="FG_PCT",
                color_continuous_scale="RdYlGn",
                category_orders={"SHOT_CLOCK_RANGE": list(SHOT_CLOCK_ORDER)}
            )
            fig5.update_layout(
                showlegend=False,
                yaxis_title="FG%",
                xaxis_type="category"
            )
            st.plotly_chart(fig5, use_container_width=True)
            
            # Individual player analysis
            if selected_players:
                st.subheader("Selected Players Performance")
                for player in selected_players:
                    player_data = player_filtered[player_filtered["PLAYER_NAME"] == player].copy()
                    if not player_data.empty:
                        # Ensure SHOT_CLOCK_RANGE is categorical and sorted correctly
                        player_data["SHOT_CLOCK_RANGE"] = pd.Categorical(
                            player_data["SHOT_CLOCK_RANGE"],
                            categories=SHOT_CLOCK_ORDER,
                            ordered=True
                        )
                        player_data = player_data.sort_values("SHOT_CLOCK_RANGE")
                        player_data["FG_PCT"] = (player_data["FGM"] / player_data["FGA"] * 100).fillna(0)
                        player_data["EFG_PCT"] = player_data["EFG_PCT"] * 100  # Convert to percentage
                        
                        fig_player = go.Figure()
                        fig_player.add_trace(go.Scatter(
                            x=player_data["SHOT_CLOCK_RANGE"].astype(str),
                            y=player_data["FG_PCT"],
                            mode='lines+markers',
                            name='FG%',
                            line=dict(color='blue', width=3),
                            marker=dict(size=10)
                        ))
                        fig_player.add_trace(go.Scatter(
                            x=player_data["SHOT_CLOCK_RANGE"].astype(str),
                            y=player_data["EFG_PCT"],
                            mode='lines+markers',
                            name='eFG%',
                            line=dict(color='green', width=3),
                            marker=dict(size=10)
                        ))
                        fig_player.update_layout(
                            title=f"{player} Performance by Shot Clock Range",
                            xaxis_title="Shot Clock Range",
                            yaxis_title="Percentage (%)",
                            hovermode='x unified',
                            height=400,
                            xaxis=dict(
                                type='category',
                                categoryorder='array',
                                categoryarray=list(SHOT_CLOCK_ORDER)
                            )
                        )
                        st.plotly_chart(fig_player, use_container_width=True)

    with tab3:
        st.header("Top Performers Analysis")
        
        # Top teams by shot clock range
        st.subheader("Top Teams by Shot Clock Range")
        
        for range_val in selected_ranges:
            range_data = team_filtered[team_filtered["SHOT_CLOCK_RANGE"] == range_val].copy()
            if not range_data.empty:
                range_data = range_data.sort_values("EFG_PCT", ascending=False).head(10)
                
                st.markdown(f"### {SHOT_CLOCK_LABELS.get(range_val, range_val)}")
                
                fig_top = px.bar(
                    range_data,
                    x="PLAYER_LAST_TEAM_ABBREVIATION",
                    y="EFG_PCT",
                    title=f"Top 10 Teams by eFG% - {SHOT_CLOCK_LABELS.get(range_val, range_val)}",
                    labels={"PLAYER_LAST_TEAM_ABBREVIATION": "Team", "EFG_PCT": "eFG%"},
                    text_auto=".1%",
                    color="EFG_PCT",
                    color_continuous_scale="RdYlGn"
                )
                fig_top.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig_top, use_container_width=True)
        
        st.divider()
        
        # Top players by shot clock range
        st.subheader("Top Players by Shot Clock Range")
        
        # Filter for meaningful sample size
        player_analysis = player_filtered[player_filtered["FGA"] >= min_fga].copy()
        
        for range_val in selected_ranges:
            range_player_data = player_analysis[player_analysis["SHOT_CLOCK_RANGE"] == range_val].copy()
            if not range_player_data.empty:
                # Calculate FG% for this range
                range_player_data["FG_PCT"] = (range_player_data["FGM"] / range_player_data["FGA"] * 100).fillna(0)
                range_player_data["PTS_PER_FGA"] = (range_player_data["POINTS"] / range_player_data["FGA"]).fillna(0)
                
                # Sort by eFG% and take top 15
                top_players = range_player_data.nlargest(15, "EFG_PCT")
                
                st.markdown(f"### {SHOT_CLOCK_LABELS.get(range_val, range_val)}")
                
                # Create display with team info
                top_players_display = top_players[[
                    "PLAYER_NAME", "PLAYER_LAST_TEAM_ABBREVIATION", 
                    "FGA", "FGM", "FG_PCT", "EFG_PCT", "PTS_PER_FGA"
                ]].copy()
                top_players_display["EFG_PCT"] = top_players_display["EFG_PCT"] * 100
                top_players_display = top_players_display.sort_values("EFG_PCT", ascending=False)
                
                fig_top_player = px.bar(
                    top_players_display,
                    x="PLAYER_NAME",
                    y="EFG_PCT",
                    color="PLAYER_LAST_TEAM_ABBREVIATION",
                    title=f"Top 15 Players by eFG% - {SHOT_CLOCK_LABELS.get(range_val, range_val)}",
                    labels={"PLAYER_NAME": "Player", "EFG_PCT": "eFG%", "PLAYER_LAST_TEAM_ABBREVIATION": "Team"},
                    text_auto=".1f",
                    hover_data=["FGA", "FGM", "FG_PCT", "PTS_PER_FGA"]
                )
                fig_top_player.update_layout(
                    xaxis_tickangle=-45,
                    height=500,
                    showlegend=True
                )
                st.plotly_chart(fig_top_player, use_container_width=True)

    with tab4:
        st.header("Detailed Data Tables")
        
        # Team data table
        st.subheader("Team Data")
        team_display = team_filtered[[
            "PLAYER_LAST_TEAM_ABBREVIATION", "SHOT_CLOCK_RANGE",
            "TOTAL_FGA", "TOTAL_FGM", "FG_PCT", "EFG_PCT", "PTS_PER_FGA", "NUM_PLAYERS"
        ]].copy()
        team_display["FG_PCT"] = team_display["FG_PCT"] * 100
        team_display["EFG_PCT"] = team_display["EFG_PCT"] * 100
        team_display = team_display.sort_values(["PLAYER_LAST_TEAM_ABBREVIATION", "SHOT_CLOCK_RANGE"])

        st.dataframe(
            team_display.style.format({
                "FG_PCT": "{:.1f}%",
                "EFG_PCT": "{:.1f}%",
                "PTS_PER_FGA": "{:.2f}",
                "TOTAL_FGA": "{:.0f}",
                "TOTAL_FGM": "{:.0f}",
                "NUM_PLAYERS": "{:.0f}"
            }),
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Download Team Data as CSV",
            data=team_display.to_csv(index=False).encode("utf-8"),
            file_name="team_shotclock_data.csv",
            mime="text/csv"
        )
        
        st.divider()
        
        # Player data table
        st.subheader("Player Data")
        player_display = player_filtered[[
            "PLAYER_NAME", "PLAYER_LAST_TEAM_ABBREVIATION", "SHOT_CLOCK_RANGE",
            "FGA", "FGM", "FG_PCT", "EFG_PCT", "FG3M", "FG3A", "PTS_PER_FGA", "GP"
        ]].copy()
        player_display["FG_PCT"] = player_display["FG_PCT"] * 100
        player_display["EFG_PCT"] = player_display["EFG_PCT"] * 100
        player_display = player_display.sort_values(["PLAYER_NAME", "SHOT_CLOCK_RANGE"])
        
        st.dataframe(
            player_display.style.format({
                "FG_PCT": "{:.1f}%",
                "EFG_PCT": "{:.1f}%",
                "PTS_PER_FGA": "{:.2f}",
                "FGA": "{:.2f}",
                "FGM": "{:.2f}",
                "FG3M": "{:.2f}",
                "FG3A": "{:.2f}",
                "GP": "{:.0f}"
            }),
        use_container_width=True,
            hide_index=True
    )

    st.download_button(
            "Download Player Data as CSV",
            data=player_display.to_csv(index=False).encode("utf-8"),
            file_name="player_shotclock_data.csv",
            mime="text/csv"
    )


if __name__ == "__main__":
    main()
