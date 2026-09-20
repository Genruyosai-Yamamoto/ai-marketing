import requests


class InstagramAPIError(Exception):
    """Raised when the Instagram API returns an error."""
    pass


class InstagramAPI:
    def __init__(
        self,
        access_token,
    ):
        if not access_token:
            raise ValueError(
                "Instagram access token is required"
            )

        if not INSTAGRAM_API_BASE_URL:
            raise ValueError(
                "Instagram API base URL is not configured"
            )

        self.base_url = (
            INSTAGRAM_API_BASE_URL.rstrip("/")
        )

        self.access_token = access_token

    def get_account(self):
        response = requests.get(
            f"{self.base_url}/me",
            params={
                "fields": "id,username",
            },
            headers={
                "Authorization": (
                    f"Bearer {self.access_token}"
                ),
            },
            timeout=10,
        )

        if not response.ok:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {
                    "message": response.text
                }

            raise InstagramAPIError(
                error_data
            )

        data = response.json()

        account_id = data.get("id")

        if not account_id:
            raise InstagramAPIError(
                "Instagram API did not return an account ID"
            )

        return {
            "account_id": account_id,
            "username": data.get("username"),
        }
        
def create_media_container(
    self,
    image_url,
    caption=None,
):
    """
    Create an Instagram image media container.
    """

    if not image_url:
        raise ValueError(
            "image_url is required"
        )

    payload = {
        "image_url": image_url,
    }

    if caption:
        payload["caption"] = caption

    response = requests.post(
        f"{self.base_url}/me/media",
        params=payload,
        headers={
            "Authorization": (
                f"Bearer {self.access_token}"
            ),
        },
        timeout=10,
    )

    if not response.ok:
        try:
            error_data = response.json()
        except ValueError:
            error_data = {
                "message": response.text
            }

        raise InstagramAPIError(
            error_data
        )

    data = response.json()

    container_id = data.get(
        "id"
    )

    if not container_id:
        raise InstagramAPIError(
            "Instagram did not return "
            "a media container ID"
        )

    return container_id

def get_media_container_status(
    self,
    container_id,
):
    """
    Check the processing status of a media container.
    """

    if not container_id:
        raise ValueError(
            "container_id is required"
        )

    response = requests.get(
        f"{self.base_url}/{container_id}",
        params={
            "fields": "status_code",
        },
        headers={
            "Authorization": (
                f"Bearer {self.access_token}"
            ),
        },
        timeout=10,
    )

    if not response.ok:
        try:
            error_data = response.json()
        except ValueError:
            error_data = {
                "message": response.text
            }

        raise InstagramAPIError(
            error_data
        )

    return response.json()

def publish_media(
    self,
    container_id,
):
    """
    Publish a previously created media container.
    """

    if not container_id:
        raise ValueError(
            "container_id is required"
        )

    response = requests.post(
        f"{self.base_url}/me/media_publish",
        params={
            "creation_id": container_id,
        },
        headers={
            "Authorization": (
                f"Bearer {self.access_token}"
            ),
        },
        timeout=10,
    )

    if not response.ok:
        try:
            error_data = response.json()
        except ValueError:
            error_data = {
                "message": response.text
            }

        raise InstagramAPIError(
            error_data
        )

    data = response.json()

    media_id = data.get(
        "id"
    )

    if not media_id:
        raise InstagramAPIError(
            "Instagram did not return "
            "a published media ID"
        )

    return media_id