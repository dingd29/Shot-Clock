import time
import pandas as pd
from nba_api.stats.static import teams
from nba_api.stats.endpoints import shotchartdetail

# 1. Get all NBA teams
nba_teams = teams.get_teams()

# 2. Helper function to fetch shot data for one team
def get_team_shot_data(team_id, season='2024-25'):
    """
    Fetches shot chart data for a given team and season.
    """
    response = shotchartdetail.ShotChartDetail(
        team_id=team_id,
        player_id=0,
        season_type_all_star='Regular Season',
        season_nullable=season,
        context_measure_simple='FGA'  # Field Goal Attempts
    )

    # Convert to DataFrame
    df = response.get_data_frames()[0]
    df['TEAM_ID'] = team_id
    df['SEASON'] = season
    return df

# 3. Iterate over all teams and collect data
all_shots = []
season = '2024-25'

for t in nba_teams:
    team_name = t['full_name']
    team_id = t['id']
    print(f"Fetching data for {team_name} ({team_id})...")

    try:
        team_df = get_team_shot_data(team_id, season)
        team_df['TEAM_NAME'] = team_name
        all_shots.append(team_df)

        # Respect NBA API rate limit
        time.sleep(1.5)

    except Exception as e:
        print(f"Failed for {team_name}: {e}")

# 4. Combine all data and save to CSV
if all_shots:
    final_df = pd.concat(all_shots, ignore_index=True)
    final_df.to_csv("nba_all_teams_shots.csv", index=False)
    print(f"✅ Saved {len(final_df)} shots to nba_all_teams_shots.csv")
else:
    print("No data collected.")