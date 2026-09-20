from connectors.base import BaseConnector


class DryRunConnector(BaseConnector):

    def execute(
        self,
        action,
        business_id,
        user_id,
    ):
        """
        Safely simulate action execution.

        This connector performs no external API calls
        and causes no external side effects.
        """

        return {
            "success": True,
            "status": "dry_run_completed",
            "message": "Action executed successfully in dry-run mode.",
            "business_id": business_id,
            "user_id": user_id,
            "action_type": action.get("action_type"),
            "action_title": action.get("title"),
        }