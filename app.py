from __future__ import annotations

import math
from typing import Sequence, Union

import pandas as pd
import plotly.express as px
import streamlit as st

from src.data_loader import load_shot_clock_data
from src.nba_stats import GENERAL_RANGES, SHOT_CLOCK_RANGES, safe_div

SHOT_CLOCK_ORDER: Sequence[str] = tuple(SHOT_CLOCK_RANGES)
GENERAL_RANGE_ORDER: Sequence[str] = tuple(GENERAL_RANGES)


def order_categories(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "shot_clock_range" in df.columns:
        df["shot_clock_range"] = pd.Categorical(
            df["shot_clock_range"], categories=SHOT_CLOCK_ORDER, ordered=True
        )
    if "general_range" in df.columns:
        df["general_range"] = pd.Categorical(
            df["general_range"], categories=GENERAL_RANGE_ORDER, ordered=True
        )
    sort_columns = [
        column
        for column in ("shot_clock_range", "general_range")
        if column in df.columns
    ]
    if sort_columns:
        df = df.sort_values(sort_columns)
    return df


GroupKey = Union[str, Sequence[str]]


def ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else math.nan


def summarize(df: pd.DataFrame, group_field: GroupKey) -> pd.DataFrame:
    grouped = df.groupby(group_field, as_index=False).agg(
        fgm=("fgm", "sum"),
        fga=("fga", "sum"),
        fg3m=("fg3m", "sum"),
        fg3a=("fg3a", "sum"),
        points=("points", "sum"),
    )
    grouped["fg_pct"] = safe_div(grouped["fgm"], grouped["fga"])
    grouped["efg_pct"] = safe_div(grouped["fgm"] + 0.5 * grouped["fg3m"], grouped["fga"])
    grouped["fg3_pct"] = safe_div(grouped["fg3m"], grouped["fg3a"])
    grouped["fg3_rate"] = safe_div(grouped["fg3a"], grouped["fga"])
    grouped["points_per_shot"] = safe_div(grouped["points"], grouped["fga"])
    grouped["fga_share"] = safe_div(grouped["fga"], pd.Series(df["fga"].sum(), index=grouped.index))
    return grouped


def main() -> None:
    st.set_page_config(
        page_title="76ers Shot-Clock Performance",
        page_icon="⏱️",
        layout="wide",
    )
    st.title("Philadelphia 76ers Shot-Clock Performance Dashboard")
    st.caption(
        "Explore how the Sixers perform across shot-clock ranges and NBA.com shooting categories. "
        "Data is sourced live from stats.nba.com."
    )

    try:
        raw_df = load_shot_clock_data()
    except RuntimeError as exc:
        st.error(
            "Could not download shot-clock data from stats.nba.com. "
            "If you're running this locally, ensure that requests to https://stats.nba.com/ are allowed."
        )
        st.caption(str(exc))
        st.stop()

    df = order_categories(raw_df)

    st.sidebar.header("Filters")
    selected_phases = st.sidebar.multiselect(
        "Shot-clock ranges",
        options=list(SHOT_CLOCK_ORDER),
        default=list(SHOT_CLOCK_ORDER),
    )
    selected_categories = st.sidebar.multiselect(
        "Shooting categories",
        options=list(GENERAL_RANGE_ORDER),
        default=list(GENERAL_RANGE_ORDER),
    )

    filtered_df = df[
        df["shot_clock_range"].isin(selected_phases)
        & df["general_range"].isin(selected_categories)
    ]

    if filtered_df.empty:
        st.warning("No data matches your filters. Try widening the selection.")
        return

    totals = filtered_df[["fgm", "fga", "fg3m", "fg3a", "points"]].sum()
    total_fga = totals["fga"]

    col1, col2, col3, col4 = st.columns(4)
    overall_efg = ratio(totals["fgm"] + 0.5 * totals["fg3m"], total_fga)
    overall_fg_pct = ratio(totals["fgm"], total_fga)
    overall_fg3_pct = ratio(totals["fg3m"], totals["fg3a"])
    overall_points_per_shot = ratio(totals["points"], total_fga)

    col1.metric(
        "Effective FG%",
        f"{overall_efg:.1%}" if not math.isnan(overall_efg) else "N/A",
    )
    col2.metric(
        "Field Goal%",
        f"{overall_fg_pct:.1%}" if not math.isnan(overall_fg_pct) else "N/A",
    )
    col3.metric(
        "3P%",
        f"{overall_fg3_pct:.1%}" if not math.isnan(overall_fg3_pct) else "N/A",
    )
    col4.metric(
        "Points per Shot",
        f"{overall_points_per_shot:.3f}"
        if not math.isnan(overall_points_per_shot)
        else "N/A",
    )

    st.divider()

    phase_summary = summarize(filtered_df, "shot_clock_range")
    phase_summary = order_categories(phase_summary)
    phase_chart = px.bar(
        phase_summary,
        x="shot_clock_range",
        y="points_per_shot",
        hover_data={
            "fgm": True,
            "fga": True,
            "fg_pct": ":.1%",
            "efg_pct": ":.1%",
            "fg3_pct": ":.1%",
        },
        text_auto=".2f",
        title="Points per Shot by Shot-Clock Range",
        labels={
            "shot_clock_range": "Shot-clock range",
            "points_per_shot": "Points per Shot",
        },
    )
    phase_chart.update_layout(yaxis=dict(tickformat=".2f"), uniformtext_minsize=10)
    range_summary = summarize(filtered_df, "general_range")
    range_summary = order_categories(range_summary)
    range_chart = px.bar(
        range_summary,
        x="points_per_shot",
        y="general_range",
        orientation="h",
        hover_data={
            "fgm": True,
            "fga": True,
            "fg_pct": ":.1%",
            "efg_pct": ":.1%",
            "fg3_pct": ":.1%",
        },
        text_auto=".2f",
        title="Points per Shot by Shooting Category",
        labels={"general_range": "Category", "points_per_shot": "Points per Shot"},
    )
    range_chart.update_layout(xaxis=dict(tickformat=".2f"), uniformtext_minsize=10)

    charts_col1, charts_col2 = st.columns(2)
    with charts_col1:
        st.plotly_chart(phase_chart, use_container_width=True)
    with charts_col2:
        st.plotly_chart(range_chart, use_container_width=True)

    heatmap_source = summarize(filtered_df, ["general_range", "shot_clock_range"])
    heatmap_source = order_categories(heatmap_source)
    heatmap_data = heatmap_source.pivot(
        index="general_range",
        columns="shot_clock_range",
        values="points_per_shot",
    )
    heatmap_data = heatmap_data.reindex(index=selected_categories, columns=selected_phases)

    heatmap = px.imshow(
        heatmap_data,
        text_auto=".2f",
        color_continuous_scale="RdBu",
        origin="lower",
        aspect="auto",
        labels=dict(color="Points per Shot"),
        title="Points per Shot Heatmap (Category × Shot-Clock Range)",
    )
    heatmap.update_layout(
        xaxis_title="Shot-clock range",
        yaxis_title="Shooting category",
    )
    st.plotly_chart(heatmap, use_container_width=True)

    st.subheader("Detailed Metrics")
    total_fga = filtered_df["fga"].sum()
    if total_fga:
        fga_share = filtered_df["fga"] / total_fga
    else:
        fga_share = pd.Series(0.0, index=filtered_df.index)
    detailed = filtered_df.assign(fga_share=fga_share)
    detailed = order_categories(detailed)
    display_columns = [
        "shot_clock_range",
        "general_range",
        "fgm",
        "fga",
        "fg_pct",
        "efg_pct",
        "fg3_pct",
        "fg3_rate",
        "points_per_shot",
        "fga_share",
    ]
    rename_map = {
        "shot_clock_range": "Shot-clock range",
        "general_range": "Category",
        "fgm": "FGM",
        "fga": "FGA",
        "fg_pct": "FG%",
        "efg_pct": "EFG%",
        "fg3_pct": "3P%",
        "fg3_rate": "3PA Rate",
        "points_per_shot": "Points per Shot",
        "fga_share": "FGA Share",
    }
    st.dataframe(
        detailed[display_columns]
        .rename(columns=rename_map)
        .style.format(
            {
                "FG%": "{:.1%}",
                "EFG%": "{:.1%}",
                "3P%": "{:.1%}",
                "3PA Rate": "{:.1%}",
                "Points per Shot": "{:.3f}",
                "FGA Share": "{:.1%}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download filtered data as CSV",
        data=detailed[display_columns].to_csv(index=False).encode("utf-8"),
        file_name="76ers_shotclock_filtered.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
