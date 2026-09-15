import pytest

import redis_helpers


DEAD_URL = "redis://127.0.0.1:6399/15"


@pytest.fixture
def redis_down(monkeypatch):
    monkeypatch.setenv("REDIS_URL", DEAD_URL)
    return DEAD_URL


def test_increment_returns_fallback_when_redis_down(redis_down):
    result = redis_helpers.redis_increment_login_attempts("1.2.3.4", 5, 900)
    assert result == (0, False, 0)


def test_is_locked_returns_false_when_redis_down(redis_down):
    assert redis_helpers.redis_is_locked("1.2.3.4") == (False, 0)


def test_check_registration_limit_returns_none_when_redis_down(redis_down):
    assert redis_helpers.redis_check_registration_limit("1.2.3.4", 3) is None


def test_log_and_reset_are_noops_when_redis_down(redis_down):
    redis_helpers.redis_log_registration("1.2.3.4")
    redis_helpers.redis_reset_login_attempts("1.2.3.4")