import pytest

from connectors import get_connector
from connectors.instagram import InstagramConnector


UNROUTED_TYPES = ["website", "content", "seo", "email", "research", "other"]


def test_get_connector_social_returns_instagram_connector():
    connector = get_connector({"action_type": "social"})
    assert isinstance(connector, InstagramConnector)


@pytest.mark.parametrize("action_type", UNROUTED_TYPES)
def test_get_connector_unrouted_action_type_raises(action_type):
    with pytest.raises(ValueError, match="No connector available for action type"):
        get_connector({"action_type": action_type})


@pytest.mark.parametrize(
    "action",
    [{}, {"action_type": None}, {"action_type": ""}],
)
def test_get_connector_missing_or_blank_action_type_raises(action):
    with pytest.raises(ValueError, match="No connector available for action type"):
        get_connector(action)


def test_instagram_connector_accepts_social_action():
    result = InstagramConnector().execute({"action_type": "social"})
    assert result["success"] is True
    assert result["status"] == "not_implemented"
    assert result["message"]


def test_instagram_connector_rejects_non_social_action():
    with pytest.raises(ValueError, match="only supports social actions"):
        InstagramConnector().execute({"action_type": "email"})