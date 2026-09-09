"""Busca semântica sobre embeddings locais (Fase 3)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EMB_PATH = ROOT / "data" / "nlp" / "embeddings.jsonl"
MODEL_PATH = ROOT / "data" / "nlp" / "embed_model.joblib"
DIM = 64


def _hash_embed(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    for tok in re.findall(r"\w+", text.lower(), flags=re.UNICODE):
        if len(tok) < 3:
            continue
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def _cos(a: list[float], b: list[float]) -> float:
    m = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(m))


@lru_cache(maxsize=1)
def _load_index() -> tuple[str, list[tuple[str, list[float]]]]:
    if not EMB_PATH.exists():
        return ("none", [])
    rows = []
    modelo = "unknown"
    for line in EMB_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        modelo = o.get("modelo") or modelo
        rows.append((o["doc_id"], o["embedding"]))
    return (modelo, rows)


@lru_cache(maxsize=1)
def _load_model() -> Any:
    if not MODEL_PATH.exists():
        return None
    try:
        import joblib

        return joblib.load(MODEL_PATH)
    except Exception:
        return None


def reload_index() -> None:
    _load_index.cache_clear()
    _load_model.cache_clear()


def _query_vec(q: str) -> list[float]:
    model = _load_model()
    if model:
        try:
            X = model["vectorizer"].transform([q])
            Y = model["svd"].transform(X)[0]
            dim = int(model.get("dim") or DIM)
            v = list(map(float, Y)) + [0.0] * dim
            v = v[:dim]
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            return [x / n for x in v]
        except Exception:
            pass
    return _hash_embed(q)


def search(q: str, size: int = 10) -> dict[str, Any]:
    modelo, rows = _load_index()
    if not rows or not q.strip():
        return {"q": q, "hits": [], "modelo": modelo, "disponivel": bool(rows)}
    qv = _query_vec(q)
    scored = []
    for doc_id, emb in rows:
        if not emb:
            continue
        scored.append((_cos(qv, emb), doc_id))
    scored.sort(key=lambda x: -x[0])
    hits = [{"doc_id": i, "score": round(s, 5)} for s, i in scored[:size] if s > 0.01]

    from app.kb_loader import load_kb

    kb = load_kb()
    titles = {d["id"]: d.get("titulo") for d in kb.get("documentos") or []}
    titles.update({f"ent:{e['id']}": e.get("nome") for e in kb.get("entidades") or []})
    for h in hits:
        h["titulo"] = titles.get(h["doc_id"])
    return {"q": q, "hits": hits, "modelo": modelo, "disponivel": True}
