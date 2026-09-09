#!/usr/bin/env python3
"""
Fase 4 residual — PNCP CONTRACT + TSE CAMPAIGN_EXPENSE + Receita PUBLIC_REVENUE
→ Iceberg silver+gold @ MinIO.

Uso:
  python pipelines/ops/iceberg_phase4_residual_pilot.py
  python pipelines/ops/iceberg_phase4_residual_pilot.py --tse-limit 20000
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
from pipelines.lakehouse.gold_campaign import to_gold_campaign_expense  # noqa: E402
from pipelines.lakehouse.gold_contract import to_gold_contract  # noqa: E402
from pipelines.lakehouse.gold_revenue import to_gold_public_revenue  # noqa: E402
from pipelines.lakehouse.io import read_table, write_table  # noqa: E402
from pipelines.ops.ensure_iceberg_bucket import ensure_iceberg_bucket  # noqa: E402

LAKE = Path(__import__("os").getenv("LAKE_PATH", ROOT / "data" / "lake"))


def _jsonl_df(path: Path, limit: int | None = None) -> pl.DataFrame:
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
        flat.append(
            {
                k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in r.items()
            }
        )
    return pl.DataFrame(flat)


def publish(
    silver_name: str,
    gold_name: str,
    path: Path,
    to_gold,
    *,
    backends: list[str],
    limit: int | None,
) -> dict:
    if not path.is_file():
        return {"ok": False, "error": f"missing {path}", "table": gold_name}
    silver = _jsonl_df(path, limit)
    gold = to_gold(silver)
    pubs = []
    for b in backends:
        ws = write_table("silver", silver_name, silver, mode="overwrite", backend=b)
        wg = write_table("gold", gold_name, gold, mode="overwrite", backend=b)
        rb = read_table("gold", gold_name, limit=2, backend=b)
        pubs.append(
            {
                "backend": b,
                "silver_rows": ws["rows"],
                "gold_rows": wg["rows"],
                "canonical_model": (
                    rb["canonical_model"].to_list()[0]
                    if "canonical_model" in rb.columns and rb.height
                    else None
                ),
            }
        )
    return {
        "ok": all(p["gold_rows"] == gold.height and gold.height > 0 for p in pubs),
        "source": str(path),
        "silver_table": f"silver.{silver_name}",
        "gold_table": f"gold.{gold_name}",
        "rows": gold.height,
        "publishes": pubs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--also-local", action="store_true")
    ap.add_argument("--tse-limit", type=int, default=0, help="0=todas despesas silver")
    args = ap.parse_args()

    reset_catalog_cache()
    if not ensure_iceberg_bucket():
        print(json.dumps({"ok": False, "error": "bucket"}))
        return 1
    backends = ["s3"] + (["local"] if args.also_local else [])
    ensure_all_namespaces(backend="s3")
    if "local" in backends:
        ensure_all_namespaces(backend="local")

    tse_limit = args.tse_limit or None
    jobs = [
        publish(
            "contract",
            "contract",
            LAKE / "silver" / "contratos" / "contratos_latest.jsonl",
            to_gold_contract,
            backends=backends,
            limit=None,
        ),
        publish(
            "campaign_expense",
            "campaign_expense",
            LAKE / "silver" / "campanhas" / "despesas_fornecedor_latest.jsonl",
            to_gold_campaign_expense,
            backends=backends,
            limit=tse_limit,
        ),
        publish(
            "public_revenue_observation",
            "public_revenue_observation",
            LAKE / "bronze" / "receita_arrecadacao" / "2026-09-07" / "arrecadacao_extract.jsonl",
            to_gold_public_revenue,
            backends=backends,
            limit=None,
        ),
    ]
    # fallback receita: latest day folder
    if not jobs[2].get("ok"):
        base = LAKE / "bronze" / "receita_arrecadacao"
        days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True) if base.exists() else []
        for d in days:
            cand = d / "arrecadacao_extract.jsonl"
            if cand.is_file():
                jobs[2] = publish(
                    "public_revenue_observation",
                    "public_revenue_observation",
                    cand,
                    to_gold_public_revenue,
                    backends=backends,
                    limit=None,
                )
                break

    ok = all(j.get("ok") for j in jobs)
    print(
        json.dumps(
            {
                "ok": ok,
                "phase": "4_residual",
                "s3_warehouse": ICEBERG_S3_WAREHOUSE,
                "tables": jobs,
                "magistrates": "out_of_scope",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
