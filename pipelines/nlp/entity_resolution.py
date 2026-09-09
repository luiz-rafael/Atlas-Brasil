#!/usr/bin/env python3
"""
Entity resolution leve (Fase 3).
Extrai menções de texto -> candidatos KB (aliases) com score.
Não cria arestas automaticamente — só candidatos para revisão.
"""

from __future__ import annotations

import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

KB = ROOT / "data" / "atlas-brasil-kb-v2.json"
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
OUT = ROOT / "data" / "nlp" / "entity_matches.jsonl"
MIN_SCORE = float(os.getenv("ER_MIN_SCORE", "0.82"))


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def _catalog(kb: dict) -> list[tuple[str, str, str]]:
    """(entity_id, display_name, normalized_alias)"""
    rows = []
    for e in kb.get("entidades") or []:
        if e.get("isolada"):
            continue
        names = [e.get("nome") or ""] + list(e.get("aliases") or [])
        for n in names:
            if n and len(n) >= 3:
                rows.append((e["id"], e.get("nome") or n, _norm(n)))
    for c in kb.get("casos") or []:
        n = c.get("nome") or ""
        if n:
            rows.append((c["id"], n, _norm(n)))
    return rows


def _mentions(text: str) -> list[str]:
    # sequências capitalizadas + termos longos
    caps = re.findall(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+){0,4})\b",
        text,
    )
    # também palavras-chave do texto bruto (já normalizado no match)
    return list(dict.fromkeys(caps))[:80]


def resolve_text(text: str, catalog: list[tuple[str, str, str]]) -> list[dict]:
    hits = []
    seen = set()
    # match direto por substring no texto normalizado
    tnorm = _norm(text)
    for eid, display, alias in catalog:
        if len(alias) < 3:
            continue
        if alias in tnorm:
            key = (eid, alias)
            if key not in seen:
                seen.add(key)
                hits.append(
                    {
                        "entity_id": eid,
                        "nome": display,
                        "mention": alias,
                        "score": 1.0,
                        "method": "substring",
                    }
                )
    # fuzzy sobre menções capitalizadas
    for m in _mentions(text):
        mn = _norm(m)
        if len(mn) < 4:
            continue
        best = None
        for eid, display, alias in catalog:
            if abs(len(alias) - len(mn)) > 12:
                continue
            sc = SequenceMatcher(None, mn, alias).ratio()
            if sc >= MIN_SCORE and (best is None or sc > best["score"]):
                best = {
                    "entity_id": eid,
                    "nome": display,
                    "mention": m,
                    "score": round(sc, 4),
                    "method": "fuzzy",
                }
        if best:
            key = (best["entity_id"], _norm(best["mention"]))
            if key not in seen:
                seen.add(key)
                hits.append(best)
    hits.sort(key=lambda x: -x["score"])
    return hits[:25]


def _doc_texts() -> list[tuple[str, str, str]]:
    """(doc_id, titulo, text)"""
    kb = json.loads(KB.read_text(encoding="utf-8"))
    docs = []
    for d in kb.get("documentos") or []:
        docs.append((d["id"], d.get("titulo") or "", d.get("titulo") or ""))
    for src in ("stf", "tse", "dou"):
        folder = LAKE / "bronze" / src
        if not folder.exists():
            continue
        for f in folder.glob("*.json"):
            rec = json.loads(f.read_text(encoding="utf-8"))
            title = rec.get("titulo") or ""
            body = title
            hp = rec.get("html_path")
            if hp:
                p = LAKE / hp
                if p.exists():
                    raw = p.read_text(encoding="utf-8", errors="ignore")
                    body = re.sub(r"<[^>]+>", " ", raw)
                    body = re.sub(r"\s+", " ", body)[:12000]
            docs.append((rec["id"], title, f"{title}\n{body}"))
    return docs


def persist_postgres(matches: list[dict]) -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        return 0
    try:
        import psycopg

        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS entity_mentions (
                      id BIGSERIAL PRIMARY KEY,
                      doc_id TEXT NOT NULL,
                      entity_id TEXT NOT NULL,
                      mention TEXT,
                      score REAL,
                      method TEXT,
                      status TEXT DEFAULT 'candidato',
                      created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                    """
                )
                cur.execute("DELETE FROM entity_mentions WHERE status = 'candidato'")
                n = 0
                for m in matches:
                    cur.execute(
                        """
                        INSERT INTO entity_mentions (doc_id, entity_id, mention, score, method)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            m["doc_id"],
                            m["entity_id"],
                            m.get("mention"),
                            m.get("score"),
                            m.get("method"),
                        ),
                    )
                    n += 1
            conn.commit()
        return n
    except Exception as e:
        print(f"postgres skip: {e}", file=sys.stderr)
        return 0


def main() -> int:
    kb = json.loads(KB.read_text(encoding="utf-8"))
    catalog = _catalog(kb)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    all_matches: list[dict] = []
    with OUT.open("w", encoding="utf-8") as f:
        for doc_id, titulo, text in _doc_texts():
            for hit in resolve_text(text, catalog):
                row = {"doc_id": doc_id, "titulo": titulo, **hit}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                all_matches.append(row)
    pg = persist_postgres(all_matches)
    print(
        json.dumps(
            {
                "matches": len(all_matches),
                "docs_scanned": len(_doc_texts()),
                "catalog_aliases": len(catalog),
                "out": str(OUT),
                "postgres_rows": pg,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
