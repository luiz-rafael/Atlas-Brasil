"""Busca semântica densa + Postgres (Fase 4)."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.db import get_conn

ROOT = Path(__file__).resolve().parents[2]
DENSE_PATH = ROOT / "data" / "nlp" / "embeddings_dense.jsonl"
DIM = int(os.getenv("ATLAS_DENSE_DIM", "384"))


def _hash_dense(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    toks = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    for i, tok in enumerate(toks):
        if len(tok) < 2:
            continue
        h = int(hashlib.sha256(f"{tok}:{i // 3}".encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 7) & 1 else -1.0
        vec[idx] += sign * (1.0 + 0.1 * (i % 5))
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def _openai_embed(text: str) -> list[float] | None:
    key = os.getenv("OPENAI_API_KEY") or os.getenv("ATLAS_LLM_API_KEY")
    if not key:
        return None
    model = os.getenv("ATLAS_EMBED_MODEL", "text-embedding-3-small")
    base = os.getenv("ATLAS_LLM_BASE", "https://api.openai.com/v1")
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.post(
                f"{base.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "input": text[:8000]},
            )
            if r.status_code >= 400:
                return None
            v = r.json()["data"][0]["embedding"]
            # pad/truncate to DIM
            v = list(map(float, v))
            if len(v) < DIM:
                v = v + [0.0] * (DIM - len(v))
            v = v[:DIM]
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            return [x / n for x in v]
    except Exception:
        return None


def embed_query(text: str) -> tuple[list[float], str]:
    v = _openai_embed(text)
    if v:
        return v, "openai"
    return _hash_dense(text), "hash_dense_384"


def _cos(a: list[float], b: list[float]) -> float:
    m = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(m))


@lru_cache(maxsize=1)
def _load_file() -> list[tuple[str, list[float], str]]:
    if not DENSE_PATH.exists():
        return []
    rows = []
    for line in DENSE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        rows.append((o["doc_id"], o["embedding"], o.get("modelo") or "dense"))
    return rows


def reload() -> None:
    _load_file.cache_clear()


def search_file(q: str, size: int = 10) -> dict[str, Any]:
    rows = _load_file()
    qv, qmodelo = embed_query(q)
    if not rows or not q.strip():
        return {"q": q, "hits": [], "modelo_query": qmodelo, "disponivel": bool(rows)}
    scored = [(_cos(qv, emb), did, modelo) for did, emb, modelo in rows]
    scored.sort(key=lambda x: -x[0])
    hits = [
        {"doc_id": did, "score": round(s, 5), "modelo": m}
        for s, did, m in scored[:size]
        if s > 0.01
    ]
    return {
        "q": q,
        "hits": hits,
        "modelo_query": qmodelo,
        "disponivel": True,
        "backend": "file",
    }


def search_postgres(q: str, size: int = 10) -> dict[str, Any] | None:
    conn = get_conn()
    if not conn:
        return None
    qv, qmodelo = embed_query(q)
    try:
        with conn.cursor() as cur:
            # tenta pgvector se coluna embedding_v existir
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'documento_embeddings_dense'
                """
            )
            cols = {r[0] for r in cur.fetchall()}
            if not cols:
                return None
            cur.execute(
                "SELECT doc_id, modelo, embedding FROM documento_embeddings_dense"
            )
            rows = cur.fetchall()
        scored = []
        for doc_id, modelo, emb in rows:
            if emb is None:
                continue
            vec = list(emb)
            scored.append((_cos(qv, vec), doc_id, modelo))
        scored.sort(key=lambda x: -x[0])
        return {
            "q": q,
            "hits": [
                {"doc_id": d, "score": round(s, 5), "modelo": m}
                for s, d, m in scored[:size]
                if s > 0.01
            ],
            "modelo_query": qmodelo,
            "disponivel": True,
            "backend": "postgres",
        }
    except Exception:
        return None


def search(q: str, size: int = 10) -> dict[str, Any]:
    pg = search_postgres(q, size=size)
    if pg and pg.get("hits"):
        return pg
    return search_file(q, size=size)
