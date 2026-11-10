"""Silence project configuration, loaded from the container environment."""

import os


SECRET_KEY = os.environ["SILENCE_SECRET_KEY"]
DEBUG_ENABLED = False
LISTEN_ADDRESS = "0.0.0.0"
HTTP_PORT = 8000
RUN_API = True
RUN_WEB = False
API_PREFIX = "/api"
ENABLE_LOGIN = True
ENABLE_REGISTER = True
ENABLE_SUMMARY = False
SHOW_ENDPOINT_LIST = False
ENABLE_ENDPOINT_AUTO_GENERATION = False
CHECK_FOR_UPDATES = False

# Silence otherwise logs the complete registration/login request body.
DISPLAY_BODY_PARAMS_CLI = False
ALLOW_CLEAR_PASSWORDS = False
DEFAULT_ROLE_REGISTER = "guest"

DB_CONN = {
    "host": os.environ["DB_HOST"],
    "port": int(os.environ.get("DB_PORT", "3306")),
    "username": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "database": os.environ["DB_NAME"],
}

USER_AUTH_DATA = {
    "table": "users",
    "identifier": "username",
    "password": "password",
    "role": "role",
}
