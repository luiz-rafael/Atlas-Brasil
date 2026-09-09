#!/usr/bin/env python3
"""
Fase 3 — piloto Gold canônico fiscal → Iceberg @ MinIO.

Lê silver Iceberg (backend s3; fallback JSONL local), projeta schema gold
(PUBLIC_DEBT_OBSERVATION / FISCAL_RESULT_OBSERVATION) e grava gold.*.

Uso:
  python pipelines/ops/iceberg_gold_fiscal_pilot.py
  python pipelines/ops/iceberg_gold_fiscal_pilot.py --also-local
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.lakehouse.catalog import ensure_all_namespaces, reset_catalog_cache  # noqa: E402
from pipelines.lakehouse.config import ICEBERG_S3_WAREHOUSE  # noqa: E402
from pipelines.lakehouse.gold_fiscal import (  # noqa: E402
    gold_table_meta,
    to_gold_fiscal_result,
    to_gold_public_debt,
)
from pipelines.lakehouse.io import read_table, table_exists, write_table  # noqa: E402
from pipelines.ops.ensure_iceberg_bucket import ensure_iceberg_bucket  # noqa: E402

LAKE = Path(__import__("os").getenv("LAKE_PATH", ROOT / "data" / "lake"))
FISCAL_JSONL = LAKE / "silver" / "fiscal"

TRANSFORMERS = {
    "public_debt_observation": to_gold_public_debt,
    "fiscal_result_observation": to_gold_fiscal_result,
}


def _jsonl_df(path: Path) -> pl.DataFrame:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    if not rows:
        return pl.DataFrame()
    flat = []
    for r in rows:
        out = {}
        for k, v in r.items():
            if isinstance(v, (dict, list)):
                out[k] = json.dumps(v, ensure_ascii=False)
            else:
                out[k] = v
        flat.append(out)
    return pl.DataFrame(flat)


def load_silver(table: str, *, prefer_backend: str = "s3") -> tuple[pl.DataFrame, str]:
    if table_exists("silver", table, backend=prefer_backend):
        return read_table("silver", table, backend=prefer_backend), f"iceberg:{prefer_backend}"
    path = FISCAL_JSONL / f"{table}.jsonl"
    if path.is_file():
        return _jsonl_df(path), f"jsonl:{path}"
    return pl.DataFrame(), "missing"


def publish_gold(table: str, *, backends: list[str]) -> dict:
    silver, src = load_silver(table)
    if silver.is_empty():
        return {"table": f"gold.{table}", "ok": False, "error": f"no silver ({src})"}

    transform = TRANSFORMERS[table]
    gold = transform(silver)
    publishes = []
    for b in backends:
        w = write_table("gold", table, gold, mode="overwrite", backend=b)
        rb = read_table("gold", table, limit=3, backend=b)
        publishes.append(
            {
                "backend": b,
                "write": w,
                "readback_rows": rb.height,
                "has_canonical_model": "canonical_model" in rb.columns,
                "sample_ids": rb["id"].to_list() if "id" in rb.columns else [],
            }
        )
    return {
        "table": f"gold.{table}",
        "ok": all(p["write"]["rows"] == gold.height for p in publishes),
        "source": src,
        "silver_rows": silver.height,
        "gold_rows": gold.height,
        "meta": gold_table_meta(table),
        "publishes": publishes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fase 3 piloto Gold fiscal → Iceberg MinIO")
    ap.add_argument("--also-local", action="store_true")
    args = ap.parse_args()

    reset_catalog_cache()
    if not ensure_iceberg_bucket():
        print(json.dumps({"ok": False, "error": "MinIO bucket"}, ensure_ascii=False))
        return 1

    backends = ["s3"]
    if args.also_local:
        backends.append("local")

    ensure_all_namespaces(backend="s3")
    if "local" in backends:
        ensure_all_namespaces(backend="local")

    reports = [publish_gold(t, backends=backends) for t in TRANSFORMERS]
    ok = all(r.get("ok") for r in reports)
    out = {
        "ok": ok,
        "phase": 3,
        "note": "Gold canonico piloto; serving Postgres e JSONL/kb.json intactos",
        "s3_warehouse": ICEBERG_S3_WAREHOUSE,
        "backends": backends,
        "tables": reports,
        "magistrates": "out_of_scope",
        "company_mass": "out_of_scope",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
