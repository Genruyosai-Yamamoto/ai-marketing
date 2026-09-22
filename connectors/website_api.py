import os
import requests

WEBSITE_API_BASE_URL = os.getenv("WEBSITE_API_BASE_URL")


class WebsiteAPIError(Exception):
    """Raised when the Website API returns an error."""
    pass


class WebsiteAPI:
    def __init__(
        self,
        access_token,
    ):
        if not access_token:
            raise ValueError(
                "Website access token is required"
            )

        if not WEBSITE_API_BASE_URL:
            raise ValueError(
                "Website API base URL is not configured"
            )

        self.base_url = (
            WEBSITE_API_BASE_URL.rstrip("/")
        )

        self.access_token = access_token

    def get_site(self):
        response = requests.get(
            f"{self.base_url}/me",
            params={
                "fields": "id,domain",
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

            raise WebsiteAPIError(
                error_data
            )

        data = response.json()

        site_id = data.get("id")

        if not site_id:
            raise WebsiteAPIError(
                "Website API did not return a site ID"
            )

        return {
            "site_id": site_id,
            "domain": data.get("domain"),
        }
        
    def create_page_draft(
        self,
        page_url,
        content=None,
    ):
        """
        Create a website page draft.
        """

        if not page_url:
            raise ValueError(
                "page_url is required"
            )

        payload = {
            "page_url": page_url,
        }

        if content:
            payload["content"] = content

        response = requests.post(
            f"{self.base_url}/me/pages",
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

            raise WebsiteAPIError(
                error_data
            )

        data = response.json()

        draft_id = data.get(
            "id"
        )

        if not draft_id:
            raise WebsiteAPIError(
                "Website API did not return "
                "a page draft ID"
            )

        return draft_id

    def get_publish_status(
        self,
        draft_id,
    ):
        """
        Check the processing status of a page draft.
        """

        if not draft_id:
            raise ValueError(
                "draft_id is required"
            )

        response = requests.get(
            f"{self.base_url}/{draft_id}",
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

            raise WebsiteAPIError(
                error_data
            )

        return response.json()

    def publish_page(
        self,
        draft_id,
    ):
        """
        Publish a previously created page draft.
        """

        if not draft_id:
            raise ValueError(
                "draft_id is required"
            )

        response = requests.post(
            f"{self.base_url}/me/page_publish",
            params={
                "creation_id": draft_id,
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

            raise WebsiteAPIError(
                error_data
            )

        data = response.json()

        page_id = data.get(
            "id"
        )

        if not page_id:
            raise WebsiteAPIError(
                "Website API did not return "
                "a published page ID"
            )

        return page_id