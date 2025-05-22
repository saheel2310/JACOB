import requests
import json  # For working with JSON data
import datetime
import pytz
import ast  # Safely evaluate Python code literals

# === Constants ===
BASE_URL = 'https://betmatic.app/api'
LOGIN_ENDPOINT = '/account/login/'
REFRESH_ENDPOINT = '/account/refresh_token/'
NOTIFICATION_CREATE_ENDPOINT = '/notification/create/'  # Endpoint for creating notifications

# === Constants for Betmatic API lookups ===
COMPETITION_NAMECODES_ENDPOINT = '/competition/namecodes/'  # Endpoint for retrieving competition name codes
BOOKIE_NAMES_ENDPOINT = '/bookie/names/'  # Endpoint for retrieving bookie names
BET_MARKETS_ENDPOINT = '/bet/markets/'  # Endpoint for retrieving bet markets
BET_CODES_ENDPOINT = '/bet/codes/'  # Endpoint for retrieving bet codes

HEADERS = {
    'Content-Type': 'application/json',  # Header indicating JSON content
    'Accept': 'application/json'  # Header indicating JSON acceptance
}

# === Function: Login and Get Token ===
def login_to_betmatic(email, password):
    url = BASE_URL + LOGIN_ENDPOINT  # Construct login URL
    payload = {
        'email': email,  # Email for login
        'password': password  # Password for login
    }
    try:
        response = requests.post(url, json=payload, headers=HEADERS)  # Send POST request for login
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx status codes)
        data = response.json()  # Parse JSON response
        token = data.get('token')  # Extract token from response
        if not token:
            raise ValueError("Login succeeded, but no token returned.")  # Raise error if no token is returned
        print(f"✅ Logged in successfully. Token retrieved.")  # Token itself is sensitive, avoid printing in prod
        return token  # Return the token
    except requests.exceptions.RequestException as e:
        print(f"❌ Login Error: {e}")  # Print login error
        if hasattr(e, 'response') and e.response is not None:
            try:
                print(f"Response content: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response content: {e.response.text}")
        return None  # Return None if login fails

# === Function: Refresh Token ===
def refresh_betmatic_token(current_token):
    url = BASE_URL + REFRESH_ENDPOINT  # Construct refresh URL
    headers_with_auth = {
        **HEADERS,
        'Authorization': f'Token {current_token}'  # Add authorization header with token
    }
    payload = {
        'token': current_token  # Token to refresh
    }
    try:
        response = requests.post(url, json=payload, headers=headers_with_auth)  # Send POST request for token refresh
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx status codes)
        data = response.json()  # Parse JSON response
        new_token = data.get('token')  # Extract new token from response
        if not new_token:
            raise ValueError("Refresh succeeded, but no new token returned.")  # Raise error if no token is returned
        print(f"🔁 Token refreshed successfully.")  # Token itself is sensitive
        return new_token  # Return the new token
    except requests.exceptions.RequestException as e:
        print(f"❌ Refresh Token Error: {e}")  # Print refresh token error
        if hasattr(e, 'response') and e.response is not None:
            try:
                print(f"Response content: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response content: {e.response.text}")
        return None  # Return None if token refresh fails

# --- Helper functions for Betmatic API Lookups ---
def get_betmatic_competition_details(auth_token, location_name_from_phase1, race_type_from_phase1, race_number_from_phase1):
    """
    Fetches competition details from Betmatic to get the exact competition name,
    event_number, and start_time.
    """
    url = BASE_URL + COMPETITION_NAMECODES_ENDPOINT
    headers_with_auth = {**HEADERS, 'Authorization': f'Token {auth_token}'}
    try:
        response = requests.get(url, headers=headers_with_auth)
        response.raise_for_status()
        competitions = response.json()

        print(f"DEBUG: All competitions from Betmatic API: {json.dumps(competitions, indent=2)}")  # For debugging

        for comp in competitions:
            betmatic_comp_name = comp.get('name', '').upper()
            betmatic_comp_code = comp.get('code', '').upper()
            betmatic_event_num = comp.get('event_number')

            normalized_phase1_race_type = race_type_from_phase1.upper()
            if normalized_phase1_race_type == "GREYHOUND":  # Betmatic uses plural
                normalized_phase1_race_type = "GREYHOUNDS"

            # More robust matching:  Check if the competition name *contains* the location.
            # And compare the race type and race number.
            if (location_name_from_phase1.upper() in betmatic_comp_name and
                    normalized_phase1_race_type == betmatic_comp_code and
                    str(betmatic_event_num) == str(race_number_from_phase1)):  # Compare as strings for safety
                print(f"✅ Matched Betmatic Competition: {comp['name']} for R{comp['event_number']}")
                return {
                    "competition_name": comp['name'],
                    "event_number": comp['event_number'],
                    "start_time_iso": comp.get('startTime')  # ISO 8601 format
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
        bookies = response.json()  # This is likely a list of dicts
        # print(f"DEBUG: All bookies from Betmatic API: {json.dumps(bookies, indent=2)}") # For debugging

        for bookie in bookies:  # Assuming `bookies` is a list of objects like {"id": 1, "title": "Sportsbet", ...}
            if bookie.get('title', '').lower() == bookmaker_name_from_phase1.lower():
                print(f"✅ Found Betmatic Bookie ID: {bookie['id']} for {bookmaker_name_from_phase1}")
                return str(bookie['id'])  # Betmatic API for notification wants string IDs
        print(f"⚠️ Could not find Betmatic Bookie ID for: {bookmaker_name_from_phase1}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching Betmatic bookie ID: {e}")
        return None

# === Function: Create Betmatic Notification ===
def create_betmatic_notification(auth_token, opportunity_data, notification_type="Fixed Profit", is_testing=True):
    """
    Creates a new notification on Betmatic based on the opportunity data from Phase 1.
    """

    print(f"\nℹ️ Attempting to create Betmatic notification ({notification_type}) for: {opportunity_data.get('TrackName', 'N/A')} R{opportunity_data.get('RaceNo', 'N/A')}")

    # --- 1. Enrich data using Betmatic API lookups ---
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
    betmatic_start_time_iso = competition_details["start_time_iso"]  # Optional for payload

    # Get Betmatic bookie ID
    bookmaker_name = opportunity_data.get('BookmakerName')
    betmatic_bookie_id = get_betmatic_bookie_id(auth_token, bookmaker_name)
    if not betmatic_bookie_id:
        print(f"❌ Failed to get Betmatic Bookie ID for {bookmaker_name}. Aborting notification.")
        return None

    # --- 2. Construct the Notification Payload ---
    payload = {
        "type": notification_type,  # "Fixed Win" or "Fixed Profit"
        "competition": betmatic_competition_name,  # From Betmatic API lookup
        "code": opportunity_data.get('RaceType'),  # e.g., "Greyhounds" or "eHarness"
        "event_number": betmatic_event_number,  # From Betmatic API lookup (integer)
        "market": "Fixed Win",  # As per your requirement
        "selection": str(opportunity_data.get('RunnerNo')),  # Runner number as a string
        "sports": "RACING",  # As per your requirement
        "bookies": betmatic_bookie_id,  # Single bookie ID for now

        "check_odds": True,  # Recommended if you provide 'odds'
        "odds": float(opportunity_data.get('BookmakerPrice')),  # Minimum odds from Betwatch

        "is_scheduled": False,  # Immediate Trigger
        "auto_trigger": False,  # Immediate Trigger
    }

    # Wager Amount
    if notification_type == "Fixed Profit":
        payload["target_profit"] = 1.0 if is_testing else 500.0
        if "stake" in payload:
            del payload["stake"]
    else:  # Fixed Win
        payload["stake"] = 1.0 if is_testing else 500.0
        if "target_profit" in payload:
            del payload["target_profit"]

    # Code Validation and Mapping
    valid_codes = ["Greyhounds", "Harness"] # Updated valid codes

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
        return response.json()  # Or True
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
    It now expects the dictionary from "Placing bet with parameters:"
    """
    data = {}
    try:
        params_line_prefix = "Placing bet with parameters: "
        for line in phase1_console_output_string.splitlines():
            try:
                if line.strip().startswith(params_line_prefix):
                    dict_str = line.strip()[len(params_line_prefix):]
                    params_dict = ast.literal_eval(dict_str)

                    data['TrackName'] = params_dict.get('track')  # Used for logging/matching
                    data['RaceNo'] = params_dict.get('race_number')
                    data['RunnerNo'] = params_dict.get('runner_number')
                    data['BookmakerName'] = params_dict.get('bookmaker_name')
                    data['BookmakerPrice'] = params_dict.get('bookmaker_price')  # This is what Betmatic needs for 'odds'
                    break  # Found the parameters line
            except (ValueError, SyntaxError) as e:
                print(f"❌ Error parsing parameters line: {e}")
                continue # Continue parsing lines since there might be other information to extract

        if not data.get('TrackName'):  # If the dictionary wasn't found or was empty
            print("❌ Could not find 'Placing bet with parameters:' line in Phase 1 output.")
            return None

        # Extract Location and RaceType from other lines (example, needs refinement)
        for line in phase1_console_output_string.splitlines():
            try:
                line_strip = line.strip()
                if line_strip.startswith("Meeting:"):  # "  Meeting:   {Location} ({Race Type})"
                    parts = line_strip.split("Meeting:")[1].strip().split('(')
                    data['Location'] = parts[0].strip()  # e.g., "ALBION PARK"
                    if len(parts) > 1:
                        data['RaceType'] = parts[1].split(')')[0].strip()  # e.g., "Greyhounds"
                elif line_strip.startswith("Start Time:"):
                    data['StartTime_str_from_phase1'] = line_strip.split("Start Time:")[1].strip()
            except Exception as e:
                print(f"❌ Error parsing line for meeting or start time: {e}")
                continue

        # Basic validation
        required_keys = ['TrackName', 'RaceNo', 'RunnerNo', 'BookmakerName', 'BookmakerPrice', 'Location', 'RaceType']
        for key in required_keys:
            if key not in data or not data[key]:
                print(f"❌ Missing crucial key '{key}' after parsing Phase 1 output.")
                return None

        print(f"DEBUG: Parsed Data: Location={data['Location']}, RaceType={data['RaceType']}, RaceNo={data['RaceNo']}")  # Debug: Print extracted Phase 1 data

        #Filter out Galloping from function itself

        if data['RaceType'] == "Galloping":
            #Remove galloping details
            print("ℹ️ Galloping race found, skipping this race.")
            data['TrackName'] = None
            data['RaceNo'] = None
            data['RunnerNo'] = None
            data['BookmakerName'] = None
            data['BookmakerPrice'] = None
            data['Location'] = None
            data['RaceType'] = None
            data['StartTime_str_from_phase1'] = None

        print(f"ℹ️ Parsed data from Phase 1: {data}")
        return data

    except Exception as e:
        print(f"❌ General error during parsing: {e}")
        return None

# === Main Execution (Example Usage) ===
if __name__ == "__main__":
    # Replace with your Betmatic credentials
    betmatic_email = 'jacobsawers1@gmail.com'  # CHANGEME
    betmatic_password = 'Test1234'  # CHANGEME

    # Step 1: Login to Betmatic
    print("--- Attempting Betmatic Login ---")
    auth_token = login_to_betmatic(betmatic_email, betmatic_password)

    if auth_token:
        print("\n--- Simulating Phase 1 Output Processing ---")
        # Example output string from your phase1.py
        # Corrected Output

        example_phase1_output = """
-------------------------------------
>>> Opportunity Found! <<<
  Race:      ALBION PARK (R1) - SOME RACE NAME
  Meeting:   ALBION PARK (Greyhounds)
  Start Time:14:08 AEST
  Runner:    2. Some Runner Name (runner-id-123)
  Bookmaker: Sportsbet @ 2.50
  Betfair:   LAY @ 2.40
  Time Left: 5m 30s
Placing bet with parameters: {'track': 'ALBION PARK', 'race_number': 1, 'runner_number': '2', 'bookmaker_name': 'Sportsbet', 'betfair_lay_price': 2.4, 'bookmaker_price': 2.5}
  Link:      https://www.betwatch.com/app/racing/2023-10-27/G/ALBION%20PARK/1
-------------------------------------
        """

        opportunity_details = parse_phase1_output_for_betmatic(example_phase1_output)

        if opportunity_details:
            print(f"DEBUG: Parsed Data: {opportunity_details}")

            # Step 2: Create a notification using the parsed details
            # Define notification type and testing mode
            notification_type = "Fixed Profit"  # Or "Fixed Win"
            is_testing = True  # Set to False for production

            create_betmatic_notification(auth_token, opportunity_details, notification_type, is_testing)

            # Example with a Harness race (ensure 'code' mapping in create_betmatic_notification handles it)
            print("\n--- Simulating Another Phase 1 Output (Harness) ---")
            example_phase1_harness_output = """
-------------------------------------
>>> Opportunity Found! <<<
  Race:      MENANGLE (R3) - HARNESS RACE NAME
  Meeting:   MENANGLE (Harness)
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
                create_betmatic_notification(auth_token, opportunity_details_harness, notification_type, is_testing)

        else:
            print("Could not parse opportunity details from Phase 1 output.")
    else:
        print("Could not log in to Betmatic. Aborting.")
