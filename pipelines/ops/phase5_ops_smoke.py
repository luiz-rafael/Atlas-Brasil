#!/usr/bin/env python3
"""
Fase 5 — smoke ops lakehouse.

Valida papéis:
  local  = cache/dev (sempre)
  MinIO  = staging/produção-alvo (se endpoint responder)

Uso:
  python pipelines/ops/phase5_ops_smoke.py
  python pipelines/ops/phase5_ops_smoke.py --require-minio   # falha se MinIO down
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def minio_alive(endpoint: str, timeout: float = 2.0) -> bool:
    base = endpoint.rstrip("/")
    for path in ("/minio/health/live", "/minio/health/ready"):
        try:
            with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as r:
                if 200 <= r.status < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False


def smoke_local_iceberg() -> dict:
    import polars as pl

    from pipelines.lakehouse.catalog import ensure_all_namespaces, reset_catalog_cache
    from pipelines.lakehouse.io import read_table, row_count, write_table

    reset_catalog_cache()
    ensure_all_namespaces(backend="local")
    df = pl.DataFrame(
        {
            "id": ["phase5_local_1"],
            "canonical_model": ["SMOKE"],
            "atlas_domain": ["documentos_evidencias"],
            "value": [1.0],
        }
    )
    w = write_table("gold", "phase5_ops_smoke", df, mode="overwrite", backend="local")
    n = row_count("gold", "phase5_ops_smoke", backend="local")
    rb = read_table("gold", "phase5_ops_smoke", limit=1, backend="local")
    ok = n == 1 and w.get("backend") == "local"
    return {"ok": ok, "write": w, "rows": n, "sample": rb.to_dicts()}


def smoke_minio_stack() -> dict:
    # força dual + minio para esta execução
    os.environ["ATLAS_MINIO_ENABLED"] = "1"
    os.environ["ATLAS_STORAGE_BACKEND"] = "dual"

    from pipelines.ops.ensure_iceberg_bucket import ensure_iceberg_bucket
    from pipelines.ops.ensure_minio_bucket import main as ensure_raw
    from pipelines.ops.phase1_bronze_dual_smoke import main as phase1

    raw_code = ensure_raw()
    ice_ok = ensure_iceberg_bucket()
    p1 = phase1()

    import polars as pl
    from pipelines.lakehouse.catalog import ensure_all_namespaces, reset_catalog_cache
    from pipelines.lakehouse.io import read_table, write_table

    reset_catalog_cache()
    ensure_all_namespaces(backend="s3")
    df = pl.DataFrame(
        {
            "id": ["phase5_s3_1"],
            "canonical_model": ["SMOKE"],
            "value": [5.0],
        }
    )
    w = write_table("gold", "phase5_ops_smoke", df, mode="overwrite", backend="s3")
    rb = read_table("gold", "phase5_ops_smoke", limit=1, backend="s3")
    s3_ok = w.get("rows") == 1 and rb.height == 1

    return {
        "ok": raw_code == 0 and ice_ok and p1 == 0 and s3_ok,
        "atlas_raw_bucket": raw_code == 0,
        "atlas_iceberg_bucket": ice_ok,
        "phase1_dual": p1 == 0,
        "iceberg_s3_write": w,
        "iceberg_s3_read_rows": rb.height,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--require-minio",
        action="store_true",
        help="Exit 1 se MinIO inacessivel (CI staging)",
    )
    args = ap.parse_args()

    endpoint = os.getenv("ATLAS_MINIO_ENDPOINT", "http://127.0.0.1:9000")
    alive = minio_alive(endpoint)

    local = smoke_local_iceberg()
    minio_part: dict | None = None
    if alive:
        minio_part = smoke_minio_stack()
    elif args.require_minio:
        out = {
            "ok": False,
            "phase": 5,
            "error": f"MinIO required but unreachable: {endpoint}",
            "local_iceberg": local,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    ok = local.get("ok") and (minio_part is None or minio_part.get("ok"))
    out = {
        "ok": ok,
        "phase": 5,
        "roles": {
            "local": "cache_dev",
            "minio": "staging_production_target",
        },
        "minio_endpoint": endpoint,
        "minio_reachable": alive,
        "local_iceberg": local,
        "minio_stack": minio_part,
        "note": "Metastore Iceberg ainda SQLite local; remoto = evolucao futura",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
