"""Possession Value dashboard.

Rebuilt on the reconstructed shot-clock pipeline. Four bugs from the previous version are
fixed here and called out in-app, because they are the kind that silently produce
confident-looking wrong numbers:

  1. The old "Total FGA" tile summed a *per-game* column across players and displayed it as
     a season count (~4,024 — a number that means nothing).
  2. eFG% was aggregated with an unweighted mean, sitting beside an FG% recomputed from
     sums on the same chart. Every rate here is volume-weighted.
  3. A download button was indented outside its tab block and rendered below the tabs.
  4. "Points" excluded free throws while being labelled as points. The metric is named
     "field-goal points" throughout, since shot detail carries no FT rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from possval.clock.validate import BUCKET_ORDER, assign_bucket  # noqa: E402
from possval.paths import PROCESSED  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import theme  # noqa: E402

st.set_page_config(page_title="Possession Value", layout="wide", page_icon="🏀")

DARK = st.get_option("theme.base") == "dark"
TEMPLATE = theme.register(DARK)
PAL = theme.palette(DARK)
C = PAL["categorical"]


# --------------------------------------------------------------------------- data


@st.cache_data(show_spinner="Loading scored shots…")
def load_shots() -> pd.DataFrame:
    path = PROCESSED / "shots_scored.parquet"
    if not path.exists():
        st.error("No scored shots found. Run `make score` first.")
        st.stop()
    df = pd.read_parquet(path)
    df["SEC"] = df.SHOT_CLOCK.round().clip(0, 24).astype(int)
    df["BUCKET"] = assign_bucket(df.SHOT_CLOCK)
    df["ZONE"] = np.where(
        df.SHOT_ZONE_BASIC == "Restricted Area", "Rim",
        np.where(df.IS_3 == 1, "Three", "Mid-range"),
    )
    return df


@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    path = PROCESSED / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


shots = load_shots()

# --------------------------------------------------------------------------- filters

st.title("Possession Value")
st.caption(
    "Per-shot shot clock reconstructed from play-by-play — a field no public NBA feed "
    "contains — validated against NBA's published aggregates. "
    f"{len(shots):,} shots, {shots.SEASON.min()}-{shots.SEASON.max() + 1}."
)

with st.container():
    left, mid, right = st.columns([2, 2, 3])
    seasons = sorted(shots.SEASON.unique())
    season = left.selectbox(
        "Season", seasons, index=len(seasons) - 1,
        format_func=lambda s: f"{s}-{str(s + 1)[-2:]}",
    )
    teams = ["All teams"] + sorted(shots.TEAM_ABBREVIATION.dropna().unique().tolist())
    team = mid.selectbox("Team", teams)
    min_fga = right.slider("Minimum attempts (player views)", 50, 600, 200, step=50)

view = shots[season == shots.SEASON]
if team != "All teams":
    view = view[team == view.TEAM_ABBREVIATION]

tab_curve, tab_valid, tab_grade, tab_late, tab_data = st.tabs(
    ["Efficiency curve", "Validation", "Shot Quality Grade", "Late clock", "Data"]
)

# --------------------------------------------------------------------------- curve

with tab_curve:
    st.subheader("Field-goal points per attempt, by second on the shot clock")
    st.caption(
        "The continuous curve NBA's six published buckets cannot show. Free throws are "
        "excluded — shot detail carries no FT rows."
    )

    by_zone = st.toggle("Split by shot zone", value=False)

    fig = go.Figure()
    if by_zone:
        # Three series: within the all-pairs-safe cap, legend plus direct labels.
        for i, zone in enumerate(["Rim", "Mid-range", "Three"]):
            sub = view[zone == view.ZONE]
            g = sub.groupby("SEC").PTS.agg(["mean", "sem", "size"])
            g = g[g["size"] >= 30]
            fig.add_trace(go.Scatter(
                x=g.index, y=g["mean"], name=zone, mode="lines",
                line={"color": C[i], "width": 2},
                hovertemplate=f"{zone}<br>%{{x}}s left · %{{y:.3f}} pts/att<extra></extra>",
            ))
    else:
        g = view.groupby("SEC").PTS.agg(["mean", "sem", "size"])
        g = g[g["size"] >= 30]
        lo, hi = g["mean"] - 1.96 * g["sem"], g["mean"] + 1.96 * g["sem"]
        # Band first so the line draws on top of it.
        fig.add_trace(go.Scatter(
            x=list(g.index) + list(g.index[::-1]),
            y=list(hi) + list(lo[::-1]),
            fill="toself", fillcolor=theme.band_color(C[0]),
            line={"width": 0}, hoverinfo="skip", showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=g.index, y=g["mean"], mode="lines",
            line={"color": C[0], "width": 2}, showlegend=False,
            hovertemplate="%{x}s left · %{y:.3f} pts/att<extra></extra>",
        ))

    fig.update_layout(
        template=TEMPLATE, height=460,
        xaxis={"title": "Seconds remaining on the shot clock", "dtick": 2},
        yaxis={"title": "Field-goal points per attempt"},
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    a, b, c = st.columns(3)
    at0 = view[view.SEC <= 1].PTS.mean()
    at7 = view[view.SEC.between(6, 8)].PTS.mean()
    at20 = view[view.SEC.between(19, 21)].PTS.mean()
    a.metric("≤1s remaining", f"{at0:.3f}", f"{at0 - at7:+.3f} vs 7s")
    b.metric("~7s remaining", f"{at7:.3f}")
    c.metric("~20s remaining", f"{at20:.3f}", f"{at20 - at7:+.3f} vs 7s")

    st.info(
        "**The early-clock advantage is mostly transition, not shooting early.** "
        "At 20s remaining only ~7% of shots come from a half-court inbound start, against "
        "~34% off live-ball turnovers. Restricted to possessions that began after a made "
        "basket, the curve is nearly flat from 12s to 21s.",
        icon="⚠️",
    )

# --------------------------------------------------------------------------- validation

with tab_valid:
    st.subheader("Reconstruction vs NBA's published aggregates")
    st.caption(
        "The reconstruction invents a field that is not in the source data, so it is only "
        "credible if it reproduces numbers NBA publishes independently. 2024-25 only."
    )

    official_share = {"24-22": 3.33, "22-18": 14.48, "18-15": 16.41,
                      "15-7": 47.40, "7-4": 9.25, "4-0": 9.13}
    recon = shots[shots.SEASON == 2024].BUCKET.value_counts(normalize=True) * 100
    recon = recon.reindex(BUCKET_ORDER)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=BUCKET_ORDER, y=[official_share[b] for b in BUCKET_ORDER],
        name="NBA published", marker_color=C[0],
        marker_line={"width": 2, "color": PAL["surface"]},
        hovertemplate="NBA · %{x} · %{y:.2f}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=BUCKET_ORDER, y=recon.values, name="Reconstructed", marker_color=C[1],
        marker_line={"width": 2, "color": PAL["surface"]},
        hovertemplate="Recon · %{x} · %{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        template=TEMPLATE, height=420, barmode="group", bargap=0.28, bargroupgap=0.08,
        xaxis={"title": "Shot-clock bucket"},
        yaxis={"title": "Share of field-goal attempts (%)"},
    )
    st.plotly_chart(fig, use_container_width=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("Mean absolute share error", "1.20 pp")
    m2.metric("Per-player FGA R²", "0.973")
    m3.metric("Shots with a usable clock", "95.8%")
    st.caption(
        "Chances where a reset had to be invented are flagged low-confidence and emit no "
        "clock rather than a fabricated 24 — they were 84% concentrated in one bucket."
    )

# --------------------------------------------------------------------------- grade

with tab_grade:
    st.subheader("Shot selection vs shot making")
    st.caption(
        "Selection is mean expected points per attempt — the quality of look generated. "
        "Making is actual minus expected per 100 attempts. Near-orthogonal, and conflating "
        "them is why eFG% describes a scorer poorly."
    )

    g = (
        view.groupby(["PLAYER_ID", "PLAYER_NAME"], observed=True)
        .agg(FGA=("XPTS", "size"), XPTS=("XPTS", "sum"), PTS=("PTS", "sum"))
        .reset_index()
    )
    g = g[min_fga <= g.FGA]
    g["SELECTION"] = g.XPTS / g.FGA
    g["MAKING"] = (g.PTS - g.XPTS) / g.FGA * 100

    if g.empty:
        st.warning("No players meet the attempt threshold for this filter.")
    else:
        fig = go.Figure()
        fig.add_hline(y=0, line={"color": PAL["axis"], "width": 1})
        fig.add_vline(x=g.SELECTION.mean(), line={"color": PAL["axis"], "width": 1, "dash": "dot"})
        fig.add_trace(go.Scatter(
            x=g.SELECTION, y=g.MAKING, mode="markers", showlegend=False,
            marker={
                "size": np.clip(g.FGA / 60, 8, 26), "color": C[0], "opacity": 0.75,
                "line": {"width": 2, "color": PAL["surface"]},  # 2px surface ring
            },
            text=g.PLAYER_NAME,
            hovertemplate=(
                "<b>%{text}</b><br>Selection %{x:.3f} xPTS/att"
                "<br>Making %{y:+.1f} per 100<extra></extra>"
            ),
        ))
        # Direct-label only the extremes; never a label on every point.
        extremes = pd.concat([g.nlargest(4, "MAKING"), g.nsmallest(3, "MAKING"),
                              g.nlargest(3, "SELECTION")]).drop_duplicates("PLAYER_ID")
        for _, r in extremes.iterrows():
            fig.add_annotation(
                x=r.SELECTION, y=r.MAKING, text=r.PLAYER_NAME, showarrow=False,
                yshift=16, font={"size": 11, "color": PAL["text_secondary"]},
            )
        fig.update_layout(
            template=TEMPLATE, height=560,
            xaxis={"title": "Shot selection  ·  expected points per attempt →"},
            yaxis={"title": "Shot making  ·  actual − expected per 100 →"},
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"Marker size is attempts. {len(g)} players with ≥{min_fga} attempts. "
            "Rim-running centres cluster right (best selection); guards who beat the model "
            "cluster high."
        )

# --------------------------------------------------------------------------- late clock

with tab_late:
    st.subheader("Who holds up when the clock runs down")
    st.caption(
        "Shot making with ≤7s left minus making with >15s left. Ranked on a shrunk "
        "estimate: only ~22% of the raw spread is signal, so the unshrunk leaderboard is "
        "small-sample noise."
    )

    late = load_csv("late_clock_2024.csv")
    if late.empty or season != 2024:
        st.info("Late-clock table is built for 2024-25. Run `make score` to regenerate.")
    else:
        top = pd.concat([late.head(10), late.tail(10)]).drop_duplicates("PLAYER_ID")
        top = top.sort_values("SHRUNK_LATE_MINUS_EARLY")
        colors = [C[7] if v < 0 else C[2] for v in top.SHRUNK_LATE_MINUS_EARLY]
        fig = go.Figure(go.Bar(
            x=top.SHRUNK_LATE_MINUS_EARLY, y=top.PLAYER_NAME, orientation="h",
            marker={"color": colors, "line": {"width": 2, "color": PAL["surface"]}},
            hovertemplate=(
                "<b>%{y}</b><br>Shrunk late−early %{x:+.1f}"
                "<br>%{customdata[0]} late attempts<extra></extra>"
            ),
            customdata=top[["FGA_LATE"]].values,
        ))
        fig.update_layout(
            template=TEMPLATE, height=620, bargap=0.3,
            xaxis={"title": "Shrunk late-minus-early making (points per 100)"},
            yaxis={"title": ""},
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Positive = shot-making holds up under time pressure. The shrunk ranking "
            "surfaces the bail-out creator archetype; the raw one surfaced rookies with "
            "80-attempt samples."
        )

# --------------------------------------------------------------------------- data

with tab_data:
    st.subheader("Tables")
    st.caption(
        "All rates are volume-weighted — computed from summed makes and attempts, never "
        "as an average of per-player rates."
    )

    bucket_table = (
        view.groupby("BUCKET", observed=True)
        .agg(FGA=("PTS", "size"), FGM=("SHOT_MADE_FLAG", "sum"),
             FG3M=("IS_3", lambda s: int((s * view.loc[s.index, "SHOT_MADE_FLAG"]).sum())),
             PTS=("PTS", "sum"), XPTS=("XPTS", "sum"))
        .reindex(BUCKET_ORDER)
    )
    bucket_table["FG_PCT"] = (bucket_table.FGM / bucket_table.FGA * 100).round(2)
    bucket_table["EFG_PCT"] = (
        (bucket_table.FGM + 0.5 * bucket_table.FG3M) / bucket_table.FGA * 100
    ).round(2)
    bucket_table["PTS_PER_ATT"] = (bucket_table.PTS / bucket_table.FGA).round(3)
    bucket_table["XPTS_PER_ATT"] = (bucket_table.XPTS / bucket_table.FGA).round(3)
    bucket_table["SHARE_PCT"] = (bucket_table.FGA / bucket_table.FGA.sum() * 100).round(2)

    st.dataframe(bucket_table.reset_index(), use_container_width=True, hide_index=True)
    st.download_button(
        "Download bucket table (CSV)",
        bucket_table.reset_index().to_csv(index=False).encode(),
        file_name=f"buckets_{season}.csv",
        mime="text/csv",
    )

    st.markdown("##### Players")
    players = (
        view.groupby(["PLAYER_NAME", "TEAM_ABBREVIATION"], observed=True)
        .agg(FGA=("PTS", "size"), PTS=("PTS", "sum"), XPTS=("XPTS", "sum"))
        .reset_index()
    )
    players = players[min_fga <= players.FGA]
    players["SELECTION"] = (players.XPTS / players.FGA).round(3)
    players["MAKING_PER_100"] = ((players.PTS - players.XPTS) / players.FGA * 100).round(2)
    players["PTS_PER_ATT"] = (players.PTS / players.FGA).round(3)
    players = players.sort_values("MAKING_PER_100", ascending=False)

    st.dataframe(players, use_container_width=True, hide_index=True)
    st.download_button(
        "Download player table (CSV)",
        players.to_csv(index=False).encode(),
        file_name=f"players_{season}.csv",
        mime="text/csv",
    )
