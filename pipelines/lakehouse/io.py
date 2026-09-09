"""Leitura/escrita Iceberg via Polars/PyArrow."""

from __future__ import annotations

from typing import Any, Literal

import pyarrow as pa

from pipelines.lakehouse.catalog import (
    ensure_namespace,
    get_catalog,
    table_identifier,
)
from pipelines.lakehouse.config import iceberg_backend

Mode = Literal["overwrite", "append"]


def _to_arrow(df) -> pa.Table:
    if isinstance(df, pa.Table):
        return df
    if hasattr(df, "to_arrow"):
        return df.to_arrow()
    raise TypeError(f"unsupported frame type: {type(df)}")


def write_table(
    namespace: str,
    name: str,
    df,
    *,
    mode: Mode = "overwrite",
    backend: str | None = None,
) -> dict[str, Any]:
    """
    Grava DataFrame Polars/Arrow em Iceberg.
    mode=overwrite: recreate table; append: append rows (cria se não existir).
    backend: local|s3 — None = ATLAS_ICEBERG_BACKEND
    """
    b = backend or iceberg_backend()
    ensure_namespace(namespace, backend=b)
    cat = get_catalog(b)
    ident = table_identifier(namespace, name)
    arrow = _to_arrow(df)
    fields = []
    for field in arrow.schema:
        if pa.types.is_null(field.type):
            fields.append(pa.field(field.name, pa.string(), nullable=True))
        else:
            fields.append(field)
    arrow = arrow.cast(pa.schema(fields))

    if arrow.num_rows == 0 and mode == "append":
        return {
            "table": ident,
            "rows": 0,
            "mode": mode,
            "skipped_empty": True,
            "backend": b,
        }

    try:
        table = cat.load_table(ident)
        exists = True
    except Exception:
        exists = False
        table = None

    if not exists:
        table = cat.create_table(ident, schema=arrow.schema)
        if arrow.num_rows > 0:
            table.append(arrow)
    elif mode == "overwrite":
        cat.drop_table(ident)
        table = cat.create_table(ident, schema=arrow.schema)
        if arrow.num_rows > 0:
            table.append(arrow)
    else:
        assert table is not None
        table.append(arrow)

    return {
        "table": ident,
        "rows": arrow.num_rows,
        "mode": mode,
        "columns": arrow.column_names,
        "backend": b,
        "warehouse": "s3" if b == "s3" else "local",
    }


def read_table(
    namespace: str,
    name: str,
    *,
    limit: int | None = None,
    backend: str | None = None,
):
    """Retorna Polars DataFrame da tabela Iceberg."""
    import polars as pl

    b = backend or iceberg_backend()
    cat = get_catalog(b)
    ident = table_identifier(namespace, name)
    table = cat.load_table(ident)
    arrow = table.scan().to_arrow()
    df = pl.from_arrow(arrow)
    if limit is not None:
        df = df.head(limit)
    return df


def table_exists(namespace: str, name: str, *, backend: str | None = None) -> bool:
    b = backend or iceberg_backend()
    cat = get_catalog(b)
    ident = table_identifier(namespace, name)
    try:
        cat.load_table(ident)
        return True
    except Exception:
        return False


def row_count(namespace: str, name: str, *, backend: str | None = None) -> int:
    df = read_table(namespace, name, backend=backend)
    return df.height
