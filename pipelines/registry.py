"""SOURCE_REGISTRY — nenhum coletor sem source_id cadastrado."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(
    os.getenv("ATLAS_SOURCE_REGISTRY", ROOT / "data" / "source_registry.json")
)
DATASETS_PATH = Path(
    os.getenv("ATLAS_SOURCE_DATASETS", ROOT / "data" / "source_datasets.json")
)
STATE_PATH = ROOT / "data" / "lake" / "meta" / "registry_state.json"
CONNECTOR_VERSION = os.getenv("ATLAS_CONNECTOR_VERSION", "1.0")

def dataset_id_from_env(default: str | None = None) -> str | None:
    return os.getenv("ATLAS_DATASET_ID") or default


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        raise FileNotFoundError(f"SOURCE_REGISTRY ausente: {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def load_datasets() -> dict[str, Any]:
    if not DATASETS_PATH.is_file():
        return {"datasets": []}
    return json.loads(DATASETS_PATH.read_text(encoding="utf-8"))


def sources_by_id() -> dict[str, dict]:
    reg = load_registry()
    return {s["source_id"]: s for s in reg.get("sources") or []}


def require_source(source_id: str) -> dict:
    """Falha se source_id não estiver no registry."""
    src = sources_by_id().get(source_id)
    if not src:
        raise RuntimeError(
            f"source_id '{source_id}' não está no SOURCE_REGISTRY. "
            "Cadastre em data/source_registry.json antes do coletor."
        )
    if src.get("status") == "disabled":
        raise RuntimeError(f"source_id '{source_id}' está disabled")
    return src


def start_run(source_id: str, dataset_id: str | None = None) -> dict:
    src = require_source(source_id)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = {
        "ingestion_run_id": run_id,
        "source_id": source_id,
        "dataset_id": dataset_id,
        "started_at": _utc(),
        "connector_name": src.get("connector_name"),
        "connector_version": src.get("connector_version") or CONNECTOR_VERSION,
    }
    try:
        from pipelines.control_plane import record_run_start

        record_run_start(run)
    except Exception:
        pass
    return run


def _load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"sources": {}}


def _derive_health(st: dict, src: dict) -> str:
    """HEALTHY | DEGRADED | BROKEN | SCHEMA_CHANGED | UNAVAILABLE | UNKNOWN."""
    status = (src.get("status") or "").lower()
    if status in ("disabled", "unavailable"):
        return "UNAVAILABLE"
    if st.get("ok") is False:
        return "BROKEN"
    if st.get("ok") is True:
        return "HEALTHY"
    if status in ("stub", "registered"):
        return "UNKNOWN"
    if status == "partial":
        return "DEGRADED"
    return "UNKNOWN"


def mark_ingested(
    source_id: str,
    *,
    run_id: str,
    counts: dict | None = None,
    ok: bool = True,
    error: str | None = None,
    dataset_id: str | None = None,
    last_hash: str | None = None,
    last_cursor: str | None = None,
) -> None:
    # consome pending_hash do check_source_update se não passado
    if last_hash is None and dataset_id:
        last_hash = _peek_pending_hash(source_id, dataset_id)

    state = _load_state()
    state.setdefault("sources", {})
    entry = {
        "last_ingested_at": _utc(),
        "last_run_id": run_id,
        "ok": ok,
        "error": error,
        "counts": counts or {},
        "dataset_id": dataset_id,
        "last_hash": last_hash,
        "last_cursor": last_cursor,
    }
    state["sources"][source_id] = entry
    if dataset_id:
        state.setdefault("datasets", {})
        state["datasets"][dataset_id] = {
            **(state["datasets"].get(dataset_id) or {}),
            "source_id": source_id,
            "last_hash": last_hash,
            "last_ingested_at": _utc(),
            "last_run_id": run_id,
            "ok": ok,
            "last_decision": "SUCCESS" if ok else "FAILED",
        }
        state["datasets"][dataset_id].pop("pending_hash", None)
        # compat chave composta
        key = f"{source_id}::{dataset_id}"
        state["datasets"][key] = dict(state["datasets"][dataset_id])
    state["updated_at"] = _utc()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if last_hash and dataset_id:
        _clear_pending_file(source_id, dataset_id)
    try:
        from pipelines.control_plane import record_run_finish

        record_run_finish(
            source_id=source_id,
            run_id=run_id,
            dataset_id=dataset_id,
            counts=counts or {},
            ok=ok,
            error=error,
            last_hash=last_hash,
            last_cursor=last_cursor,
        )
    except Exception:
        pass


def _peek_pending_hash(source_id: str, dataset_id: str) -> str | None:
    pending = ROOT / "data" / "lake" / "meta" / "pending_hashes.json"
    if pending.exists():
        try:
            blob = json.loads(pending.read_text(encoding="utf-8"))
            if blob.get(dataset_id):
                return blob[dataset_id]
            key = f"{source_id}::{dataset_id}"
            if blob.get(key):
                return blob[key]
        except Exception:
            pass
    state = _load_state()
    ds = (state.get("datasets") or {}).get(dataset_id) or {}
    return ds.get("pending_hash")


def _clear_pending_file(source_id: str, dataset_id: str) -> None:
    pending = ROOT / "data" / "lake" / "meta" / "pending_hashes.json"
    if not pending.exists():
        return
    try:
        blob = json.loads(pending.read_text(encoding="utf-8"))
        blob.pop(dataset_id, None)
        blob.pop(f"{source_id}::{dataset_id}", None)
        pending.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def commit_pending_hash(source_id: str, dataset_id: str, run_id: str | None = None) -> None:
    """Após extract OK — promove pending_hash → last_hash."""
    fp = _peek_pending_hash(source_id, dataset_id)
    rid = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mark_ingested(
        source_id,
        run_id=rid,
        counts={"commit_hash": 1},
        ok=True,
        dataset_id=dataset_id,
        last_hash=fp,
    )


def coverage_report() -> dict:
    reg = load_registry()
    state = _load_state()
    rows = []
    for s in reg.get("sources") or []:
        sid = s["source_id"]
        st = (state.get("sources") or {}).get(sid) or {}
        cov_status = s.get("coverage_status")
        if not cov_status:
            if s.get("coverage_start") or s.get("coverage_end"):
                cov_status = "PARTIAL"
            else:
                cov_status = "UNKNOWN"
        rows.append(
            {
                "source_id": sid,
                "source_name": s.get("source_name"),
                "status": s.get("status"),
                "priority": s.get("priority"),
                "connector_name": s.get("connector_name"),
                "reliability": s.get("reliability") or s.get("source_type"),
                "coverage_start": s.get("coverage_start"),
                "coverage_end": s.get("coverage_end"),
                "coverage_status": cov_status,
                "health_status": _derive_health(st, s),
                "last_ingested_at": st.get("last_ingested_at"),
                "last_run_ok": st.get("ok"),
                "last_run_id": st.get("last_run_id"),
                "counts": st.get("counts") or {},
            }
        )
    by_status: dict[str, int] = {}
    by_coverage: dict[str, int] = {}
    by_health: dict[str, int] = {}
    for r in rows:
        by_status[r["status"] or "?"] = by_status.get(r["status"] or "?", 0) + 1
        by_coverage[r["coverage_status"]] = by_coverage.get(r["coverage_status"], 0) + 1
        by_health[r["health_status"]] = by_health.get(r["health_status"], 0) + 1
    return {
        "gerado_em": _utc(),
        "total_sources": len(rows),
        "por_status": by_status,
        "por_coverage_status": by_coverage,
        "por_health_status": by_health,
        "sources": rows,
    }
