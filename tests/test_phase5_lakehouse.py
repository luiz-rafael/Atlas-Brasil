"""Fase 5 — testes de papéis de storage / Iceberg backend (sem MinIO obrigatório)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_minio_enabled_via_storage_backend(monkeypatch):
    monkeypatch.delenv("ATLAS_MINIO_ENABLED", raising=False)
    monkeypatch.setenv("ATLAS_STORAGE_BACKEND", "dual")
    from pipelines import raw_store

    assert raw_store.minio_enabled() is True


def test_iceberg_backend_default_local(monkeypatch):
    monkeypatch.delenv("ATLAS_ICEBERG_BACKEND", raising=False)
    from pipelines.lakehouse.config import iceberg_backend

    assert iceberg_backend() == "local"


def test_iceberg_catalog_properties_local(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_ICEBERG_BACKEND", "local")
    monkeypatch.setenv("ATLAS_ICEBERG_ROOT", str(tmp_path / "iceberg"))
    monkeypatch.setenv("ATLAS_ICEBERG_WAREHOUSE", str(tmp_path / "iceberg" / "wh"))
    monkeypatch.setenv("ATLAS_ICEBERG_CATALOG", str(tmp_path / "iceberg" / "c.db"))
    from pipelines.lakehouse.catalog import reset_catalog_cache
    from pipelines.lakehouse.config import catalog_properties

    reset_catalog_cache()
    props = catalog_properties(backend="local")
    assert props["warehouse"].startswith("file:")
    assert "sqlite" in props["uri"]


def test_iceberg_catalog_properties_s3(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_ICEBERG_BACKEND", "s3")
    monkeypatch.setenv("ATLAS_ICEBERG_ROOT", str(tmp_path / "iceberg"))
    monkeypatch.setenv("ATLAS_ICEBERG_CATALOG_S3", str(tmp_path / "iceberg" / "c.s3.db"))
    monkeypatch.setenv("ATLAS_ICEBERG_S3_WAREHOUSE", "s3://atlas-iceberg/warehouse")
    from pipelines.lakehouse.catalog import reset_catalog_cache
    from pipelines.lakehouse.config import catalog_properties

    reset_catalog_cache()
    props = catalog_properties(backend="s3")
    assert props["warehouse"] == "s3://atlas-iceberg/warehouse"
    assert props["s3.path-style-access"] == "true"
    assert "s3.endpoint" in props


def test_phase5_local_iceberg_roundtrip(monkeypatch, tmp_path):
    """Smoke Iceberg local isolado (CI sem MinIO)."""
    monkeypatch.setenv("ATLAS_ICEBERG_BACKEND", "local")
    monkeypatch.setenv("ATLAS_ICEBERG_ROOT", str(tmp_path / "iceberg"))
    monkeypatch.setenv("ATLAS_ICEBERG_WAREHOUSE", str(tmp_path / "iceberg" / "wh"))
    monkeypatch.setenv("ATLAS_ICEBERG_CATALOG", str(tmp_path / "iceberg" / "c.db"))
    import polars as pl

    from pipelines.lakehouse.catalog import ensure_all_namespaces, reset_catalog_cache
    from pipelines.lakehouse.io import read_table, write_table

    reset_catalog_cache()
    ensure_all_namespaces(backend="local")
    df = pl.DataFrame({"id": ["t1"], "v": [1.0]})
    w = write_table("gold", "phase5_unit", df, mode="overwrite", backend="local")
    assert w["rows"] == 1
    rb = read_table("gold", "phase5_unit", backend="local")
    assert rb.height == 1
    assert rb["id"][0] == "t1"
