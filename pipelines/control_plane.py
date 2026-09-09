"""Control plane — source_state / ingestion_run / quarantine (Postgres fail-soft)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv(
        "ATLAS_DATABASE_URL",
        "",  # vazio = só JSON local
    ),
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    url = DATABASE_URL.strip()
    if not url:
        # default local compose (host port 5433)
        if os.getenv("ATLAS_PG_CONTROL", "").lower() in ("1", "true", "yes"):
            url = "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil"
        else:
            return None
    try:
        import psycopg
    except ImportError:
        return None
    try:
        return psycopg.connect(url, connect_timeout=3)
    except Exception:
        return None


def record_run_start(run: dict[str, Any]) -> None:
    conn = _connect()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingestion_run (
                      run_id, source_id, dataset_id, started_at, status
                    ) VALUES (%s, %s, %s, %s::timestamptz, 'RUNNING')
                    ON CONFLICT (run_id) DO UPDATE SET
                      started_at = EXCLUDED.started_at,
                      status = 'RUNNING'
                    """,
                    (
                        run["ingestion_run_id"],
                        run["source_id"],
                        run.get("dataset_id"),
                        run.get("started_at") or _utc(),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO source_state (
                      source_id, dataset_id, last_checked_at, health_status, updated_at
                    ) VALUES (%s, %s, %s::timestamptz, 'UNKNOWN', NOW())
                    ON CONFLICT (source_id, dataset_id) DO UPDATE SET
                      last_checked_at = EXCLUDED.last_checked_at,
                      updated_at = NOW()
                    """,
                    (
                        run["source_id"],
                        run.get("dataset_id") or "",
                        run.get("started_at") or _utc(),
                    ),
                )
    finally:
        conn.close()


def record_run_finish(
    *,
    source_id: str,
    run_id: str,
    dataset_id: str | None = None,
    counts: dict | None = None,
    ok: bool = True,
    error: str | None = None,
    last_hash: str | None = None,
    last_cursor: str | None = None,
) -> None:
    conn = _connect()
    if not conn:
        return
    counts = counts or {}
    status = "SUCCESS" if ok else "FAILED"
    # PARTIAL se ok mas houve falhas reportadas
    if ok and (counts.get("fail") or 0) > 0:
        status = "PARTIAL"
    health = "HEALTHY" if ok else "BROKEN"
    if status == "PARTIAL":
        health = "DEGRADED"
    now = _utc()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ingestion_run SET
                      finished_at = %s::timestamptz,
                      records_found = COALESCE(%s, records_found),
                      records_processed = COALESCE(%s, records_processed),
                      records_inserted = COALESCE(%s, records_inserted),
                      records_updated = COALESCE(%s, records_updated),
                      records_rejected = COALESCE(%s, records_rejected),
                      records_quarantined = COALESCE(%s, records_quarantined),
                      status = %s,
                      error = %s,
                      counts = %s::jsonb
                    WHERE run_id = %s
                    """,
                    (
                        now,
                        counts.get("found"),
                        counts.get("processed") or counts.get("ok"),
                        counts.get("inserted") or counts.get("ok") or counts.get("mun"),
                        counts.get("updated"),
                        counts.get("rejected") or counts.get("fail"),
                        counts.get("quarantined"),
                        status,
                        error,
                        json.dumps(counts),
                        run_id,
                    ),
                )
                # se UPDATE não achou linha (start falhou), INSERT
                if cur.rowcount == 0:
                    cur.execute(
                        """
                        INSERT INTO ingestion_run (
                          run_id, source_id, dataset_id, started_at, finished_at,
                          status, error, counts
                        ) VALUES (
                          %s, %s, %s, %s::timestamptz, %s::timestamptz,
                          %s, %s, %s::jsonb
                        )
                        ON CONFLICT (run_id) DO NOTHING
                        """,
                        (
                            run_id,
                            source_id,
                            dataset_id,
                            now,
                            now,
                            status,
                            error,
                            json.dumps(counts),
                        ),
                    )
                cur.execute(
                    """
                    INSERT INTO source_state (
                      source_id, dataset_id, last_checked_at, last_successful_at,
                      last_hash, last_cursor, last_run_id, health_status, updated_at
                    ) VALUES (
                      %s, %s, %s::timestamptz,
                      CASE WHEN %s THEN %s::timestamptz ELSE NULL END,
                      %s, %s, %s, %s, NOW()
                    )
                    ON CONFLICT (source_id, dataset_id) DO UPDATE SET
                      last_checked_at = EXCLUDED.last_checked_at,
                      last_successful_at = COALESCE(
                        EXCLUDED.last_successful_at, source_state.last_successful_at
                      ),
                      last_hash = COALESCE(EXCLUDED.last_hash, source_state.last_hash),
                      last_cursor = COALESCE(EXCLUDED.last_cursor, source_state.last_cursor),
                      last_run_id = EXCLUDED.last_run_id,
                      health_status = EXCLUDED.health_status,
                      updated_at = NOW()
                    """,
                    (
                        source_id,
                        dataset_id or "",
                        now,
                        ok,
                        now,
                        last_hash,
                        last_cursor,
                        run_id,
                        health,
                    ),
                )
    finally:
        conn.close()


def quarantine_put(
    *,
    source_id: str,
    reason_code: str,
    payload: dict | list | str,
    dataset_id: str | None = None,
    run_id: str | None = None,
    entity_hint: str | None = None,
) -> None:
    """Escrita mínima em quarantine (fail-soft)."""
    conn = _connect()
    if not conn:
        return
    if isinstance(payload, (dict, list)):
        body = json.dumps(payload, ensure_ascii=False)
    else:
        body = str(payload)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO quarantine (
                      source_id, dataset_id, run_id, reason_code,
                      payload, entity_hint, status
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, 'OPEN')
                    """,
                    (
                        source_id,
                        dataset_id,
                        run_id,
                        reason_code,
                        body if body.startswith("{") or body.startswith("[") else json.dumps({"text": body}),
                        entity_hint,
                    ),
                )
    finally:
        conn.close()
