#!/usr/bin/env python3
"""Indexa documentos da KB + bronze lake no OpenSearch."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app.opensearch_client import ensure_index, index_document, ping_opensearch  # noqa: E402

KB_CANDIDATES = [
    ROOT / "data" / "atlas-brasil-kb-gold.json",
    ROOT / "data" / "atlas-brasil-kb-active.json",
    ROOT / "data" / "lake" / "gold" / "kb.json",
    ROOT / "data" / "atlas-brasil-kb-v2.json",
]
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))


def _load_kb() -> dict:
    for p in KB_CANDIDATES:
        if p.is_file():
            print("index KB:", p)
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def main() -> int:
    if not ping_opensearch():
        print("OpenSearch indisponivel em", os.getenv("OPENSEARCH_URL", "http://localhost:9200"))
        return 1
    ensure_index()
    n = 0
    kb = _load_kb()
    for d in kb.get("documentos") or []:
        if index_document({**d, "fonte": "kb", "corpo": d.get("titulo")}):
            n += 1
    for e in kb.get("entidades") or []:
        if e.get("tipo") != "pessoa":
            continue
        doc = {
            "id": f"ent_{e['id']}",
            "titulo": e.get("nome"),
            "tipo": "entidade",
            "orgao": e.get("partido"),
            "fonte": "gold",
            "corpo": f"{e.get('nome')} {e.get('cargo_atual') or ''} {e.get('uf') or ''} {e.get('partido') or ''}",
        }
        if index_document(doc):
            n += 1
    for src in ("stf", "tse", "dou", "camara_v2", "senado_legis", "tse_ckan", "cgu_portal"):
        folder = LAKE / "bronze" / src
        if not folder.exists():
            continue
        for f in folder.rglob("*.json"):
            if f.name in ("manifest.json", "README.json", "stub.json"):
                continue
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(rec, list):
                continue
            corpo = rec.get("titulo") or rec.get("nome") or f.stem
            if index_document(
                {
                    "id": f"lake_{src}_{f.stem}"[:80],
                    "titulo": str(corpo)[:200],
                    "fonte": src,
                    "corpo": str(corpo)[:2000],
                }
            ):
                n += 1
        for f in folder.glob("*.json"):
            rec = json.loads(f.read_text(encoding="utf-8")) if f.stat().st_size < 5_000_000 else {}
            html_rel = rec.get("html_path") if isinstance(rec, dict) else None
            corpo = rec.get("titulo", "") if isinstance(rec, dict) else ""
            if html_rel:
                hp = LAKE / html_rel
                if hp.exists():
                    raw = hp.read_text(encoding="utf-8", errors="ignore")
                    # texto sem tags para busca
                    corpo = re.sub(r"<[^>]+>", " ", raw)
                    corpo = re.sub(r"\s+", " ", corpo).strip()[:8000]
            if index_document({**rec, "corpo": corpo}):
                n += 1
    print(f"opensearch indexed={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
