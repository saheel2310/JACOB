import requests
import json
import os
import datetime
import time
import argparse
import logging
import logging.handlers # For rotating file logging
import tempfile
import pathlib
import sys # To control stdout/stderr directly if needed (used for flush)
from dotenv import load_dotenv
import pytz
import backoff
import urllib.parse

# --- Configuration ---
# Load environment variables from .env file
# load_dotenv()
# API_KEY = os.getenv("BETWATCH_API_KEY")
API_KEY="b350fb40-937c-4ec5-a68e-3f3671e096d8"


GRAPHQL_ENDPOINT = "https://api.betwatch.com/query"

# Bookmakers to check against Betfair (Used for final price check)
TARGET_BOOKMAKERS_STR = ["Sportsbet", "Tab", "Boombet", "Tabtouch"]

# Time window for races (in minutes)
MIN_TIME_TO_JUMP = 2
MAX_TIME_TO_JUMP = 15

# Race types to include (Use the string values for GraphQL)
TARGET_RACE_TYPES_STR = ["Greyhound", "Harness"]

# Locations/States to include (Removed NZ as requested)
TARGET_LOCATIONS = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"] 

# Pagination settings
PAGE_LIMIT = 95 # Keep slightly under 100 for safety

# Loop settings (Default, can be overridden by args)
DEFAULT_CHECK_INTERVAL_SECONDS = 3 # <-- Defaulting to faster checks

# Set to keep track of reported opportunities for the entire duration of the script run.
# Key: (race_id, runner_id, bookmaker_name_str)
# This set is NOT cleared in the main loop to prevent duplicate alerts.
PERSISTENT_REPORTED_OPPORTUNITIES = set()

# --- Logging Setup ---
log_file_path = None # Global variable to store log file path for confirmation message

def place_bet(**kwargs):
    """
    Function to place a bet using the provided parameters.
    This is a placeholder function and should be implemented with actual betting logic.
    """
    # Placeholder for placing a bet
    print(f"Placing bet with parameters: {kwargs}")
    # Implement actual betting logic here
              
def setup_logging(log_level_str):
    """Configures logging ONLY to a rotating file in temp directory."""
    global log_file_path # Declare intent to modify the global variable
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    # More detailed log format
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s')
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level) # Set overall level

    # --- Remove Existing Handlers (Clean Slate) ---
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # --- File Handler ---
    try:
        temp_dir = pathlib.Path(tempfile.gettempdir())
        log_dir = temp_dir / "betwatch_finder_logs"
        log_dir.mkdir(parents=True, exist_ok=True) # Create log directory if it doesn't exist
        log_file_name = f"betwatch_opp_finder_{datetime.date.today().strftime('%Y-%m-%d')}.log"
        log_file_path = log_dir / log_file_name

        # Use RotatingFileHandler to limit log file size (e.g., 10MB per file, keep 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(log_level) # File logs at the requested level (INFO or DEBUG)
        root_logger.addHandler(file_handler)
        logging.info(f"File logging initialized. Level: {logging.getLevelName(log_level)}, Log File: {log_file_path}")
    except Exception as e:
        # If file logging fails, fallback to console for critical errors
        logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.error(f"CRITICAL: Failed to configure file logging: {e}. Logging only critical errors to console.")
        log_file_path = "Error - Check Console" # Indicate failure

# --- GraphQL Query Builder --- (No changes needed here, still fetches necessary data)
def build_graphql_query(
    date_from_str: str,
    date_to_str: str,
    types: list[str] | None = None,
    locations: list[str] | None = None,
    limit: int = PAGE_LIMIT,
    offset: int = 0
):
    """
    Builds the GraphQL query string and variables dictionary for fetching races with markets,
    supporting pagination. Fetches required fields for filtering and opportunity identification.
    """
    query_name = "GetRacesWithMarketsPaginated" # Keep name descriptive
    variable_definitions = [ "$dateFrom: String!", "$dateTo: String!", "$limit: Int!", "$offset: Int!" ]
    arguments = [ "dateFrom: $dateFrom", "dateTo: $dateTo", "limit: $limit", "offset: $offset" ]
    variables = { "dateFrom": date_from_str, "dateTo": date_to_str, "limit": limit, "offset": offset }

    if types:
        variable_definitions.append("$types: [RaceType!]")
        arguments.append("types: $types")
        variables["types"] = types
    if locations:
        variable_definitions.append("$locations: [String!]")
        arguments.append("locations: $locations")
        variables["locations"] = locations

    core_fields = """
        id
        meeting { id location track type date }
        name number status startTime
    """
    # Request ALL available bookmaker markets and Betfair markets (including LAY)
    # No need to filter bookmakers here, we do it client-side against TARGET_BOOKMAKERS_STR
    runner_fields_content = """
            id name number scratchedTime
            bookmakerMarkets { id bookmaker fixedWin { price lastUpdated } } # Added lastUpdated for potential debugging
            betfairMarkets {
                id marketName totalMatched
                back { price size } # Keep back price
                lay { price size lastUpdated }  # Need lay price, added lastUpdated
            }
    """
    runner_block = f""" runners {{ {runner_fields_content} }} """
    query_string = f"""
        query {query_name}({', '.join(variable_definitions)}) {{
            races({', '.join(arguments)}) {{ {core_fields} {runner_block} }}
        }}"""

    # Log the query build details only if DEBUG is enabled
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(f"Built GraphQL Query for offset {offset}:\n{query_string}")
        logging.debug(f"Built GraphQL Variables for offset {offset}:\n{json.dumps(variables, indent=2)}")
    return query_string, variables

# --- Betfair Price Extractor --- (No changes needed, still uses LAY price)
def get_betfair_lay_price(runner_data):
    """Extracts the best available Betfair LAY price (pink column) for the Win market."""
    if not runner_data or 'betfairMarkets' not in runner_data or not isinstance(runner_data['betfairMarkets'], list):
        return None

    win_market_data = None
    best_lay_price = None

    # Prioritize explicitly named 'Win' markets that aren't place markets
    for market_data in runner_data['betfairMarkets']:
        if not market_data or not isinstance(market_data, dict): continue

        market_name = market_data.get('marketName', '').lower()
        is_win_market = ("win" in market_name and
                         "place" not in market_name and
                         " to be placed" not in market_name) # More robust check

        if is_win_market:
            lay_prices = market_data.get('lay')
            if isinstance(lay_prices, list) and len(lay_prices) > 0:
                lay_price_info = lay_prices[0] # Best lay is first
                if lay_price_info and isinstance(lay_price_info, dict):
                    try:
                        price_str = lay_price_info.get('price')
                        if price_str is not None and price_str != '':
                           price = float(price_str)
                           if price > 0:
                               # Found a potential explicit win market lay price
                               best_lay_price = price
                               logging.debug(f"Found explicit win market LAY price {best_lay_price} in '{market_data.get('marketName')}' for {runner_data.get('name', 'N/A')}")
                               break # Use the first explicit win market found
                    except (ValueError, TypeError) as e:
                        logging.warning(f"Error parsing LAY price from explicit win market '{market_data.get('marketName')}': {price_str}, Error: {e}")

    # If no explicit 'Win' market LAY price found after checking all, return None
    if best_lay_price is None:
        logging.debug(f"No valid Betfair LAY price found in any explicit 'Win' market for runner {runner_data.get('name', 'N/A')}")
        return None

    return best_lay_price


# --- GraphQL Execution Function with Backoff --- (No changes needed here)
@backoff.on_exception(backoff.expo,
                      (requests.exceptions.RequestException, ValueError), # Include ValueError for GraphQL errors raised
                      max_tries=5,
                      max_time=60, # Add a max time limit for retries
                      logger=logging.getLogger(), # Use the configured logger
                      backoff_log_level=logging.WARNING, # Log backoff attempts as warnings
                      giveup_log_level=logging.ERROR, # Log giving up as error
                      on_giveup=lambda details: logging.error(f"GraphQL query failed after {details['tries']} tries over {details['elapsed']:.1f}s: {details.get('exception')}"),
                      giveup=lambda e: (
                          # Give up immediately on authentication errors
                          isinstance(e, ValueError) and getattr(e, 'args', [None])[0] is not None and
                          isinstance(e.args[0], dict) and "GraphQL errors" in e.args[0] and
                          any('Authentication failed.' in str(err.get('message', '')) for err in e.args[0].get('GraphQL errors', []) if isinstance(err, dict))
                      ) or (
                          # Give up on client-side errors (4xx) except 429 (rate limiting)
                          isinstance(e, requests.exceptions.HTTPError) and 400 <= e.response.status_code < 500 and e.response.status_code != 429
                      ),
                     )
def execute_graphql_query(query, variables, api_key):
    """Executes a GraphQL query using requests, with retry logic integrated with logging."""
    headers = { "Content-Type": "application/json", "X-API-KEY": api_key }
    payload = { "query": query, "variables": variables }
    logging.debug(f"Executing GraphQL query (Offset: {variables.get('offset', 'N/A')})...")
    response = requests.post(GRAPHQL_ENDPOINT, headers=headers, data=json.dumps(payload), timeout=20) # Add timeout
    response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
    result = response.json()
    if 'errors' in result:
        # Log the specific errors encountered
        logging.error(f"GraphQL errors received for offset {variables.get('offset', 'N/A')}: {json.dumps(result['errors'], indent=2)}")
        # Raise a ValueError that backoff can potentially handle or give up on
        raise ValueError({"message": f"GraphQL errors encountered", "GraphQL errors": result['errors']})
    if 'data' not in result:
         logging.error(f"GraphQL response missing 'data' field for offset {variables.get('offset', 'N/A')}: {result}")
         raise ValueError(f"GraphQL response missing 'data' field") # Should trigger retry
    logging.debug(f"GraphQL query successful for offset {variables.get('offset', 'N/A')}.")
    return result['data']

# --- Main Opportunity Finder Logic (Refined) ---
def check_for_opportunities(test_mode=False):
    """
    Fetches ALL relevant races via GraphQL, filters, identifies opportunities based on the
    PERSISTENT reported set, and PRINTS new opportunities to console.
    Returns the count of NEW opportunities found in this cycle.
    """
    global PERSISTENT_REPORTED_OPPORTUNITIES # Access the persistent global set

    if not API_KEY:
        logging.error("BETWATCH_API_KEY not found. Cannot proceed.")
        print("ERROR: BETWATCH_API_KEY not found in environment variables or .env file. Exiting.", file=sys.stderr)
        sys.exit(1)

    if test_mode: logging.info("Running in Test Mode.") # Log file only

    all_fetched_races = []
    current_offset = 0
    page_num = 1
    fetch_successful = True
    cycle_start_time = time.monotonic() # For timing the fetch/process cycle

    try:
        today = datetime.date.today()
        date_str = today.strftime('%Y-%m-%d')
        logging.info(f"Starting fetch for {date_str} ({','.join(TARGET_RACE_TYPES_STR)} in {','.join(TARGET_LOCATIONS)})")

        # --- Pagination Loop ---
        while True:
            logging.debug(f"Fetching page {page_num} (offset {current_offset})...")
            query_string, variables = build_graphql_query(date_from_str=date_str, date_to_str=date_str, types=TARGET_RACE_TYPES_STR, locations=TARGET_LOCATIONS, limit=PAGE_LIMIT, offset=current_offset)
            try:
                 data = execute_graphql_query(query_string, variables, API_KEY)
            except Exception as e:
                 logging.error(f"Failed to fetch page {page_num} (offset {current_offset}): {e}. Stopping pagination for this cycle.")
                 fetch_successful = False
                 break
            races_in_batch = data.get('races', [])
            num_races_in_batch = len(races_in_batch) if races_in_batch else 0
            logging.debug(f"Fetched {num_races_in_batch} races in page {page_num}.")
            if races_in_batch: all_fetched_races.extend(races_in_batch)
            if num_races_in_batch < PAGE_LIMIT:
                logging.debug("Last page reached.")
                break
            page_num += 1
            current_offset += PAGE_LIMIT
            # Add a small delay between paginated requests to be polite to the API
            time.sleep(0.3) # 300ms delay
        # --- End Pagination Loop ---

        if not fetch_successful:
             logging.warning("Aborted processing this cycle due to errors during race fetching.")
             return 0

        logging.info(f"Total races fetched: {len(all_fetched_races)}. Processing filters...")

        # --- Apply client-side filters ---
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        new_opportunities_found_count = 0
        races_in_time_window = []
        # Statuses to consider (Open for betting, Suspended might still have valid prices briefly)
        STATUSES_TO_PROCESS = ["Open", "Suspended"]

        for race_data in all_fetched_races:
            race_id_for_log = race_data.get('id', 'N/A')
            race_status = race_data.get('status')

            # 1. Filter by Status
            if race_status not in STATUSES_TO_PROCESS:
                 # logging.debug(f"Race {race_id_for_log} skipped (status: '{race_status}')")
                 continue

            # 2. Parse Start Time
            start_time_utc = None
            startTime_str = race_data.get('startTime')
            if startTime_str:
                try:
                    start_time_utc = datetime.datetime.fromisoformat(startTime_str.replace('Z', '+00:00'))
                    if start_time_utc.tzinfo is None: start_time_utc = pytz.utc.localize(start_time_utc)
                    else: start_time_utc = start_time_utc.astimezone(pytz.utc)
                except (ValueError, TypeError) as e:
                    logging.warning(f"Could not parse startTime '{startTime_str}' for race {race_id_for_log}: {e}. Skipping.")
                    continue
            else:
                 logging.warning(f"Race {race_id_for_log} missing startTime. Skipping.")
                 continue

            # 3. Filter out past races (allow a small buffer, e.g., 1 min, in case of slight clock differences or API lag)
            if start_time_utc <= (now_utc - datetime.timedelta(minutes=1)):
                # logging.debug(f"Race {race_id_for_log} skipped (already started/past).")
                continue

            # 4. Calculate Time to Jump and Filter by Window
            time_to_jump = start_time_utc - now_utc
            minutes_to_jump = time_to_jump.total_seconds() / 60

            if MIN_TIME_TO_JUMP <= minutes_to_jump <= MAX_TIME_TO_JUMP:
                logging.debug(f"Race {race_id_for_log} is within time window ({minutes_to_jump:.1f} mins). Adding for processing.")
                # Store needed info for processing stage
                races_in_time_window.append({
                    "data": race_data,
                    "start_time_utc": start_time_utc,
                    "minutes_to_jump": minutes_to_jump,
                    "time_to_jump": time_to_jump
                })
            # else: # Log if needed for debugging
            #    logging.debug(f"Race {race_id_for_log} skipped (time to jump {minutes_to_jump:.1f} mins is outside {MIN_TIME_TO_JUMP}-{MAX_TIME_TO_JUMP} window).")

        logging.info(f"Found {len(races_in_time_window)} races in the {MIN_TIME_TO_JUMP}-{MAX_TIME_TO_JUMP} min window. Checking runners...")

        # --- Process races within the time window ---
        for race_info in races_in_time_window:
            race_data = race_info["data"]
            start_time_utc = race_info["start_time_utc"]
            minutes_to_jump = race_info["minutes_to_jump"]
            time_to_jump = race_info["time_to_jump"]

            race_id = race_data.get('id')
            logging.debug(f"Processing race {race_id} ({race_data.get('meeting',{}).get('track')})...")
            runners_data = race_data.get('runners', [])
            if not runners_data: continue

            for runner_data in runners_data:
                runner_id = runner_data.get('id')
                runner_name = runner_data.get('name', 'N/A')
                runner_number = runner_data.get('number', 'N/A')

                if not runner_data or not runner_id or runner_name == 'N/A': continue
                if runner_data.get('scratchedTime') is not None: continue # Skip scratched

                # Get Betfair LAY price
                betfair_lay_price = get_betfair_lay_price(runner_data)
                if betfair_lay_price is None:
                    # logging.debug(f"No valid Betfair LAY price for runner {runner_number}.{runner_name} in race {race_id}")
                    continue

                bookmaker_markets_data = runner_data.get('bookmakerMarkets', [])
                if not bookmaker_markets_data: continue

                for market_data in bookmaker_markets_data:
                    if not market_data: continue
                    bookmaker_name = market_data.get('bookmaker')
                    if bookmaker_name not in TARGET_BOOKMAKERS_STR: continue # Only check target bookies

                    fixed_win_data = market_data.get('fixedWin')
                    if fixed_win_data and fixed_win_data.get('price') is not None:
                        bookmaker_price = None # Reset before try block
                        price_str = str(fixed_win_data['price']) # Convert upfront
                        try:
                            if price_str and price_str.lower() != 'none':
                                bookmaker_price = float(price_str)
                                if bookmaker_price <= 0: bookmaker_price = None # Ignore invalid prices

                        except (ValueError, TypeError) as e:
                            logging.warning(f"Could not parse bookmaker price for {bookmaker_name} runner {runner_number}.{runner_name} ({runner_id}): Price='{price_str}'. Error: {e}")
                            continue # Skip this market price if parsing fails

                        if bookmaker_price is not None:
                            # --- Core Opportunity Check ---
                            if bookmaker_price >= betfair_lay_price:
                                opportunity_key = (race_id, runner_id, bookmaker_name)

                                # *** Check against PERSISTENT set ***
                                if opportunity_key not in PERSISTENT_REPORTED_OPPORTUNITIES:
                                    PERSISTENT_REPORTED_OPPORTUNITIES.add(opportunity_key) # Add BEFORE printing
                                    new_opportunities_found_count += 1
                                    logging.info(f"NEW Opportunity Found: Race={race_id}, Runner={runner_id}, Bookie={bookmaker_name}, Price={bookmaker_price:.2f}, BF_Lay={betfair_lay_price:.2f}")

                                    # --- CONSOLE OUTPUT for the client ---
                                    print("\n-------------------------------------")
                                    print(">>> Opportunity Found! <<<")
                                    meeting_data = race_data.get('meeting', {})
                                    track = meeting_data.get('track', 'N/A')
                                    location = meeting_data.get('location', 'N/A')
                                    race_number = race_data.get('number', 'N/A')
                                    race_name = race_data.get('name', 'N/A')
                                    try:
                                        local_tz = datetime.datetime.now().astimezone().tzinfo
                                        local_start_time = start_time_utc.astimezone(local_tz)
                                        start_time_str = local_start_time.strftime('%H:%M %Z')
                                    except Exception: start_time_str = start_time_utc.strftime('%H:%M UTC')

                                    print(f"  Race:      {track} (R{race_number}) - {race_name}")
                                    print(f"  Meeting:   {location} ({meeting_data.get('type', 'N/A')})")
                                    print(f"  Start Time:{start_time_str}")
                                    print(f"  Runner:    {runner_number}. {runner_name} ({runner_id})")
                                    print(f"  Bookmaker: {bookmaker_name} @ {bookmaker_price:.2f}")
                                    print(f"  Betfair:   LAY @ {betfair_lay_price:.2f}")
                                    time_left_str = f"{int(minutes_to_jump)}m {int(time_to_jump.total_seconds() % 60)}s"
                                    print(f"  Time Left: {time_left_str}")

                                    place_bet(track,race_number,runner_number,bookmaker_name,betfair_lay_price,bookmaker_price)
                                    
                                    try: # Construct Betwatch URL
                                        base_url = "https://www.betwatch.com/app/racing/"
                                        race_date_for_url = start_time_utc.strftime('%Y-%m-%d')
                                        race_type = meeting_data.get('type', 'Unknown'); type_code_map = {'Greyhound': 'G', 'Harness': 'H', 'Thoroughbred': 'R'}
                                        type_code = type_code_map.get(race_type, 'R'); encoded_track = urllib.parse.quote(track)
                                        betwatch_url = f"{base_url}{race_date_for_url}/{type_code}/{encoded_track}/{race_number}"
                                        print(f"  Link:      {betwatch_url}")
                                    except Exception as url_err: logging.warning(f"Could not construct Betwatch URL for race {race_id}: {url_err}"); print("  Link:      Error constructing URL")
                                    print("-------------------------------------")
                                    sys.stdout.flush() # Ensure it prints immediately
                                    # --- END CONSOLE OUTPUT ---
                                # else: # Opportunity already reported, log for debugging if needed
                                #    logging.debug(f"Opportunity already reported: Race={race_id}, Runner={runner_id}, Bookie={bookmaker_name}")


        # Log summary of findings for this cycle (to log file only)
        cycle_duration = time.monotonic() - cycle_start_time
        logging.info(f"Check cycle complete in {cycle_duration:.2f}s. Found {new_opportunities_found_count} NEW opportunities.")
        return new_opportunities_found_count # Return count of new finds

    except Exception as e:
        logging.exception(f"An unexpected error occurred in check_for_opportunities: {e}")
        return 0 # Return 0 on error


# --- Script Entry Point & Live Loop ---
if __name__ == "_main_":
    parser = argparse.ArgumentParser(description="Betwatch Opportunity Finder (GraphQL - Fast Check). Logs details to file, prints NEW opportunities to console.")
    parser.add_argument("--test", action="store_true", help="Run in test mode (informational logging).")
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set the logging level for the log FILE.")
    parser.add_argument("--interval", type=float, default=DEFAULT_CHECK_INTERVAL_SECONDS, help=f"Check interval in seconds (can be float, e.g., 2.5) (default: {DEFAULT_CHECK_INTERVAL_SECONDS}).")

    args = parser.parse_args()

    if args.interval <= 1.0:
        print("WARNING: Check interval set to <= 1.0 seconds. This is very frequent and may risk API rate limits.", file=sys.stderr)
    elif args.interval <= 0:
         print("ERROR: Check interval must be positive.", file=sys.stderr)
         sys.exit(1)

    # --- Setup Logging (File Only) ---
    setup_logging(args.log)

    # --- Initial Console Output ---
    print("--- Betwatch Opportunity Finder (Fast Check Version) ---")
    print(f"Initialization complete. Starting continuous checks...")
    if isinstance(log_file_path, pathlib.Path):
         print(f"Logging details to: {log_file_path} (Level: {args.log.upper()})")
    else:
         print(f"WARNING: File logging setup failed. Logging may be incomplete. Status: {log_file_path}")

    print(f"Checking every {args.interval} seconds.")
    print(f"Target Bookmakers: {', '.join(TARGET_BOOKMAKERS_STR)}")
    print(f"Race Types: {', '.join(TARGET_RACE_TYPES_STR)}")
    print(f"Locations: {', '.join(TARGET_LOCATIONS)}")
    print(f"Time Window: {MIN_TIME_TO_JUMP}-{MAX_TIME_TO_JUMP} minutes before jump.")
    print(f"Condition: Bookmaker Fixed Win >= Betfair LAY price.")
    print(">>> Will only print each unique opportunity (Race+Runner+Bookmaker) ONCE per script run. <<<")
    print("Press Ctrl+C to stop.")
    print("--------------------------------------------------------")
    # --- End Initial Console Output ---

    # --- Live Loop ---
    try:
        while True:
            loop_start_time = time.monotonic()
            logging.info("--- Starting new opportunity check cycle ---")

            new_opps_found = 0
            try:
                # Find opportunities (prints to console if new ones found, logs internally)
                new_opps_found = check_for_opportunities(test_mode=args.test)

                # Print a dot to console ONLY if no new opportunities were found in this cycle
                if new_opps_found == 0:
                     print(".", end="", flush=True) # Use dot for quiet cycle

            except Exception as cycle_err:
                 # Log critical errors during the main check function call itself
                 logging.exception(f"Critical error during check_for_opportunities execution: {cycle_err}")
                 # Print 'X' to console to indicate an error occurred in the cycle
                 print("X", end="", flush=True) # Use X for error cycle

            # Calculate time spent and sleep accordingly
            loop_end_time = time.monotonic()
            time_spent = loop_end_time - loop_start_time
            sleep_time = max(0, args.interval - time_spent) # Ensure sleep time is non-negative

            logging.debug(f"Cycle took {time_spent:.2f}s. Sleeping for {sleep_time:.2f}s.")
            if sleep_time > 0:
                time.sleep(sleep_time)
            # If time_spent > args.interval, it will immediately start the next cycle

    except KeyboardInterrupt:
        print("\n--------------------------------------------------------")
        logging.info("Script interrupted by user (Ctrl+C). Exiting.")
        print("Script stopped by user. Exiting.")
        print("--------------------------------------------------------")
    except Exception as main_loop_err:
        logging.exception("FATAL: An unexpected error occurred in the main loop. Exiting.")
        print(f"\nFATAL ERROR in main loop: {main_loop_err}. Check log file for details. Exiting.", file=sys.stderr)
    finally:
        logging.info("--- Betwatch Opportunity Finder Shutting Down ---")