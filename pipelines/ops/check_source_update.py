#!/usr/bin/env python3
"""
Gate de atualização por hash.

Saída (stdout):
  ATLAS_UPDATE=SKIPPED|RUN
  ATLAS_NEW_HASH=...
  ATLAS_DATASET=...

Exit 0 sempre que a decisão for clara (skip ou run).
Exit 2 se probe falhar (Airflow retenta).
Exit 3 se requires_env ausente → tratado como SKIPPED (não quebra grade).

ATLAS_FORCE_UPDATE=1 força RUN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.catalog import get_dataset, load_catalog  # noqa: E402
from pipelines.ops.probes import probe_fingerprint  # noqa: E402
from pipelines.registry import STATE_PATH, _load_state  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _last_hash(source_id: str, dataset_id: str) -> str | None:
    state = _load_state()
    # prefer chave por dataset_id (estável entre aliases de source)
    by_ds = (state.get("datasets") or {}).get(dataset_id) or {}
    if by_ds.get("last_hash"):
        return by_ds["last_hash"]
    key = f"{source_id}::{dataset_id}"
    compound = (state.get("datasets") or {}).get(key) or {}
    if compound.get("last_hash"):
        return compound["last_hash"]
    src = (state.get("sources") or {}).get(source_id) or {}
    if src.get("last_hash") and (src.get("dataset_id") in (None, "", dataset_id)):
        return src["last_hash"]

    try:
        from pipelines.control_plane import _connect

        conn = _connect()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT last_hash FROM source_state
                        WHERE source_id = %s AND dataset_id = %s
                        """,
                        (source_id, dataset_id),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        return row[0]
            finally:
                conn.close()
    except Exception:
        pass
    return None


def _record_skipped(source_id: str, dataset_id: str, fp: str) -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        from pipelines.control_plane import record_run_start

        record_run_start(
            {
                "ingestion_run_id": run_id,
                "source_id": source_id,
                "dataset_id": dataset_id,
                "started_at": _utc(),
            }
        )
        from pipelines.control_plane import _connect

        conn = _connect()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE ingestion_run SET
                              finished_at = NOW(), status = 'SKIPPED',
                              counts = '{"skipped":1}'::jsonb
                            WHERE run_id = %s
                            """,
                            (run_id,),
                        )
            finally:
                conn.close()
    except Exception:
        pass
    state = _load_state()
    state.setdefault("datasets", {})
    state["datasets"][dataset_id] = {
        **(state["datasets"].get(dataset_id) or {}),
        "source_id": source_id,
        "last_checked_at": _utc(),
        "last_hash": fp,
        "last_decision": "SKIPPED",
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _remember_pending_hash(source_id: str, dataset_id: str, fp: str) -> None:
    """Guarda hash candidato para mark_ingested pós-extract."""
    state = _load_state()
    state.setdefault("datasets", {})
    state["datasets"][dataset_id] = {
        **(state["datasets"].get(dataset_id) or {}),
        "source_id": source_id,
        "pending_hash": fp,
        "last_checked_at": _utc(),
        "last_decision": "RUN",
    }
    pending = ROOT / "data" / "lake" / "meta" / "pending_hashes.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    blob = {}
    if pending.exists():
        try:
            blob = json.loads(pending.read_text(encoding="utf-8"))
        except Exception:
            blob = {}
    blob[dataset_id] = fp
    pending.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def check_dataset(dataset_id: str, force: bool = False) -> int:
    ds = get_dataset(dataset_id)
    source_id = ds["source_id"]
    for env_name in ds.get("requires_env") or []:
        if not os.getenv(env_name):
            print(f"ATLAS_UPDATE=SKIPPED")
            print(f"ATLAS_DATASET={dataset_id}")
            print(f"ATLAS_SKIP_REASON=missing_env:{env_name}")
            _write_update_env(dataset_id, "SKIPPED", f"missing_env:{env_name}")
            return 0

    force = force or os.getenv("ATLAS_FORCE_UPDATE", "").lower() in ("1", "true", "yes")
    probe = ds.get("probe") or {"kind": "always"}

    try:
        fp = probe_fingerprint(probe)
    except Exception as e:
        print(f"ATLAS_PROBE_ERROR={e}", file=sys.stderr)
        return 2

    prev = _last_hash(source_id, dataset_id)
    print(f"ATLAS_DATASET={dataset_id}")
    print(f"ATLAS_SOURCE_ID={source_id}")
    print(f"ATLAS_NEW_HASH={fp}")
    print(f"ATLAS_PREV_HASH={prev or ''}")

    if not force and prev and prev == fp:
        print("ATLAS_UPDATE=SKIPPED")
        _record_skipped(source_id, dataset_id, fp)
        _write_update_env(dataset_id, "SKIPPED", fp)
        return 0

    print("ATLAS_UPDATE=RUN")
    _remember_pending_hash(source_id, dataset_id, fp)
    _write_update_env(dataset_id, "RUN", fp)
    return 0


def _write_update_env(dataset_id: str, decision: str, fp: str) -> None:
    out = ROOT / "data" / "lake" / "meta" / f"update_{dataset_id}.env"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"ATLAS_UPDATE={decision}\nATLAS_NEW_HASH={fp}\nATLAS_DATASET={dataset_id}\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Check source update by hash")
    ap.add_argument("--dataset", required=True, help="id no catálogo")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true", help="lista datasets e sai")
    args = ap.parse_args()
    if args.list:
        cat = load_catalog()
        for d in cat.get("datasets") or []:
            print(d["id"], d.get("dag_id"), d.get("domain"))
        return 0
    return check_dataset(args.dataset, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
