import requests
import json # For potential future use if parsing more complex JSON
# You'll also need datetime and pytz if you implement start_time correctly later
import datetime
import pytz

# === Constants (from your phase2.py) ===
BASE_URL = 'https://betmatic.app/api'
LOGIN_ENDPOINT = '/account/login/'
REFRESH_ENDPOINT = '/account/refresh_token/'
NOTIFICATION_CREATE_ENDPOINT = '/notification/create/' # Added for clarity

# === Constants for Betmatic API lookups (will be needed for robust implementation) ===
COMPETITION_NAMECODES_ENDPOINT = '/competition/namecodes/'
BOOKIE_NAMES_ENDPOINT = '/bookie/names/'
BET_MARKETS_ENDPOINT = '/bet/markets/' # To get full market names
BET_CODES_ENDPOINT = '/bet/codes/'     # To get valid race codes


HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

# === Function: Login and Get Token (from your phase2.py) ===
def login_to_betmatic(email, password):
    url = BASE_URL + LOGIN_ENDPOINT
    payload = {
        'email': email,
        'password': password
    }
    try:
        response = requests.post(url, json=payload, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        token = data.get('token')
        if not token:
            raise ValueError("Login succeeded, but no token returned.")
        print(f"✅ Logged in successfully. Token retrieved.") # Token itself is sensitive, avoid printing in prod
        return token
    except requests.exceptions.RequestException as e:
        print(f"❌ Login Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                print(f"Response content: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response content: {e.response.text}")
        return None

# === Function: Refresh Token (from your phase2.py - corrected payload) ===
def refresh_betmatic_token(current_token):
    url = BASE_URL + REFRESH_ENDPOINT
    headers_with_auth = {
        **HEADERS,
        'Authorization': f'Token {current_token}'
    }
    # The payload for refresh token just needs the current token
    payload = {
        'token': current_token
    }
    try:
        response = requests.post(url, json=payload, headers=headers_with_auth)
        response.raise_for_status()
        data = response.json()
        new_token = data.get('token')
        if not new_token:
            raise ValueError("Refresh succeeded, but no new token returned.")
        print(f"🔁 Token refreshed successfully.") # Token itself is sensitive
        return new_token
    except requests.exceptions.RequestException as e:
        print(f"❌ Refresh Token Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                print(f"Response content: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response content: {e.response.text}")
        return None

# --- Helper functions for Betmatic API Lookups (Essential for robust implementation) ---
# These would ideally be more fleshed out with error handling and caching

def get_betmatic_competition_details(auth_token, location_name_from_phase1, race_type_from_phase1, race_number_from_phase1):
    """
    Fetches competition details from Betmatic to get the exact competition name,
    event_number, and start_time.
    THIS IS A SIMPLIFIED PLACEHOLDER. A real version needs to match carefully.
    """
    url = BASE_URL + COMPETITION_NAMECODES_ENDPOINT
    headers_with_auth = {**HEADERS, 'Authorization': f'Token {auth_token}'}
    try:
        response = requests.get(url, headers=headers_with_auth)
        response.raise_for_status()
        competitions = response.json()

        # print(f"DEBUG: All competitions from Betmatic API: {json.dumps(competitions, indent=2)}") # For debugging

        for comp in competitions:
            # Phase 1 gives Location (e.g., "NSW"), Betmatic might have "RANDWICK (NSW)"
            # Phase 1 gives Race Type (e.g., "Greyhound"), Betmatic has "code" (e.g. "Greyhounds")
            # Phase 1 gives Race No, Betmatic has "event_number"
            # This matching logic needs to be robust. For now, a simple check:
            betmatic_comp_name = comp.get('name', '').upper()
            betmatic_comp_code = comp.get('code', '').upper() # e.g. "GREYHOUNDS"
            betmatic_event_num = comp.get('event_number')

            # Normalize race type from phase1 if needed
            normalized_phase1_race_type = race_type_from_phase1.upper()
            if normalized_phase1_race_type == "GREYHOUND": # Betmatic uses plural
                 normalized_phase1_race_type = "GREYHOUNDS"


            # This is a very basic match. Real-world might need fuzzy matching or more precise mapping.
            # Especially since Betwatch location is "NSW", Betmatic competition is "TRACK_NAME (NSW)"
            if (location_name_from_phase1.upper() in betmatic_comp_name and
                normalized_phase1_race_type == betmatic_comp_code and
                str(betmatic_event_num) == str(race_number_from_phase1)): # Compare as strings for safety
                print(f"✅ Matched Betmatic Competition: {comp['name']} for R{comp['event_number']}")
                return {
                    "competition_name": comp['name'],
                    "event_number": comp['event_number'],
                    "start_time_iso": comp.get('startTime') # ISO 8601 format
                }
        print(f"⚠️ Could not find matching Betmatic competition for {location_name_from_phase1}, {race_type_from_phase1}, R{race_number_from_phase1}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching Betmatic competition details: {e}")
        return None

def get_betmatic_bookie_id(auth_token, bookmaker_name_from_phase1):
    """
    Fetches the bookie ID from Betmatic based on the bookmaker name.
    """
    url = BASE_URL + BOOKIE_NAMES_ENDPOINT
    headers_with_auth = {**HEADERS, 'Authorization': f'Token {auth_token}'}
    try:
        response = requests.get(url, headers=headers_with_auth)
        response.raise_for_status()
        bookies = response.json() # This is likely a list of dicts
        # print(f"DEBUG: All bookies from Betmatic API: {json.dumps(bookies, indent=2)}") # For debugging

        for bookie in bookies: # Assuming `bookies` is a list of objects like {"id": 1, "title": "Sportsbet", ...}
            if bookie.get('title', '').lower() == bookmaker_name_from_phase1.lower():
                print(f"✅ Found Betmatic Bookie ID: {bookie['id']} for {bookmaker_name_from_phase1}")
                return str(bookie['id']) # Betmatic API for notification wants string IDs
        print(f"⚠️ Could not find Betmatic Bookie ID for: {bookmaker_name_from_phase1}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching Betmatic bookie ID: {e}")
        return None

# === Function: Create Betmatic Notification ===
def create_betmatic_notification(auth_token, opportunity_data):
    """
    Creates a new notification on Betmatic based on the opportunity data from Phase 1.

    Args:
        auth_token (str): The active Betmatic authentication token.
        opportunity_data (dict): A dictionary containing the parsed data from Phase 1.
                                 Expected keys: 'Location', 'RaceType', 'RaceNo',
                                                'RunnerNo', 'BookmakerName', 'BookmakerPrice'
                                                (and 'TrackName' is also useful)
    """
    print(f"\nℹ️ Attempting to create Betmatic notification for: {opportunity_data.get('TrackName', 'N/A')} R{opportunity_data.get('RaceNo', 'N/A')}")

    # --- 1. Enrich data using Betmatic API lookups ---
    # Get precise Betmatic competition name, event_number, and start_time
    competition_details = get_betmatic_competition_details(
        auth_token,
        opportunity_data.get('Location'),
        opportunity_data.get('RaceType'),
        opportunity_data.get('RaceNo')
    )
    if not competition_details:
        print("❌ Failed to get Betmatic competition details. Aborting notification.")
        return None

    betmatic_competition_name = competition_details["competition_name"]
    betmatic_event_number = competition_details["event_number"]
    betmatic_start_time_iso = competition_details["start_time_iso"] # Optional for payload

    # Get Betmatic bookie ID
    # For simplicity, assuming single bookmaker. If multiple, this needs a loop and '&' join.
    betmatic_bookie_id = get_betmatic_bookie_id(auth_token, opportunity_data.get('BookmakerName'))
    if not betmatic_bookie_id:
        print(f"❌ Failed to get Betmatic Bookie ID for {opportunity_data.get('BookmakerName')}. Aborting notification.")
        return None

    # --- 2. Construct the Notification Payload ---
    # Directly from your requirements:
    payload = {
        "type": "Fixed Wager", # As per your requirement "type - fixed win" (Fixed Wager is a common term)
        "competition": betmatic_competition_name, # From Betmatic API lookup
        "code": opportunity_data.get('RaceType'), # e.g., "Greyhounds" or "Harness" (ensure it's one of the Betmatic accepted values)
        "event_number": betmatic_event_number,    # From Betmatic API lookup (integer)
        "market": "Fixed Win",                    # As per your requirement
        "selection": str(opportunity_data.get('RunnerNo')), # Runner number as a string
        "sports": "RACING",                       # As per your requirement
        "bookies": betmatic_bookie_id,            # Single bookie ID for now

        # --- Optional fields based on your comments (placeholders or to be decided) ---
        # "start_time": betmatic_start_time_iso, # Uncomment if you want to use it.
                                                 # Ensures targeting the exact race if multiple meets exist.
        # "stake": 10,                           # Placeholder: Value to be decided by you
        # "target_bot": "YOUR_TARGET_BOT_ID_HERE", # Placeholder: Value to be decided by you

        # --- Fields from Betwatch opportunity that might be useful ---
        "odds": float(opportunity_data.get('BookmakerPrice')), # Minimum odds from Betwatch
        "check_odds": True, # Recommended if you provide 'odds'

        # --- Other common default values (adjust as needed) ---
        "is_scheduled": False,
        "auto_trigger": False, # Triggers immediately if not scheduled
    }

    # Validate 'code' field if necessary
    valid_codes = ["Galloping", "Harness", "Greyhounds"]
    if payload["code"] not in valid_codes:
        # Attempt to normalize (e.g., "Greyhound" from phase1 to "Greyhounds" for Betmatic)
        if payload["code"] == "Greyhound":
            payload["code"] = "Greyhounds"
        elif payload["code"] == "Thoroughbred": # Common synonym for Galloping
            payload["code"] = "Galloping"
        # Add more normalization if needed

        if payload["code"] not in valid_codes:
            print(f"❌ Invalid 'code' for Betmatic: {payload['code']}. Must be one of {valid_codes}. Aborting.")
            return None


    print(f"ℹ️ Notification Payload for Betmatic:\n{json.dumps(payload, indent=2)}")

    # --- 3. Send the API Request ---
    url = BASE_URL + NOTIFICATION_CREATE_ENDPOINT
    headers_with_auth = {
        **HEADERS,
        'Authorization': f'Token {auth_token}'
    }

    try:
        response = requests.post(url, json=payload, headers=headers_with_auth)
        response.raise_for_status()
        print(f"✅ Betmatic Notification created successfully for {payload['competition']} R{payload['event_number']}!")
        # You might want to return response.json() if there's useful data
        return response.json() # Or True
    except requests.exceptions.RequestException as e:
        print(f"❌ Create Betmatic Notification Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print(f"Response status: {e.response.status_code}")
                print(f"Response content: {json.dumps(error_details, indent=2)}")
            except json.JSONDecodeError:
                print(f"Response status: {e.response.status_code}")
                print(f"Response content: {e.response.text}")
        return None


# === Placeholder for Phase 1 Output Parsing ===
def parse_phase1_output_for_betmatic(phase1_console_output_string):
    """
    Parses the multi-line string output from Phase 1 to extract bet details.
    This is a simplified parser and might need to be more robust.
    It now expects the dictionary from "Placing bet with parameters:"
    """
    data = {}
    try:
        # Look for the line "Placing bet with parameters: {dictionary_of_bet_parameters}"
        params_line_prefix = "Placing bet with parameters: "
        for line in phase1_console_output_string.splitlines():
            if line.strip().startswith(params_line_prefix):
                dict_str = line.strip()[len(params_line_prefix):]
                # The string is a Python dict literal, not JSON. ast.literal_eval is safer.
                import ast
                params_dict = ast.literal_eval(dict_str)

                # Mapping from Phase 1's 'place_bet' kwargs to what Betmatic needs
                # Based on phase1.py's `place_bet(track,race_number,runner_number,bookmaker_name,betfair_lay_price,bookmaker_price)`
                data['TrackName'] = params_dict.get('track') # Used for logging/matching
                data['RaceNo'] = params_dict.get('race_number')
                data['RunnerNo'] = params_dict.get('runner_number')
                data['BookmakerName'] = params_dict.get('bookmaker_name')
                data['BookmakerPrice'] = params_dict.get('bookmaker_price') # This is what Betmatic needs for 'odds'
                # We also need Location and RaceType from Betwatch output for Betmatic competition lookup
                # These were not in the 'place_bet' params. We need to extract them from other lines.
                break # Found the parameters line

        if not data.get('TrackName'): # If the dictionary wasn't found or was empty
             print("❌ Could not find 'Placing bet with parameters:' line in Phase 1 output.")
             return None

        # Extract Location and RaceType from other lines (example, needs refinement)
        for line in phase1_console_output_string.splitlines():
            line_strip = line.strip()
            if line_strip.startswith("Meeting:"): # "  Meeting:   {Location} ({Race Type})"
                parts = line_strip.split("Meeting:")[1].strip().split('(')
                data['Location'] = parts[0].strip() # e.g., "ALBION PARK"
                if len(parts) > 1:
                    data['RaceType'] = parts[1].split(')')[0].strip() # e.g., "Greyhounds"
            elif line_strip.startswith("Start Time:"):
                data['StartTime_str_from_phase1'] = line_strip.split("Start Time:")[1].strip()


        # Basic validation
        required_keys = ['TrackName', 'RaceNo', 'RunnerNo', 'BookmakerName', 'BookmakerPrice', 'Location', 'RaceType']
        for key in required_keys:
            if key not in data or not data[key]:
                print(f"❌ Missing crucial key '{key}' after parsing Phase 1 output.")
                return None

        print(f"ℹ️ Parsed data from Phase 1: {data}")
        return data

    except Exception as e:
        print(f"❌ Error parsing Phase 1 output: {e}")
        return None


# === Main Execution (Example Usage) ===
if __name__ == "__main__":
    # Replace with your Betmatic credentials
    betmatic_email = 'jacobsawers1@gmail.com'  # CHANGEME
    betmatic_password = 'Test1234'    # CHANGEME

    # Step 1: Login to Betmatic
    print("--- Attempting Betmatic Login ---")
    auth_token = login_to_betmatic(betmatic_email, betmatic_password)

    if auth_token:
        print("\n--- Simulating Phase 1 Output Processing ---")
        # Example output string from your phase1.py
        # Make sure this matches EXACTLY what phase1.py's `place_bet` call would generate in the printout
        # And include the "Meeting:" line for Location and RaceType
        example_phase1_output = """
-------------------------------------
>>> Opportunity Found! <<<
  Race:      ALBION PARK (R1) - SOME RACE NAME
  Meeting:   QLD (Greyhounds)
  Start Time:14:08 AEST
  Runner:    2. Some Runner Name (runner-id-123)
  Bookmaker: Sportsbet @ 2.50
  Betfair:   LAY @ 2.40
  Time Left: 5m 30s
Placing bet with parameters: {'track': 'ALBION PARK', 'race_number': 1, 'runner_number': '2', 'bookmaker_name': 'Sportsbet', 'betfair_lay_price': 2.4, 'bookmaker_price': 2.5}
  Link:      https://www.betwatch.com/app/racing/2023-10-27/G/ALBION%20PARK/1
-------------------------------------
        """
        # Important: The parsing function now relies heavily on the "Placing bet with parameters:" line.

        opportunity_details = parse_phase1_output_for_betmatic(example_phase1_output)

        if opportunity_details:
            # Step 2: Create a notification using the parsed details
            # Define stake and target_bot_id here or pass them into opportunity_details
            # opportunity_details['stake'] = 5 # Example fixed stake
            # opportunity_details['target_bot_id'] = "your_bot_id" # Example

            create_betmatic_notification(auth_token, opportunity_details)

            # Example with a Harness race (ensure 'code' mapping in create_betmatic_notification handles it)
            print("\n--- Simulating Another Phase 1 Output (Harness) ---")
            example_phase1_harness_output = """
-------------------------------------
>>> Opportunity Found! <<<
  Race:      MENANGLE (R3) - HARNESS RACE NAME
  Meeting:   NSW (Harness)
  Start Time:18:30 AEST
  Runner:    5. Harness Hero (runner-id-456)
  Bookmaker: Tab @ 3.10
  Betfair:   LAY @ 3.00
  Time Left: 10m 0s
Placing bet with parameters: {'track': 'MENANGLE', 'race_number': 3, 'runner_number': '5', 'bookmaker_name': 'Tab', 'betfair_lay_price': 3.0, 'bookmaker_price': 3.1}
  Link:      https://www.betwatch.com/app/racing/2023-10-27/H/MENANGLE/3
-------------------------------------
            """
            opportunity_details_harness = parse_phase1_output_for_betmatic(example_phase1_harness_output)
            if opportunity_details_harness:
                create_betmatic_notification(auth_token, opportunity_details_harness)

        else:
            print("Could not parse opportunity details from Phase 1 output.")
    else:
        print("Could not log in to Betmatic. Aborting.")
