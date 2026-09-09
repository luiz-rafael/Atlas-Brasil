"""Entity resolution em tempo de consulta (Fase 3)."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.kb_loader import load_kb

ROOT = Path(__file__).resolve().parents[2]
MATCHES = ROOT / "data" / "nlp" / "entity_matches.jsonl"
MIN_SCORE = 0.82


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def resolve(text: str, limit: int = 15) -> list[dict[str, Any]]:
    kb = load_kb()
    catalog: list[tuple[str, str, str, str]] = []
    for e in kb.get("entidades") or []:
        if e.get("isolada"):
            continue
        for n in [e.get("nome") or ""] + list(e.get("aliases") or []):
            if n and len(n) >= 3:
                catalog.append((e["id"], e.get("nome") or n, e.get("tipo") or "", _norm(n)))
    for c in kb.get("casos") or []:
        n = c.get("nome") or ""
        if n:
            catalog.append((c["id"], n, "caso", _norm(n)))

    tnorm = _norm(text)
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for eid, display, tipo, alias in catalog:
        if alias in tnorm and eid not in seen:
            seen.add(eid)
            hits.append(
                {
                    "entity_id": eid,
                    "nome": display,
                    "tipo": tipo,
                    "score": 1.0,
                    "method": "substring",
                }
            )
    tokens = re.findall(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+){0,3})\b",
        text,
    )
    for m in tokens:
        mn = _norm(m)
        if len(mn) < 4:
            continue
        best = None
        for eid, display, tipo, alias in catalog:
            if eid in seen:
                continue
            sc = SequenceMatcher(None, mn, alias).ratio()
            if sc >= MIN_SCORE and (best is None or sc > best["score"]):
                best = {
                    "entity_id": eid,
                    "nome": display,
                    "tipo": tipo,
                    "score": round(sc, 4),
                    "method": "fuzzy",
                    "mention": m,
                }
        if best:
            seen.add(best["entity_id"])
            hits.append(best)
    hits.sort(key=lambda x: -x["score"])
    return hits[:limit]


def recent_batch(limit: int = 50) -> dict[str, Any]:
    if not MATCHES.exists():
        return {"matches": [], "source": None}
    rows = []
    for line in MATCHES.read_text(encoding="utf-8").splitlines()[-limit:]:
        if line.strip():
            rows.append(json.loads(line))
    return {"matches": rows, "source": str(MATCHES), "total_file_hint": "rode pipelines/nlp/entity_resolution.py"}
