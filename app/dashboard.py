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
from possval.paths import PROCESSED, REPORTS  # noqa: E402

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


@st.cache_data
def load_report(name: str, index_col: int | None = None) -> pd.DataFrame:
    path = REPORTS / name
    return pd.read_csv(path, index_col=index_col) if path.exists() else pd.DataFrame()


@st.cache_data(show_spinner="Fitting the DPM calibration…")
def load_calibration_panel() -> pd.DataFrame:
    """Team-level DPM-implied vs observed ratings. Empty if the inputs are not present."""
    from possval.models.dpm_calibration import calibration_panel

    try:
        return calibration_panel()
    except (FileNotFoundError, KeyError):
        return pd.DataFrame()


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

# Exposed as a control rather than applied silently: it moves the headline late-clock number
# by 36%, and a filter that large should be something the reader can switch off and see.
keep_heaves = st.checkbox(
    "Include buzzer-beater heaves (shots with under 3s of game clock left)",
    value=False,
    help="A third of shots at 1s or less on the shot clock are end-of-period heaves. They "
         "are near-worthless attempts, not shot-clock decisions, and they sit exactly where "
         "the late-clock findings live.",
)

view = shots[season == shots.SEASON]
if team != "All teams":
    view = view[team == view.TEAM_ABBREVIATION]
if not keep_heaves:
    view = view[view.GAME_CLOCK_EXPIRING == 0]

(tab_curve, tab_stop, tab_valid, tab_rule, tab_grade, tab_late, tab_proj,
 tab_data) = st.tabs(
    ["Efficiency curve", "Shoot or hold", "Validation", "2018-19 rule change",
     "Shot Quality Grade", "Late clock", "2026-27 projection", "Data"]
)

# --------------------------------------------------------------------------- curve

with tab_curve:
    st.subheader("Field-goal points per attempt, by second on the shot clock")
    st.caption(
        "The continuous curve NBA's six published buckets cannot show. Free throws are "
        "excluded — shot detail carries no FT rows. Buzzer-beater heaves are excluded too "
        "unless the box above is ticked; toggling it is the quickest way to see why."
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
        "**Descriptive, not causal.** Possessions surviving to 5 seconds are selected on "
        "everything earlier having failed, so this curve does not identify time pressure as "
        "the cause. Relatedly: **the early-clock advantage is mostly transition.** "
        "At 20s remaining only ~7% of shots come from a half-court inbound start, against "
        "~34% off live-ball turnovers. Restricted to possessions that began after a made "
        "basket, the curve is nearly flat from 12s to 21s.",
        icon="⚠️",
    )

# --------------------------------------------------------------------------- stopping

with tab_stop:
    st.subheader("Shooting as an option, and when teams exercise it")
    st.caption(
        "The efficiency curve is a selected sample at every second — possessions alive at 5 "
        "seconds are the ones where nothing worked earlier. This asks a question that is "
        "answerable instead: at each moment, is the shot on offer worth more than holding?"
    )

    values = load_report("stopping_continuation_value.csv")
    boundary = load_report("stopping_boundary.csv")
    ratios = load_report("stopping_relaxation.csv")
    if values.empty or boundary.empty:
        st.info("No stopping output found. Run `python -m possval.pipeline stopping`.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=values.SECOND, y=values.V_CONT, name="V(t): value of holding",
            mode="lines", line={"color": C[0], "width": 2},
            hovertemplate="%{x}s left · holding worth %{y:.3f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=boundary.SECOND, y=boundary.BOUNDARY,
            name="Marginal accepted shot (5th pct)", mode="lines",
            line={"color": C[1], "width": 2},
            hovertemplate="%{x}s left · accepted down to %{y:.3f}<extra></extra>",
        ))
        fig.update_layout(
            template=TEMPLATE, height=460, hovermode="x unified",
            xaxis={"title": "Seconds remaining on the shot clock", "dtick": 2},
            yaxis={"title": "Expected points"},
            legend={"orientation": "h", "y": 1.1, "x": 0},
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            "**Optimal exercise requires the two lines to converge as the clock expires.** "
            "Holding an option worth nothing should mean accepting almost anything. Instead "
            "the accepted standard falls by only about half as much as the value of waiting "
            "does — offenses stay picky while the option runs out."
        )

        if not ratios.empty:
            a, b = st.columns(2)
            a.metric("Relaxation ratio", f"{ratios.relaxation_ratio.mean():.2f}",
                     help="1.0 would mean the standard falls exactly as fast as V(t). "
                          "Range across quantile choices: "
                          f"{ratios.relaxation_ratio.min():.2f}-"
                          f"{ratios.relaxation_ratio.max():.2f}")
            b.metric("Excess demand late vs early",
                     f"+{ratios.excess_late_demand.mean():.2f} pts",
                     help="How much more a shot must be worth, relative to holding, at 1-3s "
                          "than at 8s or more.")

        checks = load_report("stopping_robustness.csv")
        if not checks.empty:
            st.markdown("##### Does it survive the obvious objections?")
            st.caption(
                "Garbage time and one-season flukes are the two things a reader reaches for. "
                "The ratio holds in competitive games alone and in every one of ten seasons."
            )
            st.dataframe(checks.round(3), use_container_width=True, hide_index=True)

        st.warning(
            "**The level of that orange line is not identified — only its shape.** Calling "
            "the 5th percentile of accepted shots 'the threshold' rather than the 2nd or the "
            "20th moves the gap against V(t) from −0.22 to +0.14, which flips the sign of "
            "'too aggressive' versus 'too patient'. The relaxation ratio is reported because "
            "it comes out at 0.52–0.67 whichever quantile is used. And a declined shot leaves "
            "no record, so none of this can see whether a better shot was actually "
            "available — which is also why the per-player version fails: mean surplus "
            "correlates 0.984 with mean late-clock shot quality, making it that quantity "
            "renamed rather than a measure of judgment.",
            icon="⚠️",
        )

        st.dataframe(
            values.merge(boundary[["SECOND", "BOUNDARY", "GAP"]], on="SECOND", how="left")
            .round(4),
            use_container_width=True, hide_index=True,
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

# --------------------------------------------------------------------------- rule change

with tab_rule:
    st.subheader("A rule change as a natural experiment")
    st.caption(
        "From 2018-19 the clock resets to 14 after an offensive rebound and not after a "
        "defensive one. Treatment is assigned by rule rather than by anyone's choice, so "
        "offensive-rebound chances are treated and defensive-rebound chances are control — "
        "both live-ball rebound starts, sharing the era's pace and officiating drift."
    )

    study = load_report("rulechange_event_study_ran_long.csv")
    estimates = load_report("rulechange_did.csv")
    if study.empty:
        st.info("No rule-change output found. Run `python -m possval.pipeline rulechange`.")
    else:
        fig = go.Figure()
        for i, (column, label) in enumerate(
            [("treated_mean", "Offensive rebound (treated)"),
             ("control_mean", "Defensive rebound (control)")]
        ):
            fig.add_trace(go.Scatter(
                x=study.SEASON, y=study[column] * 100, name=label, mode="lines+markers",
                line={"color": C[i], "width": 2},
                marker={"size": 9, "line": {"width": 2, "color": PAL["surface"]}},
                hovertemplate=f"{label}<br>%{{x}}-%{{x}} · %{{y:.1f}}%<extra></extra>",
            ))
        # The rule lands between 2016-17 and 2018-19; 2017-18 is absent from the series
        # because it is dropped, so the marker sits in the gap it left.
        fig.add_vline(x=2017, line={"color": PAL["muted"], "width": 2, "dash": "dash"})
        fig.add_annotation(
            x=2017, y=28, text="rule effective 2018-19<br>(2017-18 dropped)",
            showarrow=False, font={"size": 11, "color": PAL["text_secondary"]},
            xanchor="left", xshift=6,
        )
        fig.update_layout(
            template=TEMPLATE, height=460,
            xaxis={"title": "Season", "dtick": 1},
            yaxis={"title": "Chances lasting past 14 seconds (%)"},
            legend={"orientation": "h", "y": 1.1, "x": 0},
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            "Long second chances fall **9.1% → 1.4%** the season the rule takes effect and "
            "never come back, against a control that only drifts. The 1.4% that survives is "
            "not error: the reset is `max(remaining, 14)`, so a team rebounding early enough "
            "keeps a clock above 14."
        )
        if not estimates.empty:
            st.dataframe(estimates.round(4), use_container_width=True, hide_index=True)

        st.warning(
            "**2017-18 is excluded, and finding it is half the result.** The NBA changed its "
            "play-by-play timestamping that season: events immediately after a rebound "
            "carrying that rebound's exact game clock step from 14.7% to 18.7% and stay "
            "there. Chance duration here is a game-clock difference, and the change lands "
            "precisely on the events that begin a *treated* chance. That season is also the "
            "only one with the new timestamping and the old 24-second reset — which is why "
            "it showed up as an outlier three separate ways before the cause was found. "
            "Dropping it cut the standard error more than fourfold and turned an apparent "
            "null on efficiency into a small negative effect.",
            icon="⚠️",
        )

        granularity = load_report("rulechange_timestamps.csv", index_col=0)
        if not granularity.empty:
            fig = go.Figure(go.Scatter(
                x=granularity.index, y=granularity.after_rebound_identical_pct,
                mode="lines+markers", line={"color": C[3], "width": 2},
                marker={"size": 9, "line": {"width": 2, "color": PAL["surface"]}},
                hovertemplate="%{x} · %{y:.1f}%<extra></extra>", showlegend=False,
            ))
            fig.add_vline(x=2016.5, line={"color": PAL["muted"], "width": 2, "dash": "dash"})
            fig.update_layout(
                template=TEMPLATE, height=340,
                xaxis={"title": "Season", "dtick": 1},
                yaxis={"title": "Events after a rebound sharing its clock (%)"},
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "The artifact itself. A feed-quality measure, not a basketball one — and the "
                "diagnostic that identified the problem."
            )

# --------------------------------------------------------------------------- projection

with tab_proj:
    st.subheader("Projected 2026-27, all thirty teams")
    st.caption(
        "Rosters valued at current DARKO, calibrated onto the observed rating scale against "
        "2025-26 results, then simulated 20,000 times with conference brackets. Philadelphia "
        "is highlighted; every other roster is frozen at its 2025-26 shape."
    )

    projection = load_report("league_projection_2026_27.csv", index_col=0)
    if projection.empty:
        st.info("No projection found. Run `python -m possval.pipeline project --games 70`.")
    else:
        ordered = projection.sort_values("WINS")
        highlight = ordered.index == "PHI"
        # Two colours only, and they encode one thing: the team in question versus the rest.
        # Ranking is already carried by position, so colouring by rank would be redundant.
        marker_colors = np.where(highlight, C[1], C[0])

        fig = go.Figure()
        for team, row in ordered.iterrows():
            fig.add_trace(go.Scatter(
                x=[row.WINS_P10, row.WINS_P90], y=[team, team],
                mode="lines", showlegend=False, hoverinfo="skip",
                line={"color": C[1] if team == "PHI" else PAL["axis"], "width": 2},
            ))
        fig.add_trace(go.Scatter(
            x=ordered.WINS, y=ordered.index, mode="markers", showlegend=False,
            marker={"color": marker_colors, "size": 11,
                    "line": {"width": 2, "color": PAL["surface"]}},
            customdata=np.column_stack([ordered.RATING, ordered.TITLE * 100]),
            hovertemplate=(
                "<b>%{y}</b><br>%{x:.1f} wins<br>rating %{customdata[0]:+.2f}"
                "<br>title %{customdata[1]:.1f}%<extra></extra>"
            ),
        ))
        fig.add_vline(x=41, line={"color": PAL["grid"], "width": 2, "dash": "dot"})
        fig.update_layout(
            template=TEMPLATE, height=760,
            xaxis={"title": "Projected wins (dot) with 80% interval (line)"},
            yaxis={"title": ""},
        )
        st.plotly_chart(fig, use_container_width=True)

        philadelphia = projection.loc["PHI"]
        rank = int((projection.RATING > philadelphia.RATING).sum()) + 1
        a, b, c, d = st.columns(4)
        a.metric("Rating", f"{philadelphia.RATING:+.2f}")
        b.metric("Wins", f"{philadelphia.WINS:.1f}",
                 help=f"80% interval {philadelphia.WINS_P10:.0f}-{philadelphia.WINS_P90:.0f}")
        c.metric("Title odds", f"{philadelphia.TITLE:.1%}")
        d.metric("League rank", f"{rank} of 30")

        st.markdown(
            "**The superteam is not one.** Philadelphia's 2025-26 base was 18th. LeBron at 41 "
            "plus Jaylen Brown minus Paul George is about +2 DPM of talent, and it displaces "
            "bench minutes rather than replacing bad starters. New York, Oklahoma City and "
            "San Antonio sit roughly six points ahead and take 72% of simulated titles."
        )

        st.markdown("##### The calibration this rests on")
        st.caption(
            "Observed 2025-26 team rating against the one implied by minutes-weighted DPM. "
            "The textbook identity assumes the dotted line; the fitted slope is 1.433, so it "
            "compresses real spread by 43%."
        )

        panel = load_calibration_panel()
        if panel.empty:
            st.info("Calibration panel unavailable.")
        else:
            fit = np.polyfit(panel.PRED, panel.SRS, 1)
            grid = np.linspace(panel.PRED.min(), panel.PRED.max(), 50)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=grid, y=grid, mode="lines", name="Theoretical 1:1",
                line={"color": PAL["axis"], "width": 2, "dash": "dot"},
            ))
            fig.add_trace(go.Scatter(
                x=grid, y=fit[1] + fit[0] * grid, mode="lines", name="Fitted (slope 1.43)",
                line={"color": C[2], "width": 2},
            ))
            fig.add_trace(go.Scatter(
                x=panel.PRED, y=panel.SRS, mode="markers+text", name="Team",
                text=panel.index, textposition="top center",
                textfont={"size": 9, "color": PAL["muted"]},
                marker={"color": np.where(panel.index == "PHI", C[1], C[0]), "size": 9,
                        "line": {"width": 2, "color": PAL["surface"]}},
                hovertemplate=(
                    "<b>%{text}</b><br>implied %{x:+.2f}"
                    "<br>actual %{y:+.2f}<extra></extra>"
                ),
            ))
            fig.update_layout(
                template=TEMPLATE, height=520,
                xaxis={"title": "DPM-implied rating (5 × minutes-weighted DPM)"},
                yaxis={"title": "Observed 2025-26 SRS"},
                legend={"orientation": "h", "y": 1.08, "x": 0},
            )
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            projection.reset_index().rename(columns={"index": "TEAM"}),
            use_container_width=True, hide_index=True,
        )
        st.download_button(
            "Download projection (CSV)",
            projection.reset_index().to_csv(index=False).encode(),
            file_name="league_projection_2026_27.csv",
            mime="text/csv",
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
