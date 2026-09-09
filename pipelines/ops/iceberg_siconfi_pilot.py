#!/usr/bin/env python3
"""
Fase 4a — SICONFI: silver JSONL → Iceberg silver+gold @ MinIO.

Tabelas:
  silver/gold.public_budget_execution  (de public_budget_execution_siconfi.jsonl)
  silver/gold.personnel_expenditure    (de personnel_expenditure_siconfi.jsonl)

Uso:
  python pipelines/ops/iceberg_siconfi_pilot.py
  python pipelines/ops/iceberg_siconfi_pilot.py --limit 5000 --also-local
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
from pipelines.lakehouse.gold_siconfi import (  # noqa: E402
    to_gold_personnel_expenditure,
    to_gold_public_budget_execution,
)
from pipelines.lakehouse.io import read_table, write_table  # noqa: E402
from pipelines.ops.ensure_iceberg_bucket import ensure_iceberg_bucket  # noqa: E402

LAKE = Path(__import__("os").getenv("LAKE_PATH", ROOT / "data" / "lake"))
FISCAL = LAKE / "silver" / "fiscal"

SOURCES = [
    (
        "public_budget_execution",
        FISCAL / "public_budget_execution_siconfi.jsonl",
        to_gold_public_budget_execution,
    ),
    (
        "personnel_expenditure",
        FISCAL / "personnel_expenditure_siconfi.jsonl",
        to_gold_personnel_expenditure,
    ),
]


def _jsonl_df(path: Path, limit: int | None) -> pl.DataFrame:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
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


def publish(table: str, path: Path, to_gold, *, backends: list[str], limit: int | None) -> dict:
    if not path.is_file():
        return {"table": table, "ok": False, "error": f"missing {path}"}
    silver = _jsonl_df(path, limit)
    gold = to_gold(silver)
    pubs = []
    for b in backends:
        ws = write_table("silver", table, silver, mode="overwrite", backend=b)
        wg = write_table("gold", table, gold, mode="overwrite", backend=b)
        rb = read_table("gold", table, limit=2, backend=b)
        pubs.append(
            {
                "backend": b,
                "silver_write": ws,
                "gold_write": wg,
                "gold_has_model": "canonical_model" in rb.columns,
            }
        )
    return {
        "table": table,
        "ok": all(
            p["silver_write"]["rows"] == silver.height and p["gold_write"]["rows"] == gold.height
            for p in pubs
        ),
        "source_jsonl": str(path),
        "silver_rows": silver.height,
        "gold_rows": gold.height,
        "publishes": pubs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--also-local", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="0 = todas as linhas")
    args = ap.parse_args()
    limit = args.limit or None

    reset_catalog_cache()
    if not ensure_iceberg_bucket():
        print(json.dumps({"ok": False, "error": "bucket"}))
        return 1
    backends = ["s3"] + (["local"] if args.also_local else [])
    ensure_all_namespaces(backend="s3")
    if "local" in backends:
        ensure_all_namespaces(backend="local")

    reports = [
        publish(t, p, fn, backends=backends, limit=limit) for t, p, fn in SOURCES
    ]
    ok = all(r.get("ok") for r in reports)
    print(
        json.dumps(
            {
                "ok": ok,
                "phase": "4a",
                "s3_warehouse": ICEBERG_S3_WAREHOUSE,
                "limit": limit,
                "tables": reports,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
