"""Lakehouse Iceberg ATLAS (Fase B)."""

from pipelines.lakehouse.catalog import ensure_all_namespaces, get_catalog
from pipelines.lakehouse.io import read_table, row_count, write_table

__all__ = [
    "ensure_all_namespaces",
    "get_catalog",
    "read_table",
    "row_count",
    "write_table",
]
