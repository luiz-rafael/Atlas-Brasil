#!/usr/bin/env python3
"""
Pipeline lakehouse bronze -> silver -> gold (Polars).
Fase B: grava também Iceberg (silver.documentos / gold.documentos_curados).
Parquet espelho opcional via ATLAS_ICEBERG_ALSO_PARQUET=1 (default).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
BRONZE = LAKE / "bronze"
SILVER = LAKE / "silver"
GOLD = LAKE / "gold"


def main() -> int:
    try:
        import polars as pl
    except ImportError:
        print("pip install -r pipelines/requirements-lakehouse.txt", file=sys.stderr)
        return 2

    from pipelines.lakehouse.config import ALSO_PARQUET
    from pipelines.lakehouse.io import write_table

    SILVER.mkdir(parents=True, exist_ok=True)
    GOLD.mkdir(parents=True, exist_ok=True)

    rows = []
    for src in ("stf", "tse", "dou"):
        folder = BRONZE / src
        if not folder.exists():
            continue
        for f in folder.glob("*.json"):
            rec = json.loads(f.read_text(encoding="utf-8"))
            rows.append(
                {
                    "id": rec.get("id"),
                    "fonte": rec.get("fonte") or src.upper(),
                    "orgao": rec.get("orgao"),
                    "titulo": rec.get("titulo"),
                    "url": rec.get("url"),
                    "nivel_fonte": rec.get("nivel_fonte"),
                    "collected_at": rec.get("collected_at"),
                    "source_system": src,
                }
            )

    kb_path = ROOT / "data" / "atlas-brasil-kb-v2.json"
    if kb_path.exists():
        kb = json.loads(kb_path.read_text(encoding="utf-8"))
        for d in kb.get("documentos") or []:
            rows.append(
                {
                    "id": d.get("id"),
                    "fonte": "KB",
                    "orgao": d.get("orgao"),
                    "titulo": d.get("titulo"),
                    "url": d.get("url") or d.get("url_ref"),
                    "nivel_fonte": d.get("nivel_fonte"),
                    "collected_at": d.get("data"),
                    "source_system": "kb",
                }
            )

    if not rows:
        print("sem documentos")
        return 1

    df = pl.DataFrame(rows).unique(subset=["id"], keep="first").with_columns(
        [
            pl.col("id").cast(pl.Utf8),
            pl.col("fonte").cast(pl.Utf8),
            pl.col("orgao").cast(pl.Utf8),
            pl.col("titulo").cast(pl.Utf8),
            pl.col("url").cast(pl.Utf8),
            pl.col("nivel_fonte").cast(pl.Utf8),
            pl.col("collected_at").cast(pl.Utf8),
            pl.col("source_system").cast(pl.Utf8),
        ]
    )

    gold = (
        df.filter(pl.col("url").is_not_null())
        .with_columns(
            [
                pl.col("titulo").str.len_chars().cast(pl.Int64).alias("titulo_len"),
                (pl.col("nivel_fonte") == "1_primaria").alias("is_primary"),
            ]
        )
        .select(["id", "fonte", "titulo", "url", "is_primary", "titulo_len"])
        .sort("fonte", "id")
    )

    ice_silver = write_table("silver", "documentos", df, mode="overwrite")
    ice_gold = write_table(
        "gold",
        "documentos_curados",
        gold,
        mode="overwrite",
    )

    silver_path = SILVER / "documentos.parquet"
    gold_path = GOLD / "documentos_curados.parquet"
    if ALSO_PARQUET:
        df.write_parquet(silver_path)
        gold.write_parquet(gold_path)

    manifest = {
        "silver_rows": df.height,
        "gold_rows": gold.height,
        "by_fonte": df.group_by("fonte").len().to_dicts(),
        "silver": str(silver_path) if ALSO_PARQUET else None,
        "gold": str(gold_path) if ALSO_PARQUET else None,
        "iceberg": {"silver": ice_silver, "gold": ice_gold},
        "also_parquet": ALSO_PARQUET,
    }
    (GOLD / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
