"""Testes do adapter de storage e mapa canônico."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_storage_backend_default_local(monkeypatch):
    monkeypatch.delenv("ATLAS_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("ATLAS_MINIO_ENABLED", raising=False)
    from pipelines.storage.backend import storage_backend_name, get_storage

    assert storage_backend_name() == "local"
    sto = get_storage()
    assert sto.name == "local"


def test_storage_backend_dual_when_minio_flag(monkeypatch):
    monkeypatch.delenv("ATLAS_STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("ATLAS_MINIO_ENABLED", "1")
    from pipelines.storage.backend import storage_backend_name

    assert storage_backend_name() == "dual"


def test_local_write_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_STORAGE_BACKEND", "local")
    from pipelines.storage.backend import LocalStorage

    sto = LocalStorage(root=tmp_path)
    obj = sto.write_raw(
        source_id="test_src",
        run_id="run1",
        filename="sample.json",
        data=b'{"ok":true}',
        meta={"dataset_id": "test"},
        content_type="application/json",
    )
    assert obj.backend == "local"
    assert obj.local_path
    assert Path(obj.local_path).exists()
    assert sto.exists(obj.key)
    assert sto.read_raw(obj.key) == b'{"ok":true}'


def test_canonical_map_priority_datasets():
    from pipelines.catalog.canonical import dataset_canonical, load_canonical_map

    m = load_canonical_map()
    assert "datasets" in m
    assert "domains" in m
    assert len(m["domains"]) == 6
    cnpj = dataset_canonical("cnpj_rfb")
    assert cnpj
    assert cnpj["canonical_model"] == "COMPANY"
    assert cnpj["atlas_domain"] == "empresas_organizacoes"
    debt = dataset_canonical("tesouro_public_debt")
    assert debt["canonical_model"] == "PUBLIC_DEBT_OBSERVATION"
