import time

from connectors.base import BaseConnector
from connectors.instagram_api import InstagramAPI
from services.connection_service import get_connection


class InstagramConnector(BaseConnector):

    def execute(
        self,
        action,
        business_id,
        user_id,
    ):
        """
        Execute an approved Instagram action.
        """

        action_type = action.get(
            "action_type"
        )

        if action_type != "social":
            raise ValueError(
                "Instagram connector only supports "
                "social actions"
            )

        content_type = action.get(
            "content_type"
        )

        if content_type != "image":
            raise ValueError(
                "Instagram connector currently "
                "supports image actions only"
            )

        image_url = action.get(
            "image_url"
        )

        caption = action.get(
            "caption",
            "",
        )

        if not image_url:
            raise ValueError(
                "Instagram image_url is required"
            )

        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="instagram",
        )

        api = InstagramAPI(
            access_token=connection[
                "access_token"
            ],
        )

        container_id = (
            api.create_media_container(
                image_url=image_url,
                caption=caption,
            )
        )

        max_attempts = 10

        for _ in range(max_attempts):

            status = (
                api.get_media_container_status(
                    container_id
                )
            )

            status_code = status.get(
                "status_code"
            )

            if status_code == "FINISHED":
                break

            if status_code in {
                "ERROR",
                "EXPIRED",
            }:
                raise ValueError(
                    "Instagram media container "
                    f"failed: {status_code}"
                )

            time.sleep(2)

        else:
            raise TimeoutError(
                "Instagram media container "
                "did not finish processing"
            )

        media_id = api.publish_media(
            container_id
        )

        return {
            "success": True,
            "status": "published",
            "instagram_media_id": media_id,
            "container_id": container_id,
            "instagram_account_id": (
                connection["account_id"]
            ),
        }