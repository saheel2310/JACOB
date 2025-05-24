# JACOB
# Betwatch Opportunity Finder & Betmatic Notifier

This project consists of two Python scripts:

1.  **`phase1.py` (Betwatch Opportunity Finder):** Scans the Betwatch API for potential betting opportunities where a bookmaker's fixed win price is greater than or equal to the Betfair lay price for selected race types.
2.  **`phase2.py` (Betmatic Notification Creator):** Takes the details of an opportunity (currently from a simulated output similar to `phase1.py`) and creates a notification on the Betmatic platform.

## Overview

The system is designed to:
*   **Phase 1:** Continuously monitor upcoming Greyhound and Harness races in specified Australian locations via the Betwatch API. It identifies scenarios where backing a runner with a bookmaker and laying the same runner on Betfair could potentially be advantageous. Identified opportunities are printed to the console and logged.
*   **Phase 2:** Process the details of such an opportunity (specifically the parameters passed to the `place_bet` function in `phase1.py`) and use the Betmatic API to create an automated betting notification.

**Note:** The `place_bet` function in `phase1.py` is currently a placeholder and does not execute any real bets. Its primary role here is to print the parameters that `phase2.py` is designed to parse.

## Features

### Phase 1: Betwatch Opportunity Finder (`phase1.py`)

*   Connects to the Betwatch GraphQL API.
*   Fetches race data for Greyhound and Harness races.
*   Filters races based on:
    *   Time to jump (configurable `MIN_TIME_TO_JUMP` and `MAX_TIME_TO_JUMP`).
    *   Race types (`TARGET_RACE_TYPES_STR`).
    *   Locations/States (`TARGET_LOCATIONS`).
*   Compares bookmaker fixed win prices against Betfair lay prices.
*   Prints newly found opportunities to the console, including a Betwatch race link.
*   Logs detailed information, including API requests and errors, to a rotating log file in the system's temporary directory.
*   Avoids duplicate console alerts for the same opportunity (Race+Runner+Bookmaker) during a single script run.
*   Configurable check interval.
*   Includes exponential backoff for API requests to handle transient errors.

### Phase 2: Betmatic Notification Creator (`phase2.py`)

*   Logs into the Betmatic API using provided credentials.
*   Can refresh the Betmatic API token.
*   Parses opportunity details from a string format (matching the output of `phase1.py`'s `place_bet` call).
*   Maps race and bookmaker information from Phase 1 to Betmatic's internal IDs by:
    *   Looking up competition details (track, race type, race number) on Betmatic.
    *   Looking up bookmaker IDs on Betmatic.
*   Constructs and sends a notification creation request to the Betmatic API.
*   Supports "Fixed Profit" or "Fixed Win" notification types.
*   Includes a testing mode (`is_testing`) which affects wager amounts.
*   Filters out "Galloping" race types if they are inadvertently passed.

## Prerequisites

*   Python 3.7+
*   **Betwatch API Key:** Required for `phase1.py`.
*   **Betmatic Account Credentials:** Email and password required for `phase2.py`.

## Setup

1.  **Download Files:**
    Download `phase1.py` and `phase2.py` to your project directory.

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    Create a `requirements.txt` file with the following content:
    ```
    requests
    python-dotenv
    pytz
    backoff
    ```
    Then install them:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configuration:**

    *   **For `phase1.py` (Betwatch API Key):**
        Create a file named `.env` in the same directory as `phase1.py` and add your Betwatch API key:
        ```
        BETWATCH_API_KEY="YOUR_BETWATCH_API_KEY_HERE"
        ```
        Alternatively, you can modify `phase1.py` to set the `API_KEY` directly, but using a `.env` file is recommended.

    *   **For `phase2.py` (Betmatic Credentials):**
        You need to provide your Betmatic email and password. Currently, these are hardcoded in the `if __name__ == "__main__":` block of `phase2.py`:
        ```python
        betmatic_email = 'YOUR_BETMATIC_EMAIL'  # CHANGEME
        betmatic_password = 'YOUR_BETMATIC_PASSWORD'  # CHANGEME
        ```
        **Security Note:** Hardcoding credentials is not secure for production environments. Consider using environment variables or a more secure secrets management solution.

## Usage

### Running Phase 1 (`phase1.py`)

This script runs continuously, checking for opportunities at a defined interval.

```bash
python phase1.py [options]
