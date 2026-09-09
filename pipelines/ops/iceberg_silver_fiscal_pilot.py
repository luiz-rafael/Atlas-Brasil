#!/usr/bin/env python3
"""
Fase 2 — piloto Silver fiscal → Iceberg @ MinIO.

Lê JSONL local (continua canônico no disco) e grava tabelas silver.* no
warehouse S3 (bucket atlas-iceberg). Não migra observations em massa.

Uso:
  python pipelines/ops/iceberg_silver_fiscal_pilot.py
  python pipelines/ops/iceberg_silver_fiscal_pilot.py --also-local
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
from pipelines.lakehouse.config import (  # noqa: E402
    ICEBERG_S3_WAREHOUSE,
    iceberg_backend,
)
from pipelines.lakehouse.io import read_table, write_table  # noqa: E402
from pipelines.ops.ensure_iceberg_bucket import ensure_iceberg_bucket  # noqa: E402

LAKE = Path(__import__("os").getenv("LAKE_PATH", ROOT / "data" / "lake"))
FISCAL = LAKE / "silver" / "fiscal"

# Tabelas piloto (pequenas vs 1,9M observations)
PILOTS: list[tuple[str, Path]] = [
    ("public_debt_observation", FISCAL / "public_debt_observation.jsonl"),
    ("fiscal_result_observation", FISCAL / "fiscal_result_observation.jsonl"),
]


def _jsonl_to_df(path: Path) -> pl.DataFrame:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    if not rows:
        return pl.DataFrame()
    # flatten: valores escalares; dict/list → JSON string (Iceberg-friendly)
    flat = []
    for r in rows:
        out = {}
        for k, v in r.items():
            if isinstance(v, (dict, list)):
                out[k] = json.dumps(v, ensure_ascii=False)
            elif v is None:
                out[k] = None
            else:
                out[k] = v
        flat.append(out)
    return pl.DataFrame(flat)


def publish_one(table: str, path: Path, *, backends: list[str]) -> dict:
    if not path.is_file():
        return {"table": table, "ok": False, "error": f"missing {path}"}
    df = _jsonl_to_df(path)
    results = []
    for b in backends:
        w = write_table("silver", table, df, mode="overwrite", backend=b)
        rb = read_table("silver", table, limit=3, backend=b)
        results.append(
            {
                "backend": b,
                "write": w,
                "readback_rows": rb.height,
                "readback_sample_ids": [
                    str(x)
                    for x in (
                        rb["id"].to_list()
                        if "id" in rb.columns
                        else rb.columns[:1]
                    )
                ][:3],
            }
        )
    return {
        "table": f"silver.{table}",
        "source_jsonl": str(path),
        "source_rows": df.height,
        "ok": all(r["write"]["rows"] == df.height for r in results),
        "publishes": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fase 2 piloto Silver fiscal → Iceberg MinIO")
    ap.add_argument(
        "--also-local",
        action="store_true",
        help="Também grava no warehouse file:// local (dual write piloto)",
    )
    args = ap.parse_args()

    reset_catalog_cache()
    if not ensure_iceberg_bucket():
        print(json.dumps({"ok": False, "error": "MinIO bucket atlas-iceberg"}, ensure_ascii=False))
        return 1

    backends = ["s3"]
    if args.also_local:
        backends.append("local")

    ensure_all_namespaces(backend="s3")
    if "local" in backends:
        ensure_all_namespaces(backend="local")

    reports = [publish_one(name, path, backends=backends) for name, path in PILOTS]
    ok = all(r.get("ok") for r in reports)
    out = {
        "ok": ok,
        "phase": 2,
        "note": "JSONL local permanece; Iceberg@MinIO e espelho analitico piloto",
        "default_env_backend": iceberg_backend(),
        "s3_warehouse": ICEBERG_S3_WAREHOUSE,
        "backends": backends,
        "tables": reports,
        "magistrates": "out_of_scope",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
