"""PyIceberg SqlCatalog — local (file) ou MinIO/S3 (Fase 2)."""

from __future__ import annotations

from functools import lru_cache

from pipelines.lakehouse.config import (
    NAMESPACES,
    catalog_properties,
    ensure_dirs,
    iceberg_backend,
)


@lru_cache(maxsize=4)
def _catalog_for(backend: str):
    from pyiceberg.catalog.sql import SqlCatalog

    ensure_dirs()
    props = catalog_properties(backend=backend)
    # PyArrow S3FileIO — MinIO via s3.* properties (sem s3fs obrigatório)
    props.setdefault("py-io-impl", "pyiceberg.io.pyarrow.PyArrowFileIO")
    return SqlCatalog(f"atlas_{backend}", **props)


def get_catalog(backend: str | None = None):
    return _catalog_for(backend or iceberg_backend())


def reset_catalog_cache() -> None:
    _catalog_for.cache_clear()


def ensure_namespace(name: str, *, backend: str | None = None) -> None:
    cat = get_catalog(backend)
    flat = set()
    for ns in cat.list_namespaces():
        if isinstance(ns, tuple):
            flat.add(ns[0] if len(ns) == 1 else ns)
        else:
            flat.add(ns)
    if name not in flat and (name,) not in flat:
        try:
            cat.create_namespace(name)
        except Exception as e:
            if "already" not in str(e).lower() and "exists" not in str(e).lower():
                raise


def ensure_all_namespaces(*, backend: str | None = None) -> list[str]:
    created = []
    for ns in NAMESPACES:
        ensure_namespace(ns, backend=backend)
        created.append(ns)
    return created


def table_identifier(namespace: str, name: str) -> str:
    return f"{namespace}.{name}"
