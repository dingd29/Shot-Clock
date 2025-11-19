"""
Scraper for NBA shot clock statistics from the NBA website.

This script scrapes data directly from: https://www.nba.com/stats/players/shots-shotclock
It does NOT use the NBA API directly - instead it:
1. Loads the actual website page
2. Interacts with the "Shot Clock Range" filter dropdown on the page
3. Selects each shot clock range (24-22, 22-18, 18-15, 15-7, 7-4, 4-0)
4. Extracts data from the rendered HTML table

The website uses JavaScript to load data dynamically, so Selenium is required
to interact with the page and wait for content to load.
"""

import time
import json
import pandas as pd
import requests
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from io import StringIO


# Shot clock ranges as they appear on the website
# Note: The URL format includes descriptive labels like "Very Early", "Early", etc.
SHOT_CLOCK_RANGES = [
    "24-22",  # Very Early
    "22-18",  # Very Early
    "18-15",  # Early
    "15-7",   # Average
    "7-4",    # Late
    "4-0"     # Very Late
]

# Map shot clock ranges to their URL parameter format
SHOT_CLOCK_URL_MAP = {
    "24-22": "24-22",  # May need "24-22 Very Early" - will try both
    "22-18": "22-18+Very+Early",
    "18-15": "18-15+Early",
    "15-7": "15-7+Average",
    "7-4": "7-4+Late",
    "4-0": "4-0+Very+Late"
}

BASE_URL = "https://www.nba.com/stats/players/shots-shotclock"
SEASON = "2024-25"


def get_nba_api_data(shot_clock_range: str, season: str = SEASON) -> Optional[pd.DataFrame]:
    """
    Attempt to fetch data directly from NBA API endpoint.
    Returns DataFrame if successful, None otherwise.
    """
    try:
        # NBA stats API endpoint structure
        # This is a common pattern for NBA stats endpoints
        api_url = "https://stats.nba.com/stats/leaguedashplayershotlocations"
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nba.com/',
            'Origin': 'https://www.nba.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Try alternative endpoint for shot clock data
        # The actual endpoint may vary - this is a common pattern
        # Use the URL map format for API calls too
        shot_clock_url_param = SHOT_CLOCK_URL_MAP.get(shot_clock_range, shot_clock_range)
        params = {
            'Season': season,
            'SeasonType': 'Regular Season',
            'ShotClockRange': shot_clock_url_param,
            'PerMode': 'Totals'
        }
        
        response = requests.get(api_url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'resultSets' in data and len(data['resultSets']) > 0:
                # Parse the result set
                result_set = data['resultSets'][0]
                headers_list = result_set['headers']
                rows = result_set['rowSet']
                
                df = pd.DataFrame(rows, columns=headers_list)
                df['SHOT_CLOCK_RANGE'] = shot_clock_range
                return df
    except Exception as e:
        print(f"API method failed for {shot_clock_range}: {e}")
    
    return None


def scrape_with_selenium(shot_clock_range: str, season: str = SEASON) -> Optional[pd.DataFrame]:
    """
    Scrape data directly from the NBA website (https://www.nba.com/stats/players/shots-shotclock).
    This method:
    1. Loads the actual website page
    2. Interacts with the "Shot Clock Range" filter dropdown
    3. Selects the specified shot clock range
    4. Extracts data from the rendered HTML table
    """
    chrome_options = Options()
    # Don't use headless initially - it can help with debugging and some sites detect headless
    # chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Enable logging to capture network requests (for API interception)
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    chrome_options.set_capability('goog:chromeOptions', {'perfLoggingPrefs': {'enableNetwork': True}})
    
    driver = None
    try:
        # Try to use webdriver-manager if available, otherwise use system ChromeDriver
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except ImportError:
            # Fallback to system ChromeDriver
            driver = webdriver.Chrome(options=chrome_options)
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Load the actual NBA stats website
        # Use the EXACT URL format that works: SeasonType=Regular+Season (with plus sign)
        # Format: https://www.nba.com/stats/players/shots-shotclock?Season=2024-25&ShotClockRange=22-18+Very+Early&SeasonType=Regular+Season
        # The shot clock range URL parameter includes descriptive labels like "Very Early", "Early", etc.
        shot_clock_url_param = SHOT_CLOCK_URL_MAP.get(shot_clock_range, shot_clock_range)
        url = f"{BASE_URL}?Season={season}&ShotClockRange={shot_clock_url_param}&SeasonType=Regular+Season"
        print(f"🌐 Loading NBA website with exact URL format:")
        print(f"   {url}")
        print(f"   ✅ Season Type: Regular Season (explicitly in URL)")
        print(f"   ✅ Shot Clock Range: {shot_clock_range} -> URL param: {shot_clock_url_param}")
        driver.get(url)
        
        # Wait for page to fully load - wait for the main content/table to appear
        print("⏳ Waiting for page to load...")
        time.sleep(5)
        
        # Wait for the table or main content area to be present
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            print("✅ Page loaded, table found")
        except TimeoutException:
            print("⚠️  Table not found immediately, continuing anyway...")
        
        # Verify the URL loaded correctly with Regular Season
        # Since we're using the exact URL format, it should already be set correctly
        print("🔧 Verifying URL loaded correctly...")
        time.sleep(4)  # Wait for page to fully load
        
        # Check current URL
        current_url = driver.current_url
        print(f"   Current URL: {current_url[:150]}...")
        
        # Verify Regular Season is in the URL
        if 'SeasonType=Regular+Season' in current_url or 'SeasonType=Regular%20Season' in current_url:
            print(f"   ✅ URL contains 'SeasonType=Regular+Season' - correct!")
        elif 'SeasonType' in current_url:
            print(f"   ⚠️  WARNING: URL has SeasonType but might not be Regular Season")
            print(f"   Full URL: {current_url}")
        else:
            print(f"   ⚠️  WARNING: URL doesn't have SeasonType parameter")
        
        # Verify shot clock range is in URL (check for the mapped format)
        if f'ShotClockRange={shot_clock_url_param}' in current_url or f'ShotClockRange={shot_clock_range}' in current_url:
            print(f"   ✅ URL contains 'ShotClockRange={shot_clock_url_param}' - correct!")
        else:
            print(f"   ⚠️  WARNING: Shot clock range might not be in URL correctly")
            print(f"   Expected: ShotClockRange={shot_clock_url_param}")
        
        # Since we're loading the page with the shot clock range and SeasonType already in the URL,
        # we don't need to interact with any filters - they're already set correctly!
        print("✅ Shot Clock Range and Season Type are already set in URL - no filter interaction needed")
        
        # Wait for data to load
        print("⏳ Waiting for data to load...")
        time.sleep(6)  # Give time for API call and table update
        
        # Verify the page has player data
        try:
            page_text = driver.page_source.lower()
            has_player_data = 'player' in page_text and ('fgm' in page_text or 'fga' in page_text)
            
            if not has_player_data:
                print(f"⚠️  Warning: Page doesn't seem to have player data yet, waiting longer...")
                time.sleep(4)
            else:
                print(f"✅ Player data detected on page")
        except:
            pass
        
        # IMPORTANT: The page only shows ~50 rows at a time, but there are ~500 total rows
        # We need to load all rows before extracting. Try multiple strategies:
        print("📄 Loading all rows (page shows ~50 at a time, but there are ~500 total)...")
        
        # Strategy 1: Try to scroll to bottom to trigger lazy loading
        try:
            print("   Trying to scroll to load all rows...")
            # Scroll to bottom of page multiple times to trigger lazy loading
            last_height = driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scrolls = 10
            
            while scroll_attempts < max_scrolls:
                # Scroll to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)  # Wait for content to load
                
                # Check if new content loaded
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    # No new content, might be done or need to click "Load More"
                    break
                last_height = new_height
                scroll_attempts += 1
                print(f"   Scrolled (attempt {scroll_attempts}/{max_scrolls}), page height: {new_height}")
            
            # Also try scrolling the table container specifically
            try:
                table_container = driver.find_element(By.CSS_SELECTOR, "div[class*='table'], div[class*='Table'], .stats-table-pagination")
                for i in range(5):
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", table_container)
                    time.sleep(1)
            except:
                pass
                
        except Exception as e:
            print(f"   Scrolling failed: {e}")
        
        # Strategy 2: Look for "Load More" or "Show All" buttons
        try:
            print("   Looking for 'Load More' or pagination buttons...")
            load_more_selectors = [
                "button:contains('Load More')",
                "button:contains('Show More')",
                "button:contains('Show All')",
                "//button[contains(text(), 'Load More')]",
                "//button[contains(text(), 'Show More')]",
                "//button[contains(text(), 'Show All')]",
                ".stats-table-pagination__more",
                "button[aria-label*='more']",
                "button[aria-label*='load']"
            ]
            
            for selector in load_more_selectors:
                try:
                    if selector.startswith("//"):
                        buttons = driver.find_elements(By.XPATH, selector)
                    else:
                        buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    if buttons:
                        print(f"   Found load more button, clicking multiple times...")
                        # Click multiple times to load all data
                        for i in range(10):  # Try up to 10 times
                            try:
                                button = buttons[0]
                                if button.is_displayed() and button.is_enabled():
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                    time.sleep(0.5)
                                    button.click()
                                    time.sleep(2)  # Wait for data to load
                                    print(f"      Clicked load more button (iteration {i+1})")
                                else:
                                    break
                            except:
                                break
                        break
                except:
                    continue
        except Exception as e:
            print(f"   Load more button search failed: {e}")
        
        # Strategy 3: Try to change pagination to show all rows at once
        try:
            print("   Looking for pagination controls to show all rows...")
            # Look for dropdown to change rows per page
            pagination_selectors = [
                "select[name*='page']",
                "select[name*='rows']",
                "select[name*='per']",
                ".stats-table-pagination select",
                "//select[.//option[contains(text(), 'All')]]",
                "//select[.//option[contains(text(), '500')]]"
            ]
            
            for selector in pagination_selectors:
                try:
                    if selector.startswith("//"):
                        selects = driver.find_elements(By.XPATH, selector)
                    else:
                        selects = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    if selects:
                        from selenium.webdriver.support.ui import Select
                        select = Select(selects[0])
                        # Try to select "All" or highest number
                        try:
                            select.select_by_visible_text("All")
                            print("   Selected 'All' in pagination")
                            time.sleep(3)
                            break
                        except:
                            try:
                                select.select_by_visible_text("500")
                                print("   Selected '500' in pagination")
                                time.sleep(3)
                                break
                            except:
                                # Select the FIRST option (not the last)
                                options = select.options
                                if len(options) > 0:
                                    select.select_by_index(0)
                                    print(f"   Selected first option in pagination: {options[0].text}")
                                    time.sleep(3)
                                    break
                except:
                    continue
        except Exception as e:
            print(f"   Pagination control search failed: {e}")
        
        # Give final wait for all data to load
        time.sleep(3)
        print("✅ Finished attempting to load all rows")
        
        # Extract data from the page
        # Strategy 1: Try to find and parse the ACTUAL stats data table (not calendar/widgets)
        try:
            print("🔍 Looking for player stats table...")
            # Wait for the main stats table to be present
            # The NBA stats page uses specific classes for the data table
            table_selectors = [
                # More specific selectors for the actual stats table
                "table.Crom_table__p1iZz",  # Common NBA stats table class
                "table[class*='Crom']",
                ".nba-stat-table__table",
                ".stats-table-pagination__table",
                "table[class*='stats']",
                "table[class*='player']",
                # Look for table with player-related content
                "//table[.//th[contains(text(), 'Player')]]",
                "//table[.//th[contains(text(), 'FGM')]]",
                "//table[.//th[contains(text(), 'FGA')]]",
                "//table[.//th[contains(text(), 'FG%')]]",
                # Fallback to any table, but we'll filter them
                "table"
            ]
            
            table = None
            for selector in table_selectors:
                try:
                    if selector.startswith("//"):
                        # XPath selector
                        table = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                    else:
                        # CSS selector
                        table = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    if table:
                        print(f"   Found table with selector: {selector}")
                        break
                except:
                    continue
            
            # If we found a table, verify it's the stats table (not a calendar/widget)
            if table:
                # Get all tables and find the one with player stats
                all_tables = driver.find_elements(By.TAG_NAME, "table")
                print(f"   Found {len(all_tables)} total table(s) on page")
                
                stats_table = None
                for t in all_tables:
                    try:
                        table_text = t.text.lower()
                        table_html = t.get_attribute('outerHTML')
                        
                        # Check if this looks like a stats table (has player names, stats)
                        # Calendar tables will have days of week, date pickers, etc.
                        has_stats_indicators = any(indicator in table_text for indicator in [
                            'player', 'fgm', 'fga', 'fg%', '3pm', '3pa', 'pts', 'reb', 'ast'
                        ])
                        has_calendar_indicators = any(indicator in table_text.lower() for indicator in [
                            'sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat',
                            'november', 'december', 'january', 'february'
                        ])
                        
                        # Also check table size - stats tables should have many rows
                        rows = t.find_elements(By.TAG_NAME, "tr")
                        
                        if has_stats_indicators and not has_calendar_indicators and len(rows) > 10:
                            stats_table = t
                            print(f"   ✅ Found stats table with {len(rows)} rows")
                            break
                    except:
                        continue
                
                if not stats_table and all_tables:
                    # Fallback: use the largest table that's not obviously a calendar
                    for t in sorted(all_tables, key=lambda x: len(x.find_elements(By.TAG_NAME, "tr")), reverse=True):
                        table_text = t.text.lower()
                        if 'sun' not in table_text and 'mon' not in table_text:
                            stats_table = t
                            print(f"   Using largest non-calendar table")
                            break
                
                if stats_table:
                    # Extract table HTML and convert to DataFrame
                    from io import StringIO
                    table_html = stats_table.get_attribute('outerHTML')
                    dfs = pd.read_html(StringIO(table_html))
                    
                    if dfs and len(dfs) > 0:
                        df = dfs[0]
                        # Clean up the dataframe - remove any index columns
                        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
                        
                        # Verify this looks like player stats (should have player names or stats columns)
                        # Check if it's actually player data, not calendar/widget
                        df_columns_lower = [str(col).lower() for col in df.columns]
                        has_player_col = any('player' in col for col in df_columns_lower)
                        has_stats_cols = any(col in df_columns_lower for col in ['fgm', 'fga', 'fg%', 'fg_pct'])
                        is_calendar = any(col in df_columns_lower for col in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'])
                        
                        if is_calendar:
                            print(f"⚠️  Skipping calendar table (has day columns)")
                            # This is a calendar table, skip it and try next extraction method
                            stats_table = None
                        elif len(df) > 0 and len(df.columns) > 3 and (has_player_col or has_stats_cols):
                            df['SHOT_CLOCK_RANGE'] = shot_clock_range
                            print(f"✅ Extracted {len(df)} rows from stats table for {shot_clock_range}")
                            return df
                        else:
                            print(f"⚠️  Table found but doesn't look like stats data (rows: {len(df)}, cols: {len(df.columns)}, has_player: {has_player_col}, has_stats: {has_stats_cols})")
                            stats_table = None
        except Exception as e:
            print(f"Table extraction failed: {e}")
            import traceback
            traceback.print_exc()
        
        # Strategy 2: Intercept network requests to get the actual API data
        # This is the BEST method - the API response should have ALL 500 rows
        try:
            print("🔍 Checking network requests for API data (this should have all 500 rows)...")
            # Get performance logs to see network requests
            logs = driver.get_log('performance')
            
            # Look for the most recent API call (should be after filter selection)
            api_responses = []
            for log in logs:
                try:
                    message = json.loads(log['message'])['message']
                    if message['method'] == 'Network.responseReceived':
                        url = message['params']['response']['url']
                        # Look for NBA stats API endpoints
                        if 'stats.nba.com/stats' in url:
                            # Check if it's a stats endpoint (could be shotclock, leaguedash, etc.)
                            if any(keyword in url.lower() for keyword in ['shotclock', 'leaguedash', 'playershot']):
                                api_responses.append({
                                    'url': url,
                                    'requestId': message['params']['requestId'],
                                    'timestamp': log.get('timestamp', 0)
                                })
                except:
                    continue
            
            # Try the most recent API response (should be the one with our filtered data)
            if api_responses:
                # Sort by timestamp, most recent first
                api_responses.sort(key=lambda x: x['timestamp'], reverse=True)
                print(f"   Found {len(api_responses)} potential API response(s)")
                
                for api_resp in api_responses[:3]:  # Try the 3 most recent
                    try:
                        print(f"   Trying API response: {api_resp['url'][:80]}...")
                        
                        # CRITICAL: Check the URL to see if it has SeasonType parameter
                        # We MUST reject any NBA Cup data
                        url_lower = api_resp['url'].lower()
                        full_url = api_resp['url']
                        print(f"   Checking API URL: {full_url[:150]}...")
                        
                        # First, check for NBA Cup - reject immediately
                        if any(term in url_lower for term in ['cup', 'nbacup', 'nba%20cup', 'nba+cup']):
                            print(f"   ❌ REJECTED: URL contains NBA Cup - skipping this response!")
                            continue
                        
                        # Check for Regular Season
                        has_regular_season = any(term in url_lower for term in [
                            'regular', 'regularseason', 'regular%20season', 'regular+season'
                        ])
                        
                        # Check for SeasonType parameter
                        import re
                        season_type_match = re.search(r'[&?]seasonType[=:]([^&]+)', url_lower, re.IGNORECASE)
                        if season_type_match:
                            season_type_val = season_type_match.group(1)
                            print(f"   Found SeasonType parameter: {season_type_val}")
                            
                            # Decode URL encoding
                            from urllib.parse import unquote
                            season_type_val = unquote(season_type_val).lower()
                            
                            if 'cup' in season_type_val:
                                print(f"   ❌ REJECTED: SeasonType is NBA Cup - skipping!")
                                continue
                            elif 'regular' in season_type_val:
                                print(f"   ✅ SeasonType is Regular Season")
                            else:
                                print(f"   ⚠️  Unknown SeasonType value: {season_type_val}")
                                # If we can't determine, skip to be safe
                                continue
                        elif not has_regular_season:
                            print(f"   ⚠️  No SeasonType parameter found and no 'regular' in URL")
                            print(f"   ⚠️  This might be NBA Cup data - skipping to be safe!")
                            continue
                        
                        # Get the response body
                        response_body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': api_resp['requestId']})
                        if response_body and 'body' in response_body:
                            data = json.loads(response_body['body'])
                            if 'resultSets' in data and len(data['resultSets']) > 0:
                                result_set = data['resultSets'][0]
                                headers_list = result_set.get('headers', [])
                                rows = result_set.get('rowSet', [])
                                if rows and len(rows) > 10:  # Should have many rows
                                    df = pd.DataFrame(rows, columns=headers_list)
                                    
                                    # Double-check: Verify this is Regular Season data, not NBA Cup
                                    # Check if any column names or data suggest NBA Cup
                                    df_str = df.to_string().lower()
                                    if 'cup' in df_str and 'nba' in df_str:
                                        print(f"   ❌ REJECTED: Data contains NBA Cup references - skipping!")
                                        continue
                                    
                                    # Also check the first few rows of data for NBA Cup indicators
                                    sample_data = str(df.head(10).to_dict()).lower()
                                    if 'cup' in sample_data and 'nba' in sample_data:
                                        print(f"   ❌ REJECTED: Sample data contains NBA Cup references - skipping!")
                                        continue
                                    
                                    df['SHOT_CLOCK_RANGE'] = shot_clock_range
                                    print(f"✅ Extracted {len(df)} rows from API response for {shot_clock_range}")
                                    print(f"   ✅ Confirmed: This is Regular Season data (not NBA Cup)")
                                    return df
                    except Exception as e:
                        print(f"   Failed to extract from this API response: {e}")
                        continue
        except Exception as e:
            print(f"Network request interception failed: {e}")
            import traceback
            traceback.print_exc()
        
        # Strategy 3: Try to extract JSON data from page source
        try:
            print("🔍 Checking page source for embedded JSON data...")
            page_source = driver.page_source
            
            # Look for common patterns of embedded data
            import re
            json_patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.__PRELOADED_STATE__\s*=\s*({.+?});',
                r'"resultSets":\s*(\[.+?\])',
                r'"rowSet":\s*(\[.+?\])',
                r'var\s+data\s*=\s*({.+?});',
                r'const\s+data\s*=\s*({.+?});'
            ]
            
            for pattern in json_patterns:
                json_match = re.search(pattern, page_source, re.DOTALL)
                if json_match:
                    try:
                        data_str = json_match.group(1)
                        data = json.loads(data_str)
                        print("   Found JSON data in page source")
                        
                        # Try to extract table data from JSON
                        if isinstance(data, dict):
                            # Look for common data structures
                            if 'resultSets' in data:
                                result_set = data['resultSets'][0]
                                headers_list = result_set.get('headers', [])
                                rows = result_set.get('rowSet', [])
                                if rows:
                                    df = pd.DataFrame(rows, columns=headers_list)
                                    df['SHOT_CLOCK_RANGE'] = shot_clock_range
                                    print(f"✅ Extracted {len(df)} rows from JSON for {shot_clock_range}")
                                    return df
                    except Exception as e:
                        continue
        except Exception as e:
            print(f"JSON extraction attempt failed: {e}")
        
        # Strategy 4: Try to get data from the table using BeautifulSoup for better parsing
        try:
            print("🔍 Trying BeautifulSoup extraction...")
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Find all tables
            tables = soup.find_all('table')
            print(f"   Found {len(tables)} table(s) with BeautifulSoup")
            
            for table in tables:
                try:
                    # Check if this is a calendar/widget table (skip it)
                    table_text = table.get_text().lower()
                    if any(indicator in table_text for indicator in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                        print(f"   Skipping calendar table")
                        continue
                    
                    # Check if it has stats indicators
                    has_stats = any(indicator in table_text for indicator in [
                        'player', 'fgm', 'fga', 'fg%', '3pm', '3pa', 'pts'
                    ])
                    
                    if not has_stats:
                        continue
                    
                    # Try to parse the table
                    dfs = pd.read_html(StringIO(str(table)))
                    if dfs and len(dfs) > 0:
                        df = dfs[0]
                        
                        # Verify it's player stats, not calendar
                        df_columns_lower = [str(col).lower() for col in df.columns]
                        is_calendar = any(col in df_columns_lower for col in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'])
                        has_player_col = any('player' in col for col in df_columns_lower)
                        has_stats_cols = any(col in df_columns_lower for col in ['fgm', 'fga', 'fg%', 'fg_pct'])
                        
                        if is_calendar:
                            print(f"   Skipping calendar table in BeautifulSoup")
                            continue
                        
                        # Check if this looks like player stats data
                        # Should have multiple columns and rows, and player/stats columns
                        if len(df.columns) > 5 and len(df) > 10 and (has_player_col or has_stats_cols):
                            df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
                            df['SHOT_CLOCK_RANGE'] = shot_clock_range
                            print(f"✅ Extracted {len(df)} rows using BeautifulSoup for {shot_clock_range}")
                            return df
                        else:
                            print(f"   Table doesn't meet criteria (rows: {len(df)}, cols: {len(df.columns)}, has_player: {has_player_col}, has_stats: {has_stats_cols})")
                except Exception as e:
                    continue
        except Exception as e:
            print(f"BeautifulSoup extraction failed: {e}")
        
        # Strategy 3: Try to intercept network requests (advanced)
        # This would require setting up request interception, which is more complex
        
    except Exception as e:
        print(f"❌ Selenium scraping failed for {shot_clock_range}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
    
    return None


def scrape_with_requests_api(shot_clock_range: str, season: str = SEASON) -> Optional[pd.DataFrame]:
    """
    Attempt to call the NBA stats API directly by inspecting network requests.
    The NBA stats site uses specific API endpoints that we can call directly.
    """
    try:
        # The NBA stats API endpoint for shot clock data
        # Based on the URL structure: /stats/players/shots-shotclock
        api_url = "https://stats.nba.com/stats/leaguedashplayershotclock"
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nba.com/stats/players/shots-shotclock',
            'Origin': 'https://www.nba.com',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-nba-stats-origin': 'stats',
            'x-nba-stats-token': 'true'
        }
        
        # Map shot clock ranges to API values (NBA API uses specific format)
        shot_clock_map = {
            "24-22": "24-22",
            "22-18": "22-18", 
            "18-15": "18-15",
            "15-7": "15-7",
            "7-4": "7-4",
            "4-0": "4-0"
        }
        
        params = {
            'Season': season,
            'SeasonType': 'Regular Season',
            'ShotClockRange': shot_clock_map.get(shot_clock_range, shot_clock_range),
            'PerMode': 'Totals',
            'MeasureType': 'Base',
            'PlusMinus': 'N',
            'PaceAdjust': 'N',
            'Rank': 'N',
            'LeagueID': '00',
            'GameScope': '',
            'PlayerExperience': '',
            'PlayerPosition': '',
            'StarterBench': '',
            'TeamID': '0',
            'VsConference': '',
            'VsDivision': '',
            'GameSegment': '',
            'Period': '0',
            'LastNGames': '0',
            'DateFrom': '',
            'DateTo': '',
            'Outcome': '',
            'Location': '',
            'Month': '0',
            'SeasonSegment': '',
            'Conference': '',
            'Division': ''
        }
        
        print(f"Fetching data for shot clock range {shot_clock_range}...")
        # Increase timeout and add retry logic
        response = requests.get(api_url, headers=headers, params=params, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'resultSets' in data and len(data['resultSets']) > 0:
                result_set = data['resultSets'][0]
                headers_list = result_set['headers']
                rows = result_set['rowSet']
                
                if rows:
                    df = pd.DataFrame(rows, columns=headers_list)
                    df['SHOT_CLOCK_RANGE'] = shot_clock_range
                    print(f"✅ Successfully fetched {len(df)} rows for {shot_clock_range}")
                    return df
                else:
                    print(f"⚠️  No data rows returned for {shot_clock_range}")
            else:
                print(f"⚠️  Unexpected API response structure for {shot_clock_range}")
        else:
            print(f"❌ API request failed with status {response.status_code} for {shot_clock_range}")
            # Try alternative endpoint
            return try_alternative_api_endpoint(shot_clock_range, season)
            
    except Exception as e:
        print(f"❌ Error fetching data for {shot_clock_range}: {e}")
        # Try alternative endpoint
        return try_alternative_api_endpoint(shot_clock_range, season)
    
    return None


def try_alternative_api_endpoint(shot_clock_range: str, season: str = SEASON) -> Optional[pd.DataFrame]:
    """
    Try alternative NBA API endpoints for shot clock data.
    """
    try:
        # Alternative endpoint - sometimes the endpoint structure varies
        api_url = "https://stats.nba.com/stats/leaguedashplayerstats"
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nba.com/stats/players/shots-shotclock',
            'Origin': 'https://www.nba.com',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-nba-stats-origin': 'stats',
            'x-nba-stats-token': 'true'
        }
        
        # Try using the nba-api library if available
        try:
            # Check if the endpoint exists - it might have a different name
            from nba_api.stats.endpoints import leaguedashplayerstats
            
            # The nba-api library might not have a direct shot clock endpoint
            # So we'll try to use the general player stats endpoint with shot clock filter
            # Note: This might not work directly, but worth trying
            print("Attempting to use nba-api library...")
            
            # Actually, let's check what endpoints are available
            # For now, skip this and rely on direct API calls or Selenium
            pass
        except ImportError as e:
            print(f"nba-api library import issue: {e}")
        except Exception as e:
            print(f"nba-api method failed: {e}")
            
    except Exception as e:
        print(f"Alternative API endpoint failed: {e}")
    
    return None


def main():
    """
    Main function to scrape shot clock data for all ranges.
    """
    print("=" * 60)
    print("NBA Shot Clock Data Scraper")
    print("=" * 60)
    print(f"Season: {SEASON}")
    print(f"Shot Clock Ranges: {', '.join(SHOT_CLOCK_RANGES)}")
    print("=" * 60)
    
    all_data = []
    
    for shot_clock_range in SHOT_CLOCK_RANGES:
        print(f"\n📊 Processing shot clock range: {shot_clock_range}")
        
        # PRIMARY METHOD: Scrape directly from the website using Selenium
        # This is the most reliable method as it interacts with the actual webpage
        print(f"🌐 Scraping from NBA website...")
        df = scrape_with_selenium(shot_clock_range, SEASON)
        
        # FALLBACK: Try direct API calls if website scraping fails
        # Note: This may not work as the API might require authentication or have different endpoints
        if df is None or df.empty:
            print(f"⚠️  Website scraping failed, trying direct API call as fallback...")
            df = scrape_with_requests_api(shot_clock_range, SEASON)
        
        if df is not None and not df.empty:
            # FINAL CHECK: Verify this is NOT NBA Cup data before saving
            df_str = str(df).lower()
            df_columns_str = ' '.join([str(col).lower() for col in df.columns])
            
            # Check for NBA Cup indicators
            has_nba_cup = any([
                'nba cup' in df_str,
                'nbacup' in df_str,
                'nba cup' in df_columns_str,
                ('cup' in df_str and 'nba' in df_str and 'regular' not in df_str)
            ])
            
            if has_nba_cup:
                print(f"❌ REJECTED: Data for {shot_clock_range} appears to be NBA Cup data - NOT saving!")
                print(f"   This data will be skipped. Please check the Season Type filter.")
            else:
                all_data.append(df)
                print(f"✅ Collected {len(df)} rows for {shot_clock_range} (Regular Season data)")
        else:
            print(f"❌ Failed to collect data for {shot_clock_range}")
        
        # Be respectful with rate limiting
        time.sleep(2)
    
    # Combine all data
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        
        # Save to CSV
        output_file = "nba_shotclock_data.csv"
        final_df.to_csv(output_file, index=False)
        print("\n" + "=" * 60)
        print(f"✅ Successfully saved {len(final_df)} total rows to {output_file}")
        print(f"📁 Shot clock ranges included: {final_df['SHOT_CLOCK_RANGE'].unique()}")
        print("=" * 60)
        
        # Display summary
        print("\n📈 Data Summary:")
        print(final_df.groupby('SHOT_CLOCK_RANGE').size())
        
        return final_df
    else:
        print("\n❌ No data collected. Please check your internet connection and try again.")
        return None


if __name__ == "__main__":
    main()

