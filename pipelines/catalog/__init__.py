"""Carrega pipelines/catalog/datasets.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "pipelines" / "catalog" / "datasets.yaml"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    p = path or CATALOG_PATH
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError("PyYAML necessário: pip install pyyaml") from e
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"catálogo inválido: {p}")
    return data


def datasets_by_id(catalog: dict[str, Any] | None = None) -> dict[str, dict]:
    cat = catalog or load_catalog()
    return {d["id"]: d for d in (cat.get("datasets") or []) if d.get("id")}


def get_dataset(dataset_id: str) -> dict[str, Any]:
    d = datasets_by_id().get(dataset_id)
    if not d:
        raise KeyError(f"dataset '{dataset_id}' ausente em {CATALOG_PATH}")
    return d
