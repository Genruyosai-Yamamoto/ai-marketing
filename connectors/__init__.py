from connectors.dry_run import DryRunConnector
from connectors.instagram import InstagramConnector
from connectors.website import WebsiteConnector
from connectors.github import GitHubConnector


def get_connector(action):
    action_type = action.get("action_type")

    if action_type == "dry_run":
        return DryRunConnector()
    
    if action_type == "github":
        return GitHubConnector()

    if action_type == "social":
        return InstagramConnector()

    if action_type == "website":
        return WebsiteConnector()

    raise ValueError(
        f"No connector available for action type: {action_type}"
    )