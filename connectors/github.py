from connectors.base import BaseConnector
from connectors.github_api import GitHubAPI
from services.connection_service import get_connection


class GitHubConnector(BaseConnector):
    def execute(self, action, business_id, user_id):
        if action.get("action_type") != "github":
            raise ValueError(
                "GitHub connector only supports github actions"
            )

        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="github",
        )

        if not connection:
            raise ValueError(
                "GitHub connection not found"
            )

        github = GitHubAPI(
            access_token=connection["access_token"]
        )

        return {
            "success": True,
            "status": "github_connection_verified",
            "message": (
                "GitHub connection retrieved successfully. "
                "No repository changes were made."
            ),
            "business_id": business_id,
            "user_id": user_id,
            "repository": connection.get("repository"),
            "default_branch": connection.get("default_branch"),
            "github_client_ready": github is not None,
            "action_title": action.get("action_title"),
        }