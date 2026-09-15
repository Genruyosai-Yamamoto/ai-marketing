import os

import redis


DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _get_redis():
    return redis.Redis.from_url(
        os.environ.get("REDIS_URL", DEFAULT_REDIS_URL),
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def redis_increment_login_attempts(ip, max_attempts, lockout_seconds):
    try:
        r = _get_redis()
        key = f"login_attempts:{ip}"
        lock_key = f"login_lock:{ip}"
        count = r.incr(key)
        r.expire(key, lockout_seconds)
        is_locked = count >= max_attempts
        if is_locked:
            r.set(lock_key, "1", ex=lockout_seconds)
        ttl = r.ttl(lock_key)
        return count, is_locked, ttl
    except redis.RedisError:
        return 0, False, 0


def redis_reset_login_attempts(ip):
    try:
        r = _get_redis()
        r.delete(f"login_attempts:{ip}", f"login_lock:{ip}")
    except redis.RedisError:
        pass


def redis_check_registration_limit(ip, max_per_hour):
    try:
        r = _get_redis()
        key = f"reg_count:{ip}"
        raw = r.get(key)
        current = int(raw) if raw is not None else 0
        return current < max_per_hour
    except redis.RedisError:
        return None


def redis_log_registration(ip):
    try:
        r = _get_redis()
        key = f"reg_count:{ip}"
        r.incr(key)
        r.expire(key, 3600)
    except redis.RedisError:
        pass


def redis_is_locked(ip):
    try:
        r = _get_redis()
        ttl = r.ttl(f"login_lock:{ip}")
        if ttl and ttl > 0:
            return True, ttl
        return False, 0
    except redis.RedisError:
        return False, 0