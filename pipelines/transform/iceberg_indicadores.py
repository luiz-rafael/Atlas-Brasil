#!/usr/bin/env python3
"""Polars → Iceberg: indicadores (observations) + CAGED UF (piloto Fase B)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.lakehouse.bootstrap import main as bootstrap_main  # noqa: E402
from pipelines.lakehouse.config import LAKE  # noqa: E402
from pipelines.lakehouse.io import write_table  # noqa: E402

OBS_JSONL = Path(
    os.getenv(
        "ATLAS_OBS_JSONL",
        LAKE / "silver" / "indicadores" / "observations_latest.jsonl",
    )
)
CAGED_GLOB = os.getenv(
    "ATLAS_CAGED_JSONL_GLOB",
    str(LAKE / "bronze" / "caged" / "*" / "caged_mov_uf_extract.jsonl"),
)
MAX_ROWS = int(os.getenv("ATLAS_ICEBERG_MAX_ROWS", "0") or "0")


def _load_observations():
    import polars as pl

    if not OBS_JSONL.exists():
        raise FileNotFoundError(f"observations ausente: {OBS_JSONL}")

    df = pl.read_ndjson(OBS_JSONL)
    if MAX_ROWS > 0:
        df = df.head(MAX_ROWS)

    bronze_cols = [
        "observation_id",
        "indicator_id",
        "territory_id",
        "reference_year",
        "value",
        "unit",
        "source_id",
        "dataset_id",
        "geographic_level",
        "retrieved_at",
    ]
    for c in bronze_cols:
        if c not in df.columns:
            df = df.with_columns(pl.lit(None).alias(c))

    bronze = df.select(
        [
            pl.col("observation_id").cast(pl.Utf8),
            pl.col("indicator_id").cast(pl.Utf8),
            pl.col("territory_id").cast(pl.Utf8),
            pl.col("reference_year").cast(pl.Int64),
            pl.col("value").cast(pl.Float64),
            pl.col("unit").cast(pl.Utf8),
            pl.col("source_id").cast(pl.Utf8),
            pl.col("dataset_id").cast(pl.Utf8),
            pl.col("geographic_level").cast(pl.Utf8),
            pl.col("retrieved_at").cast(pl.Utf8),
            pl.lit("").cast(pl.Utf8).alias("raw_json"),
        ]
    )

    silver = bronze.select(
        [
            "observation_id",
            "indicator_id",
            "territory_id",
            "reference_year",
            "value",
            "unit",
            "source_id",
            "geographic_level",
        ]
    )
    return bronze, silver


def _gold_uf_latest(silver):
    import polars as pl

    uf = silver.filter(pl.col("territory_id").str.starts_with("uf_"))
    if uf.height == 0:
        return uf.select(
            [
                "territory_id",
                "indicator_id",
                "reference_year",
                "value",
                "unit",
                "source_id",
            ]
        )
    ranked = uf.with_columns(
        pl.col("reference_year")
        .rank(method="ordinal", descending=True)
        .over(["territory_id", "indicator_id"])
        .alias("_rk")
    )
    return (
        ranked.filter(pl.col("_rk") == 1)
        .drop("_rk")
        .select(
            [
                "territory_id",
                "indicator_id",
                "reference_year",
                "value",
                "unit",
                "source_id",
            ]
        )
    )


def _caged_paths() -> list[Path]:
    if "*" in CAGED_GLOB:
        return sorted((LAKE / "bronze" / "caged").glob("*/caged_mov_uf_extract.jsonl"))
    p = Path(CAGED_GLOB)
    return [p] if p.exists() else []


def _load_caged_flat():
    import polars as pl

    paths = _caged_paths()
    rows: list[dict] = []
    for path in paths:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                metrics = rec.get("uf_metrics") or {}
                for uf, m in metrics.items():
                    rows.append(
                        {
                            "competencia": str(rec.get("competencia") or ""),
                            "ano": int(rec["ano"]) if rec.get("ano") is not None else None,
                            "mes": int(rec["mes"]) if rec.get("mes") is not None else None,
                            "uf": str(uf),
                            "admissoes": int((m or {}).get("admissoes") or 0),
                            "desligamentos": int((m or {}).get("desligamentos") or 0),
                            "saldo": int((m or {}).get("saldo") or 0),
                            "retrieved_at": str(rec.get("retrieved_at") or ""),
                            "file": str(path),
                        }
                    )
    if not rows:
        return pl.DataFrame(
            schema={
                "competencia": pl.Utf8,
                "ano": pl.Int32,
                "mes": pl.Int32,
                "uf": pl.Utf8,
                "admissoes": pl.Int64,
                "desligamentos": pl.Int64,
                "saldo": pl.Int64,
                "retrieved_at": pl.Utf8,
                "file": pl.Utf8,
            }
        )
    df = pl.DataFrame(rows).with_columns(
        [
            pl.col("ano").cast(pl.Int64),
            pl.col("mes").cast(pl.Int64),
            pl.col("admissoes").cast(pl.Int64),
            pl.col("desligamentos").cast(pl.Int64),
            pl.col("saldo").cast(pl.Int64),
        ]
    )
    if MAX_ROWS > 0:
        df = df.head(MAX_ROWS)
    return df


def main() -> int:
    bootstrap_main()
    bronze, silver = _load_observations()
    gold = _gold_uf_latest(silver)
    caged = _load_caged_flat()

    results = [
        write_table("bronze", "indicadores_observations", bronze, mode="overwrite"),
        write_table("silver", "indicadores_observations", silver, mode="overwrite"),
        write_table("gold", "indicadores_uf_latest", gold, mode="overwrite"),
        write_table("bronze", "caged_mov_uf", caged, mode="overwrite"),
    ]
    print(json.dumps({"ok": True, "writes": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
