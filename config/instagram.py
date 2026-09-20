import os
from dotenv import load_dotenv

load_dotenv()

INSTAGRAM_CLIENT_ID = os.getenv(
    "INSTAGRAM_CLIENT_ID"
)

INSTAGRAM_CLIENT_SECRET = os.getenv(
    "INSTAGRAM_CLIENT_SECRET"
)

INSTAGRAM_REDIRECT_URI = os.getenv(
    "INSTAGRAM_REDIRECT_URI"
)

INSTAGRAM_OAUTH_AUTHORIZE_URL = os.getenv(
    "INSTAGRAM_OAUTH_AUTHORIZE_URL"
)

INSTAGRAM_OAUTH_TOKEN_URL = os.getenv(
    "INSTAGRAM_OAUTH_TOKEN_URL"
)

INSTAGRAM_API_BASE_URL = os.getenv(
    "INSTAGRAM_API_BASE_URL"
)

INSTAGRAM_OAUTH_SCOPES = os.getenv(
    "INSTAGRAM_OAUTH_SCOPES",
    "instagram_business_basic instagram_business_content_publish",
)


def validate_instagram_config():
    required = {
        "INSTAGRAM_CLIENT_ID": INSTAGRAM_CLIENT_ID,
        "INSTAGRAM_CLIENT_SECRET": INSTAGRAM_CLIENT_SECRET,
        "INSTAGRAM_REDIRECT_URI": INSTAGRAM_REDIRECT_URI,
        "INSTAGRAM_OAUTH_AUTHORIZE_URL": (
            INSTAGRAM_OAUTH_AUTHORIZE_URL
        ),
        "INSTAGRAM_OAUTH_TOKEN_URL": (
            INSTAGRAM_OAUTH_TOKEN_URL
        ),
        "INSTAGRAM_API_BASE_URL": (
            INSTAGRAM_API_BASE_URL
        ),
    }

    missing = [
        name
        for name, value in required.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing Instagram configuration: "
            + ", ".join(missing)
        )