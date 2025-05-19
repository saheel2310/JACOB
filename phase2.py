import requests

# === Constants ===
BASE_URL = 'https://betmatic.app/api'
# Defines the base URL for the Betmatic API. All API endpoints will be appended to this URL.
LOGIN_ENDPOINT = '/account/login/'
# Defines the specific endpoint for logging in.
REFRESH_ENDPOINT = '/account/refresh_token/'
# Defines the specific endpoint for refreshing the authentication token.

HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}
# Defines a dictionary of HTTP headers that will be included in the requests.  These headers tell the API that the request body is in JSON format and that the client accepts JSON responses.

# === Function: Login and Get Token ===
def login_to_betmatic(email, password):
    # Defines a function that takes an email and password as input and attempts to log in to the Betmatic API.
    url = BASE_URL + LOGIN_ENDPOINT
    # Constructs the complete URL for the login endpoint by combining the base URL and the login endpoint.
    payload = {
        'email': email,
        'password': password
    }
    # Creates a dictionary containing the email and password, which will be sent as the request body.

    try:
    # Starts a `try...except` block to handle potential errors during the API request.
        response = requests.post(url, json=payload, headers=HEADERS)
        # Sends a POST request to the login endpoint with the email and password as JSON data in the request body and the defined headers.  `requests.post` is a function from the `requests` library.
        response.raise_for_status()
        # Raises an HTTPError if the response status code is 4XX or 5XX, indicating an error on the client or server side.  This is a good practice for checking the success of the API call.
        data = response.json()
        # Parses the JSON response from the API into a Python dictionary.
        token = data.get('token')
        # Extracts the value associated with the key 'token' from the dictionary.  `.get('token')` is used in case 'token' is not present in the returned JSON.

        if not token:
        # Checks if the `token` variable is empty or None.
            raise ValueError("Login succeeded, but no token returned.")
        # Raises a ValueError exception if the token is empty, indicating that the login was successful, but no token was returned.

        print(f"✅ Logged in successfully. Token:\n{token}\n")
        # Prints a success message along with the received token. f-strings are used for easy variable insertion into strings.
        return token
        # Returns the authentication token.

    except requests.exceptions.RequestException as e:
    # Catches any exceptions that occur during the API request, such as network errors or invalid URLs.
        print(f"❌ Login Error: {e}")
        # Prints an error message along with the specific exception that occurred.
        return None
        # Returns None if there was an error during login.

# === Function: Refresh Token ===
def refresh_betmatic_token(current_token):
    # Defines a function that takes a current authentication token as input and attempts to refresh it.
    url = BASE_URL + REFRESH_ENDPOINT
    # Constructs the complete URL for the refresh token endpoint.

    headers = {
        **HEADERS,
        'Authorization': f'Token {current_token}'
    }
    # Creates a new `headers` dictionary by combining the existing `HEADERS` dictionary with an `Authorization` header.
    # The `Authorization` header is used to send the current token to the API for authentication. The `**HEADERS` syntax unpacks the `HEADERS` dictionary into the new dictionary.

    payload = {
        'token': current_token 

    }
    try:
    # Starts a `try...except` block to handle potential errors during the API request.
        response = requests.post(url, json=payload, headers=headers)
        # Sends a POST request to the refresh token endpoint with the current token as JSON data in the request body and the defined headers.
        response.raise_for_status()
        # Raises an HTTPError if the response status code is 4XX or 5XX.
        data = response.json()
        # Parses the JSON response from the API into a Python dictionary.

        new_token = data.get('token')
        # Extracts the value associated with the key 'token' from the dictionary, representing the new token.

        if not new_token:
        # Checks if the `new_token` variable is empty or None.
            raise ValueError("Refresh succeeded, but no new token returned.")
        # Raises a ValueError exception if the new token is empty.

        print(f"🔁 Token refreshed successfully. New Token:\n{new_token}\n")
        # Prints a success message along with the new token.
        return new_token
        # Returns the new authentication token.

    except requests.exceptions.RequestException as e:
    # Catches any exceptions that occur during the API request.
        print(f"❌ Refresh Token Error: {e}")
        # Prints an error message along with the specific exception that occurred.
        return None
        # Returns None if there was an error during token refresh.

# === Main Execution ===
if __name__ == "__main__":
    # This block of code will only be executed when the script is run directly (not imported as a module).
    # Replace with your credentials
    email = 'jacobsawers1@gmail.com'
    # Replace with your actual email address.
    password = 'Test1234'
    # Replace with your actual password.

    # Step 1: Login
    initial_token = login_to_betmatic(email, password)
    # Calls the `login_to_betmatic` function with the provided email and password and stores the returned token in the `initial_token` variable.

    # Step 2: Refresh Token (only if login was successful)
    if initial_token:
        # Checks if the `initial_token` variable has a value (meaning login was successful).
        refreshed_token = refresh_betmatic_token(initial_token)
        # Calls the `refresh_betmatic_token` function with the `initial_token` and stores the returned token in the `refreshed_token` variable. This only happens if the login was successful.  