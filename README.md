# 76ers Shot-Clock Dashboard

This lightweight Streamlit app pulls the Philadelphia 76ers' shot-clock dashboard from [stats.nba.com](https://www.nba.com/stats/teams/shots-shotclock) and visualises how the team performs across the official shot-clock buckets and shooting categories.

## Features
- Filter by NBA.com's shot-clock ranges (`24-22`, `22-18 Very Early`, `18-15 Early`, `15-7 Average`, `7-4 Late`, `4-0 Very Late`).
- Compare shooting segments provided by the site (`Overall`, `Catch and Shoot`, `Pullups`, `Less Than 10 ft`).
- KPI tiles summarising effective FG%, overall FG%, 3P%, and points per shot for the current selection.
- Plotly charts for:
  - Points per shot by shot-clock range.
  - Points per shot by shooting category.
  - Heatmap (category × shot-clock range) to spot sweet spots.
- Download the filtered dataset as CSV for deeper analysis.

## Getting Started

```bash
cd /workspace
pip install -r requirements.txt
streamlit run app.py
```

Streamlit will print a local URL (e.g. `http://localhost:8501`). Open it in your browser to explore the dashboard.

> **Note:** The app fetches data directly from `https://stats.nba.com/stats/leaguedashteamptshot`. Ensure your network environment allows outbound HTTPS requests to `stats.nba.com`. If the call is blocked, the app will display an error instead of the charts.

## Data Source

- Endpoint: `https://stats.nba.com/stats/leaguedashteamptshot`
- Query parameters: 76ers team ID (`1610612755`), season `2024-25`, `Regular Season`, plus the available `GeneralRange` and `ShotClockRange` filters surfaced on the public dashboard.
- Returned columns include field-goal makes/attempts, percentages (FG%, EFG%, 3P%), shot-frequency metrics, and the aggregated shot-clock buckets.
- The app derives additional metrics (points per shot, 3PA rate, FGA share within the current filter) for display.

If you need to target a different season or team, adjust the call in `src/data_loader.py` (season/season type constants) or the constants in `src/nba_stats.py`.
