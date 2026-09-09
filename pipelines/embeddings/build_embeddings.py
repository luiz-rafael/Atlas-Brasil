#!/usr/bin/env python3
"""
Embeddings locais (Fase 3) — TF-IDF + SVD (384->64) ou hash fallback.
Persiste em data/nlp/embeddings.jsonl e Postgres (float[]).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "data" / "atlas-brasil-kb-v2.json"
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
OUT = ROOT / "data" / "nlp" / "embeddings.jsonl"
DIM = int(os.getenv("EMBED_DIM", "64"))


def _strip_html(s: str) -> str:
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
                [e.get("nome"), e.get("nota"), " ".join(e.get("tags") or []), " ".join(e.get("aliases") or [])],
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
                text = _strip_html((LAKE / hp).read_text(encoding="utf-8", errors="ignore"))[:6000]
            rows.append((rec["id"], text or rec.get("titulo") or ""))
    return rows


def _hash_embed(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    for tok in re.findall(r"\w+", text.lower(), flags=re.UNICODE):
        if len(tok) < 3:
            continue
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _sklearn_embed(texts: list[str]) -> list[list[float]]:
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(max_features=4096, ngram_range=(1, 2), min_df=1)
    X = vec.fit_transform(texts)
    n_comp = min(DIM, max(2, X.shape[0] - 1), X.shape[1] - 1 if X.shape[1] > 1 else 2)
    svd = TruncatedSVD(n_components=n_comp, random_state=42)
    Y = svd.fit_transform(X)
    out = []
    for row in Y:
        # pad to DIM
        v = list(map(float, row)) + [0.0] * (DIM - len(row))
        v = v[:DIM]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def persist_postgres(rows: list[dict]) -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        return 0
    try:
        import psycopg

        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documento_embeddings (
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
                        INSERT INTO documento_embeddings (doc_id, modelo, dim, embedding)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (doc_id) DO UPDATE
                          SET modelo = EXCLUDED.modelo,
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
    modelo = "hashing"
    vectors: list[list[float]]
    try:
        import joblib
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(max_features=4096, ngram_range=(1, 2), min_df=1)
        X = vec.fit_transform(texts)
        n_comp = min(DIM, max(2, X.shape[0] - 1), X.shape[1] - 1 if X.shape[1] > 1 else 2)
        svd = TruncatedSVD(n_components=n_comp, random_state=42)
        Y = svd.fit_transform(X)
        vectors = []
        for row in Y:
            v = list(map(float, row)) + [0.0] * (DIM - len(row))
            v = v[:DIM]
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            vectors.append([x / n for x in v])
        OUT.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"vectorizer": vec, "svd": svd, "dim": DIM}, OUT.parent / "embed_model.joblib")
        modelo = "tfidf_svd"
    except Exception as e:
        print(f"sklearn fallback hashing: {e}", file=sys.stderr)
        vectors = [_hash_embed(t) for t in texts]
        modelo = "hashing"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with OUT.open("w", encoding="utf-8") as f:
        for doc_id, emb in zip(ids, vectors):
            row = {"doc_id": doc_id, "modelo": modelo, "dim": len(emb), "embedding": emb}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)
    pg = persist_postgres(rows)
    # também dump binário leve para API
    meta = {"modelo": modelo, "dim": DIM, "n": len(rows), "path": str(OUT)}
    (OUT.parent / "embeddings_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({**meta, "postgres_rows": pg}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
