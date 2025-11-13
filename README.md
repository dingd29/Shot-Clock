# 76ers Shot-Clock Dashboard

This lightweight Streamlit app visualizes how the Philadelphia 76ers perform across shot-clock phases and offensive play types.

## Features
- Filter by shot-clock phase ranges (`0-8`, `9-16`, `17-24` seconds) and play types (pick-and-roll variations, isolation, drive & kick, spot-up).
- KPI tiles summarizing efficiency (points per possession, effective FG%, assist rate, turnover rate) for the active filters.
- Interactive Plotly charts for:
  - Points per possession by shot-clock phase.
  - Relative efficiency by play type within the current selection.
  - Heatmap showing play type × shot-clock phase results.
- Downloadable filtered dataset for further analysis.

## Getting Started

```bash
cd /workspace
pip install -r requirements.txt
streamlit run app.py
```

Streamlit will print a local URL (e.g. `http://localhost:8501`). Open it in your browser to explore the dashboard.

## Data

The sample dataset lives in `data/76ers_shotclock.csv` and contains season-level possession outcomes for the 76ers across shot-clock windows and play types. Each row includes:

- Possessions, points, makes/attempts (including threes)
- Free-throw trips, turnovers, assists
- Derived metrics (computed in-app): points per possession, effective FG%, assist%, turnover rate, free-throw rate

You can swap in your own data by replacing the CSV with matching column headers. No additional code changes are required.
