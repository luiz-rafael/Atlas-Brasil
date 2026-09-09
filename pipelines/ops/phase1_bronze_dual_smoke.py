#!/usr/bin/env python3
"""
Fase 1 — validar Bronze dual: local + objeto em atlas-raw (MinIO).

Força ATLAS_MINIO_ENABLED=1 e ATLAS_STORAGE_BACKEND=dual nesta execução
(nao altera o .env do usuario).

Uso:
  python pipelines/ops/phase1_bronze_dual_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Antes de importar raw_store / storage
os.environ["ATLAS_MINIO_ENABLED"] = "1"
os.environ["ATLAS_STORAGE_BACKEND"] = "dual"


def main() -> int:
    from pipelines.common import write_raw_record
    from pipelines.raw_store import MINIO_BUCKET, MINIO_ENDPOINT, ensure_bucket, object_exists
    from pipelines.storage.backend import storage_backend_name

    if not ensure_bucket():
        print(json.dumps({"ok": False, "error": "ensure_bucket atlas-raw"}))
        return 1

    run_id = "phase1_dual_smoke"
    payload = {
        "phase": 1,
        "purpose": "bronze_dual_validation",
        "note": "local+minio mirror",
    }
    meta = write_raw_record(
        source_id="atlas_ops",
        ingestion_run_id=run_id,
        connector_version="phase1.0",
        payload=payload,
        filename="phase1_dual_smoke.json",
        dataset_id="atlas.phase1_bronze_dual",
        source_url=None,
    )

    uri = meta.get("storage_uri") or ""
    # key real no MinIO: raw/{source}/{run}/{filename_hash}
    local_name = Path(meta["file_path"]).name
    minio_key = f"raw/atlas_ops/{run_id}/{local_name}"
    on_minio = object_exists(minio_key)
    local_ok = (ROOT / "data" / "lake" / meta["file_path"]).is_file() if not Path(meta["file_path"]).is_absolute() else Path(meta["file_path"]).is_file()
    # file_path is relative to LAKE
    from pipelines.common import LAKE

    local_path = LAKE / meta["file_path"]
    local_ok = local_path.is_file()

    ok = (
        storage_backend_name() == "dual"
        and local_ok
        and on_minio
        and not meta.get("storage_error")
        and bool(uri)
    )
    out = {
        "ok": ok,
        "phase": 1,
        "backend": storage_backend_name(),
        "endpoint": MINIO_ENDPOINT,
        "bucket": MINIO_BUCKET,
        "local_path": str(local_path),
        "local_ok": local_ok,
        "minio_key": minio_key,
        "minio_ok": on_minio,
        "storage_uri": uri,
        "storage_skipped": meta.get("storage_skipped"),
        "storage_error": meta.get("storage_error"),
        "raw_record_id": meta.get("raw_record_id"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
