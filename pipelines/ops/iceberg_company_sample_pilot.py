#!/usr/bin/env python3
"""
Fase 4b — COMPANY amostra: interseção fila cnpj_interest × companies_latest.

Nunca dump nacional. Só CNPJ 14 já no silver escopado e na fila de interesse.

Uso:
  python pipelines/ops/iceberg_company_sample_pilot.py
  python pipelines/ops/iceberg_company_sample_pilot.py --limit 50 --also-local
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
from pipelines.lakehouse.gold_company import to_gold_company  # noqa: E402
from pipelines.lakehouse.io import read_table, write_table  # noqa: E402
from pipelines.ops.ensure_iceberg_bucket import ensure_iceberg_bucket  # noqa: E402

LAKE = Path(__import__("os").getenv("LAKE_PATH", ROOT / "data" / "lake"))
COMPANIES = LAKE / "silver" / "companies" / "companies_latest.jsonl"
QUEUE = LAKE / "queues" / "cnpj_interest.jsonl"


def load_interest(limit_queue: int | None = None) -> set[str]:
    out: set[str] = set()
    if not QUEUE.is_file():
        return out
    with QUEUE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            cnpj = "".join(ch for ch in str(row.get("cnpj") or "") if ch.isdigit())
            if len(cnpj) == 14:
                out.add(cnpj)
            if limit_queue and len(out) >= limit_queue:
                break
    return out


def load_companies(interest: set[str], limit: int) -> pl.DataFrame:
    rows: list[dict] = []
    with COMPANIES.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            cnpj = "".join(ch for ch in str(r.get("cnpj") or "") if ch.isdigit())
            if len(cnpj) != 14:
                continue
            if interest and cnpj not in interest:
                continue
            r["cnpj"] = cnpj
            # flatten
            flat = {
                k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in r.items()
            }
            rows.append(flat)
            if len(rows) >= limit:
                break
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--also-local", action="store_true")
    ap.add_argument("--limit", type=int, default=50, help="Max COMPANY na amostra")
    args = ap.parse_args()

    reset_catalog_cache()
    if not ensure_iceberg_bucket():
        print(json.dumps({"ok": False, "error": "bucket"}))
        return 1
    if not COMPANIES.is_file():
        print(json.dumps({"ok": False, "error": f"missing {COMPANIES}"}))
        return 1

    interest = load_interest()
    silver = load_companies(interest, args.limit)
    # se interseção vazia, ainda permite amostra do silver escopado (já não é dump nacional)
    discovery = "cnpj_interest_intersection"
    if silver.is_empty() and interest:
        # fallback: silver escopado (50) — ainda não é dump
        silver = load_companies(set(), args.limit)
        discovery = "silver_scoped_fallback"
    gold = to_gold_company(silver)
    if discovery == "silver_scoped_fallback" and not gold.is_empty():
        gold = gold.with_columns(pl.lit(discovery).alias("discovery_channel"))

    backends = ["s3"] + (["local"] if args.also_local else [])
    ensure_all_namespaces(backend="s3")
    if "local" in backends:
        ensure_all_namespaces(backend="local")

    pubs = []
    for b in backends:
        ws = write_table("silver", "company", silver, mode="overwrite", backend=b)
        wg = write_table("gold", "company", gold, mode="overwrite", backend=b)
        rb = read_table("gold", "company", limit=3, backend=b)
        pubs.append(
            {
                "backend": b,
                "silver_write": ws,
                "gold_write": wg,
                "sample_cnpjs": rb["cnpj"].to_list() if "cnpj" in rb.columns else [],
                "canonical_ok": "COMPANY"
                in (rb["canonical_model"].to_list() if "canonical_model" in rb.columns else []),
            }
        )

    ok = (not silver.is_empty()) and all(
        p["silver_write"]["rows"] == silver.height
        and p["gold_write"]["rows"] == gold.height
        and p["canonical_ok"]
        for p in pubs
    )
    print(
        json.dumps(
            {
                "ok": ok,
                "phase": "4b",
                "note": "Amostra escopada; dump nacional proibido",
                "s3_warehouse": ICEBERG_S3_WAREHOUSE,
                "interest_queue_size": len(interest),
                "discovery": discovery,
                "silver_rows": silver.height,
                "gold_rows": gold.height,
                "publishes": pubs,
                "national_dump": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
