#!/usr/bin/env python3
"""Smoke Fase 3: promove gold fiscal e valida canonical_model no MinIO."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from pipelines.lakehouse.catalog import ensure_all_namespaces, reset_catalog_cache
    from pipelines.lakehouse.io import read_table, row_count, table_exists
    from pipelines.ops.ensure_iceberg_bucket import ensure_iceberg_bucket
    from pipelines.ops.iceberg_gold_fiscal_pilot import publish_gold

    reset_catalog_cache()
    if not ensure_iceberg_bucket():
        print(json.dumps({"ok": False, "error": "bucket"}))
        return 1
    ensure_all_namespaces(backend="s3")

    reports = [
        publish_gold("public_debt_observation", backends=["s3"]),
        publish_gold("fiscal_result_observation", backends=["s3"]),
    ]

    detail = {}
    ok = True
    for table, model in (
        ("public_debt_observation", "PUBLIC_DEBT_OBSERVATION"),
        ("fiscal_result_observation", "FISCAL_RESULT_OBSERVATION"),
    ):
        exists = table_exists("gold", table, backend="s3")
        n = row_count("gold", table, backend="s3") if exists else 0
        df = read_table("gold", table, limit=1, backend="s3") if exists else None
        models = (
            df["canonical_model"].to_list()
            if df is not None and "canonical_model" in df.columns
            else []
        )
        part_ok = exists and n > 0 and model in models
        ok = ok and part_ok
        detail[table] = {
            "exists": exists,
            "rows": n,
            "canonical_model_ok": model in models,
        }

    out = {
        "ok": ok and all(r.get("ok") for r in reports),
        "phase": 3,
        "publishes": reports,
        "gold": detail,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
