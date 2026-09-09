#!/usr/bin/env python3
"""Carrega pipelines/catalog/canonical_map.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "pipelines" / "catalog" / "canonical_map.yaml"


def load_canonical_map() -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        return {"datasets": {}, "domains": {}}
    if not MAP_PATH.exists():
        return {"datasets": {}, "domains": {}}
    data = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8")) or {}
    return data


def dataset_canonical(dataset_id: str) -> dict[str, Any] | None:
    m = load_canonical_map()
    return (m.get("datasets") or {}).get(dataset_id)


def require_domain(dataset_id: str) -> str:
    info = dataset_canonical(dataset_id)
    if not info or not info.get("atlas_domain"):
        raise KeyError(
            f"Dataset {dataset_id} sem atlas_domain em canonical_map.yaml — "
            "toda fonte deve mapear para um dos 6 domínios."
        )
    return str(info["atlas_domain"])
