from config.instagram import INSTAGRAM_API_BASE_URL
from connectors.instagram_api import InstagramAPI


def get_instagram_account(access_token):
    """
    Validate an Instagram access token and retrieve
    the connected Instagram account.
    """

    api = InstagramAPI(
        base_url=INSTAGRAM_API_BASE_URL,
        access_token=access_token,
    )

    return api.get_account()