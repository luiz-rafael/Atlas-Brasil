#!/usr/bin/env python3
"""Cria namespaces bronze/silver/gold e (opcional) tabelas vazias piloto."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pyarrow as pa

from pipelines.lakehouse.catalog import ensure_all_namespaces, get_catalog
from pipelines.lakehouse.config import CATALOG_DB, WAREHOUSE
from pipelines.lakehouse.io import write_table


PILOT_SCHEMAS: dict[tuple[str, str], pa.Schema] = {
    ("bronze", "indicadores_observations"): pa.schema(
        [
            ("observation_id", pa.string()),
            ("indicator_id", pa.string()),
            ("territory_id", pa.string()),
            ("reference_year", pa.int64()),
            ("value", pa.float64()),
            ("unit", pa.string()),
            ("source_id", pa.string()),
            ("dataset_id", pa.string()),
            ("geographic_level", pa.string()),
            ("retrieved_at", pa.string()),
            ("raw_json", pa.string()),
        ]
    ),
    ("bronze", "caged_mov_uf"): pa.schema(
        [
            ("competencia", pa.string()),
            ("ano", pa.int64()),
            ("mes", pa.int64()),
            ("uf", pa.string()),
            ("admissoes", pa.int64()),
            ("desligamentos", pa.int64()),
            ("saldo", pa.int64()),
            ("retrieved_at", pa.string()),
            ("file", pa.string()),
        ]
    ),
    ("silver", "indicadores_observations"): pa.schema(
        [
            ("observation_id", pa.string()),
            ("indicator_id", pa.string()),
            ("territory_id", pa.string()),
            ("reference_year", pa.int64()),
            ("value", pa.float64()),
            ("unit", pa.string()),
            ("source_id", pa.string()),
            ("geographic_level", pa.string()),
        ]
    ),
    ("silver", "documentos"): pa.schema(
        [
            ("id", pa.string()),
            ("fonte", pa.string()),
            ("orgao", pa.string()),
            ("titulo", pa.string()),
            ("url", pa.string()),
            ("nivel_fonte", pa.string()),
            ("collected_at", pa.string()),
            ("source_system", pa.string()),
        ]
    ),
    ("gold", "indicadores_uf_latest"): pa.schema(
        [
            ("territory_id", pa.string()),
            ("indicator_id", pa.string()),
            ("reference_year", pa.int64()),
            ("value", pa.float64()),
            ("unit", pa.string()),
            ("source_id", pa.string()),
        ]
    ),
    ("gold", "documentos_curados"): pa.schema(
        [
            ("id", pa.string()),
            ("fonte", pa.string()),
            ("titulo", pa.string()),
            ("url", pa.string()),
            ("is_primary", pa.bool_()),
            ("titulo_len", pa.int64()),
        ]
    ),
}


def main() -> int:
    ns = ensure_all_namespaces()
    cat = get_catalog()
    print(f"catalog={CATALOG_DB}")
    print(f"warehouse={WAREHOUSE}")
    print(f"namespaces={ns}")

    # tabelas vazias só se ainda não existirem
    for (namespace, name), schema in PILOT_SCHEMAS.items():
        ident = f"{namespace}.{name}"
        try:
            cat.load_table(ident)
            print(f"  exists {ident}")
        except Exception:
            empty = pa.Table.from_pylist([], schema=schema)
            # create via write overwrite of empty — some catalogs dislike 0 rows;
            # create_table directly
            cat.create_table(ident, schema=schema)
            print(f"  created {ident}")

    print("OK bootstrap Iceberg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
