# NBA Shot-Clock Dashboard

This Streamlit app visualizes how every NBA team and player performs across six shot-clock windows during the 2024-25 **Regular Season**. The data comes from the official NBA stats site (scraped via `data/scrape_shotclock_data.py`) and is stored locally in `nba_shotclock_data.csv`.

## Key Features
- **Global filters**: shot-clock range selection, team selector, player search, and minimum FGA threshold.
- **Team view**: KPI tiles plus FG% / eFG% / Points-per-FGA charts by shot-clock range, heatmap comparison, and downloadable table.
- **Player view**: aggregate player metrics, shot-clock bar chart, per-player line analysis (FG% vs eFG%), and detailed table export.
- **Top performers**: automatically highlights the best teams and players for each shot-clock bucket.
- **Detailed data tab**: sortable data grids with one-click CSV exports for both teams and players.

## Getting Started

```bash
cd /Users/davidding/Shot-Clock  # adjust if your repo lives elsewhere
pip install -r requirements.txt
streamlit run app.py
```

Streamlit prints a local URL (e.g. `http://localhost:8501`). Open it in your browser to explore or share the dashboard.

## Data Notes
- Source file: `nba_shotclock_data.csv`
- Columns include: `PLAYER_ID`, `PLAYER_NAME`, `PLAYER_LAST_TEAM_ABBREVIATION`, `FGM`, `FGA`, `FG3M`, `FG3A`, `FG2M`, `FG2A`, `GP`, `AGE`, `SHOT_CLOCK_RANGE`, etc.
- `SHOT_CLOCK_RANGE` buckets (ordered): `24-22`, `22-18`, `18-15`, `15-7`, `7-4`, `4-0`.
- Derived metrics (e.g., `POINTS`, FG%, eFG%, Pts/FGA) are calculated inside `src/data_loader.py`.

To refresh the dataset, rerun `python data/scrape_shotclock_data.py` (requires Chrome + Selenium) and restart the Streamlit app. As long as the CSV columns remain consistent, no code changes are necessary.
