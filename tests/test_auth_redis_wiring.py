import pytest


@pytest.fixture
def redis_down(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/15")


def test_auth_module_imports_redis_helpers(redis_down):
    import routes.auth as auth
    assert callable(auth.redis_increment_login_attempts)


def test_increment_attempts_falls_back_to_memory(redis_down):
    import routes.auth as auth
    auth.login_attempts.clear()
    auth.locked_ips.clear()
    auth._increment_attempts("9.9.9.9")
    assert auth.login_attempts.get("9.9.9.9") == 1
    assert not auth.locked_ips.get("9.9.9.9")


def test_reset_attempts_clears_memory(redis_down):
    import routes.auth as auth
    auth.login_attempts.clear()
    auth.locked_ips.clear()
    auth._increment_attempts("9.9.9.9")
    auth._reset_attempts("9.9.9.9")
    assert "9.9.9.9" not in auth.login_attempts
    assert "9.9.9.9" not in auth.locked_ips


def test_check_registration_limit_falls_back_to_memory(redis_down):
    import routes.auth as auth
    auth.registration_log.clear()
    ip = "9.9.9.9"
    assert auth.check_registration_limit(ip) is True
    auth.log_registration(ip)
    auth.log_registration(ip)
    auth.log_registration(ip)
    assert auth.check_registration_limit(ip) is False