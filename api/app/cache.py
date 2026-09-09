from __future__ import annotations

import json
import os
from typing import Any

_redis = None


def _client():
    global _redis
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        if _redis is None:
            _redis = redis.from_url(url, decode_responses=True, socket_connect_timeout=1)
        _redis.ping()
        return _redis
    except Exception:
        return None


def cache_get(key: str) -> Any | None:
    r = _client()
    if not r:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl: int = 60) -> bool:
    r = _client()
    if not r:
        return False
    try:
        r.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
        return True
    except Exception:
        return False
