from __future__ import annotations

import os
from typing import Any

_conn = None


def get_conn():
    global _conn
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
    )
    if not url:
        return None
    try:
        import psycopg

        if _conn is None or _conn.closed:
            _conn = psycopg.connect(url)
        return _conn
    except Exception:
        return None


def ping_postgres() -> bool:
    conn = get_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        return False
