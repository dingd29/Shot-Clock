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


def _winprob_label(comparison: pd.DataFrame) -> str:
    """How much the shot-clock block moved a live win-probability model, as a percentage."""
    if comparison.empty:
        return "negligible — run `make winprob`"
    worst, best = comparison.log_loss.max(), comparison.log_loss.min()
    return f"negligible — {100 * (worst - best) / worst:.3f}% of log loss"


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

(tab_curve, tab_stop, tab_teams, tab_valid, tab_rule, tab_grade, tab_late,
 tab_proj, tab_data) = st.tabs(
    ["Efficiency curve", "Decision Atlas", "Team profiles", "Validation",
     "2018-19 rule change", "Shot Quality Grade", "Late clock",
     "2026-27 projection", "Data"]
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
    st.subheader("Decision Atlas · Chapter 1: shoot or hold")
    st.caption(
        "The first chapter in an atlas of choices hidden inside possessions. The efficiency "
        "curve is a selected sample at every second — possessions alive at 5 "
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

        st.markdown("##### What the shot clock is worth, by scale")
        st.caption(
            "The project's own answer to the question it was built to ask, and not the one "
            "it set out to find. A possession is ~1% of a game's scoring, so possession-scale "
            "information washes out at the scale below it and the scale above."
        )
        winprob = load_report("winprob_comparison.csv")
        scales = pd.DataFrame(
            {
                "question": [
                    "Will this shot go in?",
                    "Will this possession score?",
                    "Will this team win?",
                ],
                "shot clock contribution": [
                    "negligible — 0.00136 log loss, smallest ablation group",
                    "large — V(t) spans 0.36 to 0.81, a 2.2x range",
                    _winprob_label(winprob),
                ],
            }
        )
        st.dataframe(scales, use_container_width=True, hide_index=True)
        st.info(
            "**The reconstruction's value is as a measurement instrument, not a predictive "
            "feature.** The shoot-or-hold result above exists only because a continuation "
            "value can be computed at all, and it cannot be computed without a shot clock.",
            icon="🔭",
        )

        st.divider()
        st.markdown("### Chapter 2: hand over now, or create a second trip?")
        st.caption(
            "At the end of a period, finishing earlier hands the ball to the opponent earlier. "
            "The familiar 2-for-1 idea assumes there are large good and bad handover moments. "
            "The question is how much value is actually there to exploit."
        )
        ball_explore = load_report("endgame_ball_value_explore.csv")
        ball_holdout = load_report("endgame_ball_value_holdout.csv")
        timing_explore = load_report("twoforone_profile_explore.csv")
        timing_holdout = load_report("twoforone_profile_holdout.csv")
        if ball_explore.empty or ball_holdout.empty or timing_explore.empty:
            st.info("No endgame atlas output found. Run `make endgame` and `make twoforone`.")
        else:
            left, right = st.columns(2)
            with left:
                fig = go.Figure()
                for frame, name, color in (
                    (ball_explore, "2015–22", C[0]),
                    (ball_holdout, "2022–24", C[1]),
                ):
                    fig.add_trace(go.Scatter(
                        x=frame.S, y=frame.V_BALL, name=name, mode="lines+markers",
                        line={"color": color, "width": 2}, marker={"size": 5},
                        hovertemplate=(
                            f"{name}<br>%{{x:.0f}}s left · %{{y:.3f}} net points"
                            "<extra></extra>"
                        ),
                    ))
                fig.update_layout(
                    template=TEMPLATE, height=410,
                    xaxis_title="Game seconds left in the period",
                    yaxis_title="Value of holding the ball (net points to buzzer)",
                    legend={"orientation": "h", "y": 1.1, "x": 0},
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    "The wobbles are real but tiny: the structure beyond a smooth trend is "
                    "0.041 points on exploration and 0.035 held out, not the 0.49-point "
                    "sawtooth a clean alternating-possession model predicts."
                )
            with right:
                fig = go.Figure()
                for frame, name, color in (
                    (timing_explore, "2015–22", C[0]),
                    (timing_holdout, "2022–24", C[1]),
                ):
                    fig.add_trace(go.Scatter(
                        x=frame.GC_BIN, y=frame.CLOCK_USED, name=name, mode="lines+markers",
                        line={"color": color, "width": 2}, marker={"size": 5},
                        hovertemplate=(
                            f"{name}<br>Ball gained at %{{x:.0f}}s · "
                            "%{y:.1f}s used<extra></extra>"
                        ),
                    ))
                fig.add_vline(x=32, line={"color": PAL["muted"], "dash": "dash"})
                fig.add_annotation(
                    x=32, y=15.2, text="second trip becomes feasible", showarrow=False,
                    yshift=12, font={"size": 11, "color": PAL["text_secondary"]},
                )
                fig.update_layout(
                    template=TEMPLATE, height=410,
                    xaxis_title="Game seconds left when possession begins",
                    yaxis_title="Seconds used before shooting",
                    legend={"orientation": "h", "y": 1.1, "x": 0},
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    "Teams clearly speed up where a second trip becomes available—the timing "
                    "effect reproduces to a tenth of a second. The measured payoff is near zero "
                    "because the option they are buying is almost free, not because it is large."
                )

# --------------------------------------------------------------------------- team profiles

with tab_teams:
    st.subheader("Team possession profiles")
    st.caption(
        "Three questions that look alike and are not: when a team shoots is style; what its "
        "continuation curve is worth is capability; how often it shoots below its own curve "
        "is deviation. Only the last is even a candidate measure of decision quality."
    )

    premature_frames, timing_frames, curve_frames = [], [], []
    diagnostic_frames, band_frames, player_frames = [], [], []
    for window in ("explore", "holdout"):
        premature = load_report(f"value_premature_{window}.csv")
        timing = load_report(f"value_team_timing_{window}.csv")
        curves = load_report(f"value_team_curves_{window}.csv")
        diagnostics = load_report(f"value_team_diagnostics_{window}.csv")
        bands = load_report(f"value_team_clock_bands_{window}.csv")
        players = load_report(f"value_player_diagnostics_{window}.csv")
        if not premature.empty:
            premature_frames.append(premature.assign(WINDOW=window))
        if not timing.empty:
            timing_frames.append(timing.assign(WINDOW=window))
        if not curves.empty:
            curve_frames.append(curves.assign(WINDOW=window))
        if not diagnostics.empty:
            diagnostic_frames.append(diagnostics.assign(WINDOW=window))
        if not bands.empty:
            band_frames.append(bands.assign(WINDOW=window))
        if not players.empty:
            player_frames.append(players.assign(WINDOW=window))

    if (
        not premature_frames or not timing_frames or not curve_frames
        or not diagnostic_frames or not band_frames or not player_frames
    ):
        st.info("No team-profile output found. Run `make value` for both windows.")
    else:
        premature = pd.concat(premature_frames, ignore_index=True)
        timing = pd.concat(timing_frames, ignore_index=True)
        profile = premature.merge(
            timing.drop(columns="N_SHOTS"), on=["TEAM_ABBREVIATION", "WINDOW"],
            how="left",
        )
        available = sorted(profile.TEAM_ABBREVIATION.unique())
        initial = team if team in available else "PHI"
        profile_team = st.selectbox(
            "Profile team", available, index=available.index(initial), key="profile_team"
        )
        selected = profile[profile.TEAM_ABBREVIATION == profile_team].set_index("WINDOW")
        diagnostics = pd.concat(diagnostic_frames, ignore_index=True)
        holdout_diagnostics = diagnostics[diagnostics.WINDOW == "holdout"].copy()
        selected_diagnostic = holdout_diagnostics[
            holdout_diagnostics.TEAM_ABBREVIATION == profile_team
        ].iloc[0]

        a, b, c, d = st.columns(4)
        a.metric(
            "Offensive efficiency",
            f"{selected_diagnostic.PPP:.3f}",
            f"rank {int(selected_diagnostic.OFFENSE_RANK)} of 30",
        )
        b.metric(
            "Below own curve",
            f"{selected_diagnostic.PREMATURE:.1%}",
            f"rank {int(selected_diagnostic.PREMATURE_RANK)} high",
        )
        c.metric(
            "Positive gap / shot",
            f"{selected_diagnostic.EXPOSURE_PER_SHOT:.3f}",
            f"rank {int(selected_diagnostic.EXPOSURE_RANK)} high",
            help=(
                "Mean positive difference between continuation value and taken-shot value, "
                "counting zero for shots above the curve. Descriptive opportunity exposure, "
                "not recoverable points."
            ),
        )
        d.metric("Mean shot clock", f"{selected_diagnostic.MEAN_SECOND:.1f}s")

        if bool(selected_diagnostic.REVIEW_FLAG):
            st.warning(
                f"**Review candidate, not a verdict.** {profile_team} combines a bottom-third "
                "offense with top-third below-curve exposure. That makes its possessions worth "
                "film and lineup review; it does not establish that waiting would have caused "
                "better shots.",
                icon="🔎",
            )
        else:
            st.info(
                "The profile is a conjunction, not a grade. High exposure on a strong offense "
                "can be the shadow of high continuation capability; low exposure on a weak "
                "offense does not prove that team is shooting at the right time."
            )

        st.markdown("##### Where poor offense and unrealised continuation overlap")
        colors = np.where(
            holdout_diagnostics.TEAM_ABBREVIATION == profile_team,
            C[1],
            np.where(holdout_diagnostics.REVIEW_FLAG, C[2], C[0]),
        )
        fig = go.Figure(go.Scatter(
            x=holdout_diagnostics.PPP,
            y=holdout_diagnostics.EXPOSURE_PER_SHOT,
            mode="markers+text",
            text=holdout_diagnostics.TEAM_ABBREVIATION,
            textposition="top center",
            marker={"color": colors, "size": 10},
            customdata=holdout_diagnostics[["OFFENSE_RANK", "EXPOSURE_RANK"]].to_numpy(),
            hovertemplate=(
                "%{text}<br>%{x:.3f} pts/possession (rank %{customdata[0]})"
                "<br>%{y:.4f} positive gap/shot (rank %{customdata[1]})<extra></extra>"
            ),
        ))
        fig.add_vline(
            x=holdout_diagnostics.PPP.quantile(1 / 3),
            line={"color": PAL["muted"], "dash": "dot"},
        )
        fig.add_hline(
            y=holdout_diagnostics.EXPOSURE_PER_SHOT.quantile(2 / 3),
            line={"color": PAL["muted"], "dash": "dot"},
        )
        fig.update_layout(
            template=TEMPLATE, height=500,
            xaxis_title="Offensive points per possession →",
            yaxis_title="Below-curve exposure per shot →",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Orange teams are the review queue: bottom-third offense and top-third exposure. "
            "The overall relationship slopes the other way—strong offenses often have higher "
            "exposure because their continuation option is more valuable."
        )

        holdout = profile[profile.WINDOW == "holdout"].sort_values("PREMATURE")
        colors = np.where(holdout.TEAM_ABBREVIATION == profile_team, C[1], C[0])
        fig = go.Figure(go.Bar(
            x=holdout.PREMATURE * 100,
            y=holdout.TEAM_ABBREVIATION,
            orientation="h",
            marker_color=colors,
            customdata=holdout[["SE"]].to_numpy(),
            hovertemplate="%{y} · %{x:.1f}% premature<extra></extra>",
        ))
        fig.update_layout(
            template=TEMPLATE, height=720,
            xaxis_title="Shots below the team's own continuation value (%)",
            yaxis_title=None, showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("##### Capability: what this team can still create by waiting")
        team_curves = pd.concat(curve_frames, ignore_index=True)
        selected_curves = team_curves[team_curves.TEAM == profile_team]
        fig = go.Figure()
        for window, label, color in (
            ("explore", "2015–22", C[0]),
            ("holdout", "2022–24", C[1]),
        ):
            row = selected_curves[selected_curves.WINDOW == window]
            if row.empty:
                continue
            values = row.iloc[0][[f"V{second}" for second in range(25)]].to_numpy(dtype=float)
            fig.add_trace(go.Scatter(
                x=np.arange(25), y=values, name=label, mode="lines+markers",
                line={"color": color, "width": 2}, marker={"size": 4},
                hovertemplate=(
                    f"{label}<br>%{{x}}s left · waiting worth %{{y:.3f}} pts"
                    "<extra></extra>"
                ),
            ))
        fig.update_layout(
            template=TEMPLATE, height=420,
            xaxis_title="Seconds remaining on the shot clock",
            yaxis_title="Expected points from continuing",
            legend={"orientation": "h", "y": 1.1, "x": 0},
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "This is capability, not a grade: a high line means the team historically had more "
            "to gain by declining a shot and continuing the possession. League scoring levels "
            "shift across eras, so compare the curve's shape more readily than its vertical level."
        )

        st.markdown("##### When on the clock does the exposure appear?")
        band_table = pd.concat(band_frames, ignore_index=True)
        selected_bands = band_table[
            (band_table.WINDOW == "holdout")
            & (band_table.TEAM_ABBREVIATION == profile_team)
        ].copy()
        selected_bands["CLOCK_PHASE"] = pd.Categorical(
            selected_bands.CLOCK_PHASE,
            ["early (16–23)", "middle (8–15)", "late (0–7)"],
            ordered=True,
        )
        selected_bands = selected_bands.sort_values("CLOCK_PHASE")
        fig = go.Figure(go.Bar(
            x=selected_bands.CLOCK_PHASE,
            y=selected_bands.EXPOSURE_PER_SHOT,
            marker_color=[C[0], C[1], C[2]],
            customdata=selected_bands[["PREMATURE", "N_SHOTS"]].to_numpy(),
            hovertemplate=(
                "%{x}<br>%{y:.4f} positive gap/shot"
                "<br>%{customdata[0]:.1%} below curve · %{customdata[1]:,.0f} shots"
                "<extra></extra>"
            ),
        ))
        fig.update_layout(
            template=TEMPLATE, height=360,
            xaxis_title="Shot-clock phase", yaxis_title="Below-curve exposure per shot",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Early and middle-clock exposure is the plausible patience signal: the offense had "
            "time to continue. Late exposure is often burden—someone had to end the possession."
        )

        context_summary = load_report("value_team_context_summary_holdout.csv")
        context_details = load_report("value_team_context_details_holdout.csv")
        if not context_summary.empty and not context_details.empty:
            st.markdown("##### What kind of shots create the signal?")
            context_row = context_summary[
                context_summary.TEAM_ABBREVIATION == profile_team
            ].iloc[0]
            family = (
                context_details[context_details.TEAM_ABBREVIATION == profile_team]
                .groupby("SHOT_FAMILY")
                .agg(N_SHOTS=("N_SHOTS", "sum"), TOTAL_EXPOSURE=("TOTAL_EXPOSURE", "sum"))
                .reset_index()
            )
            family["SHOT_SHARE"] = family.N_SHOTS / family.N_SHOTS.sum()
            family["EXPOSURE_SHARE"] = family.TOTAL_EXPOSURE / family.TOTAL_EXPOSURE.sum()
            family = family.sort_values("EXPOSURE_SHARE", ascending=False)
            left, right = st.columns([2, 1])
            with left:
                fig = go.Figure()
                for column, label, color in (
                    ("SHOT_SHARE", "Share of attempts", C[0]),
                    ("EXPOSURE_SHARE", "Share of exposure", C[1]),
                ):
                    fig.add_trace(go.Bar(
                        x=family.SHOT_FAMILY,
                        y=family[column] * 100,
                        name=label,
                        marker_color=color,
                        hovertemplate=f"%{{x}}<br>{label}: %{{y:.1f}}%<extra></extra>",
                    ))
                fig.update_layout(
                    template=TEMPLATE, height=380, barmode="group",
                    xaxis_title="Shot family", yaxis_title="Share (%)",
                    legend={"orientation": "h", "y": 1.12, "x": 0},
                )
                st.plotly_chart(fig, use_container_width=True)
            with right:
                st.metric(
                    "Observed gap / shot",
                    f"{context_row.OBSERVED_EXPOSURE_PER_SHOT:.4f}",
                )
                st.metric(
                    "Expected from context mix",
                    f"{context_row.MIX_EXPECTED_EXPOSURE_PER_SHOT:.4f}",
                )
                st.metric(
                    "Within-context excess",
                    f"{context_row.WITHIN_CONTEXT_EXCESS:+.4f}",
                    f"rank {int(context_row.WITHIN_CONTEXT_RANK)} high",
                )
            st.caption(
                "The expected value applies league exposure rates to this team's own mix of "
                "shot family × clock phase × possession origin. The remainder shows whether "
                "the profile survives that coarse context—not whether the shot was a mistake."
            )

        game_states = load_report("mechanism_game_states_holdout.csv")
        if not game_states.empty:
            close_fourth = game_states[
                (game_states.TEAM_ABBREVIATION == profile_team)
                & (game_states.GAME_PHASE == "fourth quarter")
                & (game_states.SCORE_STATE == "within 3")
            ]
            if not close_fourth.empty:
                close = close_fourth.iloc[0]
                st.markdown("##### Close-fourth creation pressure")
                a, b, c = st.columns(3)
                a.metric(
                    "Exposure / shot",
                    f"{close.EXPOSURE_PER_SHOT:.4f}",
                    f"league {close.LEAGUE_EXPOSURE:.4f}",
                )
                b.metric(
                    "Shot-clock second",
                    f"{close.MEAN_SECOND:.1f}s",
                    f"league {close.LEAGUE_CLOCK:.1f}s",
                )
                c.metric("Sample", f"{int(close.N_SHOTS):,} shots")
                st.caption(
                    "If exposure rises while timing stays ordinary, the more plausible reading "
                    "is difficulty creating a valuable attempt under pressure—not simply rushing."
                )

        st.markdown("##### Which players ended these possessions?")
        player_table = pd.concat(player_frames, ignore_index=True)
        selected_players = player_table[
            (player_table.WINDOW == "holdout")
            & (player_table.TEAM_ABBREVIATION == profile_team)
        ].sort_values("EXPOSURE_PER_SHOT", ascending=False)
        shown_players = selected_players[[
            "PLAYER_NAME", "N_SHOTS", "PREMATURE", "PREMATURE_MINUS_TEAM",
            "EXPOSURE_PER_SHOT", "MEAN_SECOND", "LATE_SHARE",
        ]].copy()
        for column in ("PREMATURE", "PREMATURE_MINUS_TEAM", "LATE_SHARE"):
            shown_players[column] *= 100
        st.dataframe(
            shown_players.rename(columns={
                "PLAYER_NAME": "Player", "N_SHOTS": "Shots",
                "PREMATURE": "Below curve %", "PREMATURE_MINUS_TEAM": "vs team pp",
                "EXPOSURE_PER_SHOT": "Positive gap / shot",
                "MEAN_SECOND": "Mean clock", "LATE_SHARE": "Late share %",
            }).round(3),
            use_container_width=True, hide_index=True,
        )
        st.warning(
            "**Role context, not player blame.** This names the player who took the final shot. "
            "It cannot tell who designed the action, passed up an earlier look, delivered the "
            "ball late, or was assigned to rescue the possession.",
            icon="⚠️",
        )

        left, right = st.columns(2)
        with left:
            st.markdown("##### Not timing under another name")
            fig = go.Figure(go.Scatter(
                x=holdout.MEAN_SECOND, y=holdout.PREMATURE * 100,
                mode="markers+text", text=holdout.TEAM_ABBREVIATION,
                textposition="top center", marker={"color": C[0], "size": 9},
                hovertemplate=(
                    "%{text}<br>%{x:.1f}s mean clock<br>"
                    "%{y:.1f}% premature<extra></extra>"
                ),
            ))
            fig.update_layout(
                template=TEMPLATE, height=430,
                xaxis_title="Mean shot-clock second", yaxis_title="Premature share (%)",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Across the registered comparison, premature share correlates −0.048 with "
                "mean timing and +0.026 with late-shot share. Style and deviation separate."
            )
        with right:
            st.markdown("##### Real difference, unresolved meaning")
            st.metric("Held-out signal share", "79.5%", help="Observed team variance after "
                      "subtracting the team-game permutation-null variance.")
            st.metric("Cross-window rank persistence", "+0.398", "one-sided p = 0.015")
            st.warning(
                "A high share may mean settling below an attainable ceiling. It may also mean "
                "the team's curve is flattered by the selected possessions that declined to "
                "shoot. This profile does not call either explanation proven.", icon="⚠️"
            )

        prospective = load_report("value_prospective_specifications.csv")
        if not prospective.empty:
            st.markdown("##### Does it predict the next 20 games?")
            final = prospective.iloc[-1]
            st.info(
                f"Not robustly beyond what is already visible. After current efficiency, shot "
                f"value, timing, team and season controls: {final.effect_per_1pp:+.4f} future "
                f"points per possession per +1pp premature share (p = {final.p:.3f}). The sign "
                "holds under nearby block definitions, but its magnitude and inference do not. "
                "This is not a short-horizon forecasting product."
            )
            shown = prospective[[
                "specification", "effect_per_1pp", "std_error", "p", "r2"
            ]].copy()
            st.dataframe(shown.round(4), use_container_width=True, hide_index=True)
            robustness = load_report("value_prospective_robustness.csv")
            if not robustness.empty:
                st.caption("Fully controlled sensitivity to the current/future block length")
                st.dataframe(
                    robustness[robustness.check == "block_length"][[
                        "games_per_block", "effect_per_1pp", "std_error", "p", "n"
                    ]].round(4),
                    use_container_width=True, hide_index=True,
                )

        persistence = load_report("mechanism_persistence.csv")
        sequence = load_report("mechanism_sequence_league_holdout.csv")
        if not persistence.empty and not sequence.empty:
            with st.expander("What travels across seasons—and what changes after one possession?"):
                st.markdown(
                    "**Both player and environment matter.** Franchise exposure persists year to "
                    "year; movers preserve a smaller team-relative fingerprint; their raw change "
                    "still follows the new team environment most strongly."
                )
                st.dataframe(
                    persistence[["COMPARISON", "N", "PEARSON", "SPEARMAN"]].round(3),
                    use_container_width=True, hide_index=True,
                )
                st.markdown(
                    "**Possession-to-possession memory is tiny.** After team, current possession "
                    "origin, and quarter are removed, teams take the next first shot only about "
                    "0.30 seconds earlier after an empty trip than after scoring."
                )
                st.dataframe(
                    sequence[[
                        "PREVIOUS_RESULT", "N", "CLOCK_RESIDUAL", "XPTS_RESIDUAL"
                    ]].round(4),
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
