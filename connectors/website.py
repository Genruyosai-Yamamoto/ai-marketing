from connectors.base import BaseConnector


class WebsiteConnector(BaseConnector):

    def execute(
        self,
        action,
        business_id,
        user_id,
    ):
        """
        Execute an approved website action in dry-run mode.

        This does not modify the website.
        """

        action_type = action.get("action_type")

        if action_type != "website":
            raise ValueError(
                "Website connector only supports website actions"
            )

        return {
            "success": True,
            "status": "website_dry_run_completed",
            "message": (
                "Website action validated successfully "
                "in dry-run mode. No website changes were made."
            ),
            "business_id": business_id,
            "user_id": user_id,
            "action_title": action.get("action_title"),
            "action_type": action_type,
            "objective": action.get("objective"),
            "description": action.get("description"),
            "required_inputs": action.get("required_inputs", []),
        }