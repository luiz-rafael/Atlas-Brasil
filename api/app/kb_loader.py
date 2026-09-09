from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


def _candidates() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    env = os.getenv("KB_PATH", "").strip()
    paths: list[Path] = []
    # Preferir gold coletado; KB_PATH so se apontar para gold/active
    preferred = [
        root / "data" / "atlas-brasil-kb-gold.json",
        root / "data" / "atlas-brasil-kb-active.json",
        root / "data" / "lake" / "gold" / "kb.json",
    ]
    if env:
        ep = Path(env).resolve()
        # KB_PATH legado manual so se gold ainda nao existir
        if ep.is_file() and (
            "gold" in ep.name or "active" in ep.name or not preferred[0].is_file()
        ):
            paths.append(ep)
    paths.extend(preferred)
    paths.append(root / "data" / "atlas-brasil-kb-v2.json")
    # dedupe preservando ordem
    seen = set()
    out = []
    for p in paths:
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(p)
    return out


@lru_cache(maxsize=1)
def load_kb() -> dict[str, Any]:
    for path in _candidates():
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("meta", {})["_loaded_from"] = str(path)
            return data
    # Cloud/demo: KB JSON não vai no git (centenas de MB). Serving usa Postgres.
    return {
        "meta": {
            "versao": "empty",
            "_loaded_from": None,
            "_empty": True,
            "nota": "KB ausente — API em modo serving (Postgres). Defina KB_PATH ou monte data/.",
        },
        "entidades": [],
        "relacoes": [],
        "fontes": [],
        "eventos": [],
        "observacoes": [],
    }


def clear_kb_cache() -> None:
    load_kb.cache_clear()
