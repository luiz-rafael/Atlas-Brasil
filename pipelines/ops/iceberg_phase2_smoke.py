#!/usr/bin/env python3
"""Smoke Fase 2: namespaces + write/read Iceberg no MinIO."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    import polars as pl

    from pipelines.lakehouse.catalog import ensure_all_namespaces, reset_catalog_cache
    from pipelines.lakehouse.config import ICEBERG_S3_WAREHOUSE
    from pipelines.lakehouse.io import read_table, row_count, write_table
    from pipelines.ops.ensure_iceberg_bucket import ensure_iceberg_bucket

    reset_catalog_cache()
    if not ensure_iceberg_bucket():
        print(json.dumps({"ok": False, "error": "bucket"}))
        return 1

    ns = ensure_all_namespaces(backend="s3")
    sample = pl.DataFrame(
        {
            "id": ["smoke_debt_1", "smoke_debt_2"],
            "dataset_id": ["smoke.debt", "smoke.debt"],
            "reference_date": ["2024-01-01", "2024-02-01"],
            "value": [1.0, 2.0],
            "unit": ["BRL", "BRL"],
        }
    )
    w = write_table(
        "silver", "phase2_smoke_fiscal", sample, mode="overwrite", backend="s3"
    )
    n = row_count("silver", "phase2_smoke_fiscal", backend="s3")
    df = read_table("silver", "phase2_smoke_fiscal", limit=5, backend="s3")

    ok = n == 2 and w.get("backend") == "s3"
    out = {
        "ok": ok,
        "phase": 2,
        "warehouse": ICEBERG_S3_WAREHOUSE,
        "namespaces": ns,
        "write": w,
        "rows": n,
        "sample": df.to_dicts(),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
