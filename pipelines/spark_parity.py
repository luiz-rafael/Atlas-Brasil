#!/usr/bin/env python3
"""
Paridade Spark (Fase 3): lê o mesmo contrato Parquet do lake.
Se pyspark estiver instalado, agrega via Spark; senão usa Polars (mesmo output).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
GOLD = LAKE / "gold" / "documentos_curados.parquet"
OUT = LAKE / "gold" / "spark_parity_agg.json"


def main() -> int:
    if not GOLD.exists():
        print("rode pipelines/lake_polars.py antes", file=sys.stderr)
        return 1
    try:
        from pyspark.sql import SparkSession

        spark = (
            SparkSession.builder.master("local[*]")
            .appName("atlas-fase3")
            .config("spark.driver.memory", "1g")
            .getOrCreate()
        )
        df = spark.read.parquet(str(GOLD))
        agg = df.groupBy("fonte").count().collect()
        result = {
            "engine": "pyspark",
            "by_fonte": [{"fonte": r["fonte"], "count": r["count"]} for r in agg],
            "total": df.count(),
        }
        spark.stop()
    except Exception:
        import polars as pl

        df = pl.read_parquet(GOLD)
        result = {
            "engine": "polars_parity",
            "by_fonte": df.group_by("fonte").len().rename({"len": "count"}).to_dicts(),
            "total": df.height,
            "note": "pyspark opcional — contrato Parquet idêntico",
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
