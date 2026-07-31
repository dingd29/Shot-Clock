"""Chart theme: validated palette + Plotly defaults.

Colours come from a palette validated for colour-vision deficiency separation, so the
categorical slots are used **in fixed order and never cycled**. Scatter plots put every
pair on screen simultaneously, which is a stricter test than adjacent-only comparisons —
so those are capped at the first three slots, which clear the all-pairs floors.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

# Categorical slots, in the order they must be assigned.
CATEGORICAL_LIGHT = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]
CATEGORICAL_DARK = [
    "#3987e5", "#d95926", "#199e70", "#c98500",
    "#d55181", "#008300", "#9085e9", "#e66767",
]

# Forms that show all pairs at once (scatter, bubble) may use only these three.
ALL_PAIRS_SAFE = 3

SEQUENTIAL_BLUE = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
    "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
    "#184f95", "#104281", "#0d366b",
]

# Diverging: blue <-> red with a neutral gray midpoint. Never a hue at the midpoint.
DIVERGING_LIGHT = ["#1c5cab", "#5598e7", "#b7d3f6", "#f0efec", "#f0a3a2", "#e34948", "#a32020"]
DIVERGING_DARK = ["#184f95", "#3987e5", "#9ec5f4", "#383835", "#e66767", "#d03b3b", "#8f1d1d"]

LIGHT = {
    "surface": "#fcfcfb",
    "plane": "#f9f9f7",
    "text": "#0b0b0b",
    "text_secondary": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "categorical": CATEGORICAL_LIGHT,
    "diverging": DIVERGING_LIGHT,
}

DARK = {
    "surface": "#1a1a19",
    "plane": "#0d0d0d",
    "text": "#ffffff",
    "text_secondary": "#c3c2b7",
    "muted": "#898781",
    "grid": "#2c2c2a",
    "axis": "#383835",
    "categorical": CATEGORICAL_DARK,
    "diverging": DIVERGING_DARK,
}

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def palette(dark: bool = False) -> dict:
    return DARK if dark else LIGHT


def register(dark: bool = False) -> str:
    """Install a Plotly template and return its name."""
    p = palette(dark)
    template = go.layout.Template()
    template.layout = go.Layout(
        paper_bgcolor=p["surface"],
        plot_bgcolor=p["surface"],
        font={"family": FONT, "color": p["text"], "size": 13},
        title={"font": {"size": 16, "color": p["text"]}, "x": 0, "xanchor": "left"},
        colorway=p["categorical"],
        # Recessive chrome: hairline grid, no vertical rules, no chart border.
        xaxis={
            "gridcolor": p["grid"], "linecolor": p["axis"], "zerolinecolor": p["axis"],
            "tickfont": {"color": p["muted"], "size": 12}, "showgrid": False,
            "title": {"font": {"color": p["text_secondary"], "size": 13}},
        },
        yaxis={
            "gridcolor": p["grid"], "linecolor": p["axis"], "zerolinecolor": p["axis"],
            "tickfont": {"color": p["muted"], "size": 12}, "gridwidth": 1,
            "title": {"font": {"color": p["text_secondary"], "size": 13}},
        },
        legend={
            "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0,
            "font": {"color": p["text_secondary"], "size": 12},
            "orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0,
        },
        hoverlabel={"font": {"family": FONT, "size": 12}, "namelength": -1},
        margin={"l": 60, "r": 24, "t": 56, "b": 48},
    )
    name = "possval_dark" if dark else "possval_light"
    pio.templates[name] = template
    return name


def band_color(hex_color: str, alpha: float = 0.15) -> str:
    """Translucent fill for a confidence band, matched to its line."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"
