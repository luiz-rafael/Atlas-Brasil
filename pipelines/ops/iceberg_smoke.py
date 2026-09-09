#!/usr/bin/env python3
"""Smoke Fase B: bootstrap + write/read Iceberg com contagem > 0."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    import polars as pl

    from pipelines.lakehouse.bootstrap import main as bootstrap_main
    from pipelines.lakehouse.config import CATALOG_DB, WAREHOUSE
    from pipelines.lakehouse.io import read_table, row_count, write_table

    bootstrap_main()

    sample = pl.DataFrame(
        {
            "observation_id": ["smoke_obs_1", "smoke_obs_2"],
            "indicator_id": ["ind_smoke", "ind_smoke"],
            "territory_id": ["uf_SP", "uf_RJ"],
            "reference_year": [2024, 2024],
            "value": [1.0, 2.0],
            "unit": ["n", "n"],
            "source_id": ["smoke", "smoke"],
            "dataset_id": ["smoke.ds", "smoke.ds"],
            "geographic_level": ["uf", "uf"],
            "retrieved_at": ["2026-01-01", "2026-01-01"],
            "raw_json": ["", ""],
        }
    )
    w = write_table("bronze", "indicadores_observations", sample, mode="overwrite")
    n = row_count("bronze", "indicadores_observations")
    df = read_table("bronze", "indicadores_observations", limit=5)

    docs = pl.DataFrame(
        {
            "id": ["doc_smoke_1"],
            "fonte": ["SMOKE"],
            "orgao": ["test"],
            "titulo": ["Smoke doc"],
            "url": ["https://example.com"],
            "nivel_fonte": ["1_primaria"],
            "collected_at": ["2026-01-01"],
            "source_system": ["smoke"],
        }
    )
    wd = write_table("silver", "documentos", docs, mode="overwrite")
    nd = row_count("silver", "documentos")

    ok = n > 0 and nd > 0
    out = {
        "ok": ok,
        "catalog": str(CATALOG_DB),
        "warehouse": str(WAREHOUSE),
        "write_bronze": w,
        "bronze_rows": n,
        "bronze_sample": df.to_dicts(),
        "write_silver_docs": wd,
        "silver_documentos_rows": nd,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
