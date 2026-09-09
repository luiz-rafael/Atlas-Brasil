"""Paths e env do lakehouse Iceberg.

Backends:
  local — warehouse em data/lake/iceberg/warehouse (compat)
  s3    — warehouse em MinIO (Fase 2 — alvo Silver)

Env:
  ATLAS_ICEBERG_BACKEND=local|s3
  ATLAS_ICEBERG_S3_WAREHOUSE=s3://atlas-iceberg/warehouse
  ATLAS_MINIO_* (endpoint, keys)
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))

ICEBERG_ROOT = Path(os.getenv("ATLAS_ICEBERG_ROOT", LAKE / "iceberg"))
WAREHOUSE_LOCAL = Path(
    os.getenv("ATLAS_ICEBERG_WAREHOUSE", ICEBERG_ROOT / "warehouse")
)
CATALOG_DB_LOCAL = Path(
    os.getenv("ATLAS_ICEBERG_CATALOG", ICEBERG_ROOT / "catalog.db")
)
CATALOG_DB_S3 = Path(
    os.getenv("ATLAS_ICEBERG_CATALOG_S3", ICEBERG_ROOT / "catalog.s3.db")
)

NAMESPACES = ("bronze", "silver", "gold")

ALSO_PARQUET = os.getenv("ATLAS_ICEBERG_ALSO_PARQUET", "1").lower() in (
    "1",
    "true",
    "yes",
)

# Compat: código antigo importava WAREHOUSE / CATALOG_DB
WAREHOUSE = WAREHOUSE_LOCAL
CATALOG_DB = CATALOG_DB_LOCAL

ICEBERG_S3_BUCKET = os.getenv("ATLAS_ICEBERG_S3_BUCKET", "atlas-iceberg")
ICEBERG_S3_WAREHOUSE = os.getenv(
    "ATLAS_ICEBERG_S3_WAREHOUSE",
    f"s3://{ICEBERG_S3_BUCKET}/warehouse",
)


def iceberg_backend() -> str:
    b = os.getenv("ATLAS_ICEBERG_BACKEND", "local").strip().lower()
    return b if b in ("local", "s3") else "local"


def minio_endpoint() -> str:
    return os.getenv("ATLAS_MINIO_ENDPOINT", "http://127.0.0.1:9000")


def minio_access_key() -> str:
    return os.getenv("ATLAS_MINIO_ACCESS_KEY", "atlasminio")


def minio_secret_key() -> str:
    return os.getenv("ATLAS_MINIO_SECRET_KEY", "atlasbrasilminio")


def minio_region() -> str:
    return os.getenv("ATLAS_MINIO_REGION", "us-east-1")


def ensure_dirs() -> None:
    WAREHOUSE_LOCAL.mkdir(parents=True, exist_ok=True)
    ICEBERG_ROOT.mkdir(parents=True, exist_ok=True)
    CATALOG_DB_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_DB_S3.parent.mkdir(parents=True, exist_ok=True)


def catalog_properties(*, backend: str | None = None) -> dict:
    """Propriedades SqlCatalog conforme backend (local|s3)."""
    ensure_dirs()
    b = (backend or iceberg_backend()).strip().lower()
    if b == "s3":
        uri = f"sqlite:///{CATALOG_DB_S3.resolve().as_posix()}"
        return {
            "uri": uri,
            "warehouse": ICEBERG_S3_WAREHOUSE.rstrip("/"),
            "s3.endpoint": minio_endpoint(),
            "s3.access-key-id": minio_access_key(),
            "s3.secret-access-key": minio_secret_key(),
            "s3.region": minio_region(),
            "s3.path-style-access": "true",
        }

    wh = WAREHOUSE_LOCAL.resolve().as_posix()
    if len(wh) >= 2 and wh[1] == ":":
        warehouse = f"file://{wh}"
    else:
        warehouse = f"file://{wh}" if wh.startswith("/") else f"file:///{wh}"
    uri = f"sqlite:///{CATALOG_DB_LOCAL.resolve().as_posix()}"
    return {"uri": uri, "warehouse": warehouse}
