#!/usr/bin/env python3
"""
Embeddings densos Fase 4 (384-d).
- Com OPENAI_API_KEY / ATLAS_LLM_API_KEY: text-embedding-3-small (trunc/pad 384)
- Sem chave: hash denso local 384-d
Persiste data/nlp/embeddings_dense.jsonl + Postgres documento_embeddings_dense
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "data" / "atlas-brasil-kb-v2.json"
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
OUT = ROOT / "data" / "nlp" / "embeddings_dense.jsonl"
DIM = int(os.getenv("ATLAS_DENSE_DIM", "384"))


def _strip(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _corpus() -> list[tuple[str, str]]:
    rows = []
    kb = json.loads(KB.read_text(encoding="utf-8"))
    for d in kb.get("documentos") or []:
        rows.append((d["id"], d.get("titulo") or ""))
    for e in kb.get("entidades") or []:
        blob = " ".join(
            filter(
                None,
                [
                    e.get("nome"),
                    e.get("nota"),
                    " ".join(e.get("tags") or []),
                    " ".join(e.get("aliases") or []),
                ],
            )
        )
        rows.append((f"ent:{e['id']}", blob))
    for src in ("stf", "tse", "dou"):
        folder = LAKE / "bronze" / src
        if not folder.exists():
            continue
        for f in folder.glob("*.json"):
            rec = json.loads(f.read_text(encoding="utf-8"))
            text = rec.get("titulo") or ""
            hp = rec.get("html_path")
            if hp and (LAKE / hp).exists():
                text = _strip((LAKE / hp).read_text(encoding="utf-8", errors="ignore"))[:4000]
            rows.append((rec["id"], text or rec.get("titulo") or ""))
    return rows


def hash_dense(text: str) -> list[float]:
    vec = [0.0] * DIM
    toks = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    for i, tok in enumerate(toks):
        if len(tok) < 2:
            continue
        h = int(hashlib.sha256(f"{tok}:{i // 3}".encode()).hexdigest(), 16)
        idx = h % DIM
        sign = 1.0 if (h >> 7) & 1 else -1.0
        vec[idx] += sign * (1.0 + 0.1 * (i % 5))
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def openai_batch(texts: list[str]) -> list[list[float]] | None:
    key = os.getenv("OPENAI_API_KEY") or os.getenv("ATLAS_LLM_API_KEY")
    if not key:
        return None
    model = os.getenv("ATLAS_EMBED_MODEL", "text-embedding-3-small")
    base = os.getenv("ATLAS_LLM_BASE", "https://api.openai.com/v1")
    out: list[list[float]] = []
    # batches de 32
    with httpx.Client(timeout=120.0) as client:
        for i in range(0, len(texts), 32):
            chunk = [t[:6000] or " " for t in texts[i : i + 32]]
            r = client.post(
                f"{base.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "input": chunk},
            )
            if r.status_code >= 400:
                print(r.text[:300], file=sys.stderr)
                return None
            data = sorted(r.json()["data"], key=lambda x: x["index"])
            for item in data:
                v = list(map(float, item["embedding"]))
                if len(v) < DIM:
                    v = v + [0.0] * (DIM - len(v))
                v = v[:DIM]
                n = math.sqrt(sum(x * x for x in v)) or 1.0
                out.append([x / n for x in v])
    return out


def persist_pg(rows: list[dict]) -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        return 0
    try:
        import psycopg

        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documento_embeddings_dense (
                      doc_id TEXT PRIMARY KEY,
                      modelo TEXT NOT NULL,
                      dim INT NOT NULL,
                      embedding REAL[] NOT NULL,
                      updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                    """
                )
                # tenta extensão vector (só se imagem pgvector)
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                except Exception:
                    conn.rollback()
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS documento_embeddings_dense (
                          doc_id TEXT PRIMARY KEY,
                          modelo TEXT NOT NULL,
                          dim INT NOT NULL,
                          embedding REAL[] NOT NULL,
                          updated_at TIMESTAMPTZ DEFAULT NOW()
                        )
                        """
                    )
                n = 0
                for r in rows:
                    cur.execute(
                        """
                        INSERT INTO documento_embeddings_dense (doc_id, modelo, dim, embedding)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (doc_id) DO UPDATE SET
                          modelo = EXCLUDED.modelo,
                          dim = EXCLUDED.dim,
                          embedding = EXCLUDED.embedding,
                          updated_at = NOW()
                        """,
                        (r["doc_id"], r["modelo"], r["dim"], r["embedding"]),
                    )
                    n += 1
            conn.commit()
        return n
    except Exception as e:
        print(f"postgres skip: {e}", file=sys.stderr)
        return 0


def main() -> int:
    corpus = _corpus()
    if not corpus:
        print("sem corpus")
        return 1
    ids = [c[0] for c in corpus]
    texts = [c[1] or " " for c in corpus]
    vectors = openai_batch(texts)
    modelo = "openai"
    if vectors is None:
        vectors = [hash_dense(t) for t in texts]
        modelo = "hash_dense_384"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with OUT.open("w", encoding="utf-8") as f:
        for did, emb in zip(ids, vectors):
            row = {"doc_id": did, "modelo": modelo, "dim": len(emb), "embedding": emb}
            f.write(json.dumps(row) + "\n")
            rows.append(row)
    pg = persist_pg(rows)
    meta = {"modelo": modelo, "dim": DIM, "n": len(rows), "postgres_rows": pg, "path": str(OUT)}
    (OUT.parent / "embeddings_dense_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
