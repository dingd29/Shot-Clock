from __future__ import annotations

import math
from typing import Sequence, Union

import pandas as pd
import plotly.express as px
import streamlit as st

from src.data_loader import load_shot_clock_data

PHASE_ORDER: Sequence[str] = ("0-8", "9-16", "17-24")


def order_categories(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["shot_clock_phase"] = pd.Categorical(
        df["shot_clock_phase"], categories=PHASE_ORDER, ordered=True
    )
    return df.sort_values("shot_clock_phase")


GroupKey = Union[str, Sequence[str]]


def summarize(df: pd.DataFrame, group_field: GroupKey) -> pd.DataFrame:
    grouped = df.groupby(group_field, as_index=False).agg(
        possessions=("possessions", "sum"),
        points=("points", "sum"),
        fgm=("fgm", "sum"),
        fga=("fga", "sum"),
        threes_made=("threes_made", "sum"),
        turnovers=("turnovers", "sum"),
        assists=("assists", "sum"),
        free_throw_trips=("free_throw_trips", "sum"),
    )
    grouped["points_per_possession"] = grouped["points"].div(grouped["possessions"])
    grouped["effective_fg_pct"] = (
        grouped["fgm"] + 0.5 * grouped["threes_made"]
    ).div(grouped["fga"])
    grouped["assist_pct"] = grouped["assists"].div(grouped["fgm"])
    grouped["turnover_rate"] = grouped["turnovers"].div(grouped["possessions"])
    grouped["free_throw_rate"] = grouped["free_throw_trips"].div(grouped["possessions"])

    for column in [
        "points_per_possession",
        "effective_fg_pct",
        "assist_pct",
        "turnover_rate",
        "free_throw_rate",
    ]:
        grouped[column] = grouped[column].replace(
            [pd.NA, float("inf"), -float("inf")], pd.NA
        )
    return grouped


def main() -> None:
    st.set_page_config(
        page_title="76ers Shot-Clock Performance",
        page_icon="⏱️",
        layout="wide",
    )
    st.title("Philadelphia 76ers Shot-Clock Performance Dashboard")
    st.caption(
        "Explore how the Sixers perform across shot-clock phases and play types. "
        "Data is season-level and summarized possessions and efficiency metrics."
    )

    raw_df = load_shot_clock_data()
    df = order_categories(raw_df)

    st.sidebar.header("Filters")
    selected_phases = st.sidebar.multiselect(
        "Shot-clock phases", options=list(PHASE_ORDER), default=list(PHASE_ORDER)
    )
    play_types = sorted(df["play_type"].unique())
    selected_play_types = st.sidebar.multiselect(
        "Play types", options=play_types, default=play_types
    )

    filtered_df = df[
        df["shot_clock_phase"].isin(selected_phases)
        & df["play_type"].isin(selected_play_types)
    ]

    if filtered_df.empty:
        st.warning("No data matches your filters. Try widening the selection.")
        return

    totals = filtered_df[
        [
            "possessions",
            "points",
            "fgm",
            "fga",
            "threes_made",
            "turnovers",
            "assists",
            "free_throw_trips",
        ]
    ].sum()
    possessions = totals["possessions"]

    col1, col2, col3, col4 = st.columns(4)
    overall_ppp = totals["points"] / possessions if possessions else math.nan
    overall_efg = (
        (totals["fgm"] + 0.5 * totals["threes_made"]) / totals["fga"]
        if totals["fga"]
        else math.nan
    )
    overall_ast = (
        totals["assists"] / totals["fgm"] if totals["fgm"] else math.nan
    )
    overall_tov = (
        totals["turnovers"] / possessions if possessions else math.nan
    )

    col1.metric(
        "Points per Possession",
        f"{overall_ppp:.3f}" if not math.isnan(overall_ppp) else "N/A",
    )
    col2.metric(
        "Effective FG%",
        f"{overall_efg:.1%}" if not math.isnan(overall_efg) else "N/A",
    )
    col3.metric(
        "Assist % on Makes",
        f"{overall_ast:.1%}" if not math.isnan(overall_ast) else "N/A",
    )
    col4.metric(
        "Turnover Rate",
        f"{overall_tov:.1%}" if not math.isnan(overall_tov) else "N/A",
    )

    st.divider()

    phase_summary = summarize(filtered_df, "shot_clock_phase")
    phase_summary = order_categories(phase_summary)
    phase_chart = px.bar(
        phase_summary,
        x="shot_clock_phase",
        y="points_per_possession",
        hover_data={
            "possessions": True,
            "points": True,
            "effective_fg_pct": ":.1%",
            "assist_pct": ":.1%",
            "turnover_rate": ":.1%",
        },
        text_auto=".2f",
        title="Efficiency by Shot-Clock Phase",
        labels={"shot_clock_phase": "Shot-clock phase", "points_per_possession": "PPP"},
    )
    phase_chart.update_layout(yaxis=dict(tickformat=".2f"), uniformtext_minsize=10)
    play_summary = summarize(filtered_df, "play_type").sort_values(
        "points_per_possession", ascending=False
    )
    play_chart = px.bar(
        play_summary,
        x="points_per_possession",
        y="play_type",
        orientation="h",
        hover_data={
            "possessions": True,
            "points": True,
            "effective_fg_pct": ":.1%",
            "assist_pct": ":.1%",
            "turnover_rate": ":.1%",
        },
        text_auto=".2f",
        title="Play-Type Efficiency within Selection",
        labels={"play_type": "Play type", "points_per_possession": "PPP"},
    )
    play_chart.update_layout(xaxis=dict(tickformat=".2f"), uniformtext_minsize=10)

    charts_col1, charts_col2 = st.columns(2)
    with charts_col1:
        st.plotly_chart(phase_chart, use_container_width=True)
    with charts_col2:
        st.plotly_chart(play_chart, use_container_width=True)

    heatmap_data = summarize(
        filtered_df, ["play_type", "shot_clock_phase"]
    ).pivot(
        index="play_type", columns="shot_clock_phase", values="points_per_possession"
    )
    heatmap_data = heatmap_data.reindex(index=play_types, columns=PHASE_ORDER)
    heatmap_data = heatmap_data.loc[selected_play_types, selected_phases]

    heatmap = px.imshow(
        heatmap_data,
        text_auto=".2f",
        color_continuous_scale="RdBu",
        origin="lower",
        aspect="auto",
        labels=dict(color="PPP"),
        title="PPP Heatmap (Play Type × Shot-Clock Phase)",
    )
    heatmap.update_layout(
        xaxis_title="Shot-clock phase",
        yaxis_title="Play type",
    )
    st.plotly_chart(heatmap, use_container_width=True)

    st.subheader("Detailed Metrics")
    formatted = filtered_df[
        [
            "shot_clock_phase",
            "play_type",
            "possessions",
            "points",
            "points_per_possession",
            "effective_fg_pct",
            "assist_pct",
            "turnover_rate",
            "free_throw_rate",
        ]
    ].sort_values(
        ["shot_clock_phase", "play_type"]
    )

    st.dataframe(
        formatted.style.format(
            {
                "points_per_possession": "{:.3f}",
                "effective_fg_pct": "{:.1%}",
                "assist_pct": "{:.1%}",
                "turnover_rate": "{:.1%}",
                "free_throw_rate": "{:.1%}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download filtered data as CSV",
        data=formatted.to_csv(index=False).encode("utf-8"),
        file_name="76ers_shotclock_filtered.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
