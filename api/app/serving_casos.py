"""Serving casos editoriais (dossiês) — Postgres editorial_cases; fallback KB.

Não confundir com legal_cases (DataJud). Processo/dossiê ≠ culpa.
"""

from __future__ import annotations

import json
from typing import Any

from app.db import get_conn
from app.kb_loader import load_kb

DISCLAIMER = (
    "O Atlas não acusa. O Atlas documenta. "
    "Dossiê, investigação ou menção ≠ culpa. "
    "Desfechos posteriores (arquivamento, absolvição) devem ter igual destaque."
)


def list_casos(
    *,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    conn = get_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM editorial_cases")
                total = cur.fetchone()[0]
                if total:
                    limit = max(1, min(int(limit), 1000))
                    offset = max(0, int(offset))
                    qn = (q or "").strip()
                    if qn:
                        cur.execute(
                            """
                            SELECT case_id, nome, periodo, eixos, resumo
                            FROM editorial_cases
                            WHERE nome ILIKE %s
                            ORDER BY nome
                            LIMIT %s OFFSET %s
                            """,
                            (f"%{qn}%", limit, offset),
                        )
                        cur2 = conn.cursor()
                        cur2.execute(
                            "SELECT COUNT(*) FROM editorial_cases WHERE nome ILIKE %s",
                            (f"%{qn}%",),
                        )
                        total = cur2.fetchone()[0]
                        cur2.close()
                    else:
                        cur.execute(
                            """
                            SELECT case_id, nome, periodo, eixos, resumo
                            FROM editorial_cases
                            ORDER BY nome
                            LIMIT %s OFFSET %s
                            """,
                            (limit, offset),
                        )
                    cols = [d[0] for d in cur.description]
                    items = []
                    for r in cur.fetchall():
                        row = dict(zip(cols, r))
                        eixos = row.get("eixos") or []
                        if isinstance(eixos, str):
                            eixos = json.loads(eixos)
                        items.append(
                            {
                                "id": row["case_id"],
                                "nome": row["nome"],
                                "periodo": row.get("periodo"),
                                "eixos": eixos,
                                "resumo": row.get("resumo"),
                            }
                        )
                    return {
                        "ok": True,
                        "total": total,
                        "items": items,
                        "source": "postgres",
                        "disclaimer": DISCLAIMER,
                    }
        except Exception:
            pass

    kb = load_kb()
    qn = (q or "").strip().lower()
    items = []
    for c in kb.get("casos") or []:
        if qn and qn not in (c.get("nome") or "").lower():
            continue
        items.append(
            {
                "id": c.get("id"),
                "nome": c.get("nome"),
                "periodo": c.get("periodo"),
                "eixos": c.get("eixos") or [],
                "resumo": c.get("resumo") or c.get("sinopse"),
            }
        )
    total = len(items)
    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))
    return {
        "ok": True,
        "total": total,
        "items": items[offset : offset + limit],
        "source": "kb_gateway",
        "disclaimer": DISCLAIMER,
    }


def get_caso(case_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT payload FROM editorial_cases WHERE case_id = %s",
                    (case_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    payload = row[0]
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    # Enrich with person links from persons regs in profile is heavy;
                    # attach registros from KB only if needed — keep payload + disclaimer
                    kb = None
                    try:
                        kb = load_kb()
                    except Exception:
                        kb = None
                    regs = []
                    pessoas = {}
                    if kb:
                        regs = [
                            r
                            for r in (kb.get("registros_pessoa_caso") or [])
                            if r.get("caso_id") == case_id
                        ]
                        ent = {
                            e["id"]: e
                            for e in (kb.get("entidades") or [])
                            if e.get("id")
                        }
                        for r in regs:
                            pid = r.get("pessoa_id")
                            if pid and pid in ent:
                                p = ent[pid]
                                pessoas[pid] = {
                                    "id": pid,
                                    "nome": p.get("nome"),
                                    "partido": p.get("partido"),
                                    "cargo_atual": p.get("cargo_atual"),
                                }
                    return {
                        "ok": True,
                        "caso": payload,
                        "regs": regs,
                        "pessoas": pessoas,
                        "source": "postgres",
                        "disclaimer": DISCLAIMER,
                    }
        except Exception:
            pass

    kb = load_kb()
    c = next((x for x in (kb.get("casos") or []) if x.get("id") == case_id), None)
    if not c:
        return None
    regs = [
        r
        for r in (kb.get("registros_pessoa_caso") or [])
        if r.get("caso_id") == case_id
    ]
    ent = {e["id"]: e for e in (kb.get("entidades") or []) if e.get("id")}
    pessoas = {}
    for r in regs:
        pid = r.get("pessoa_id")
        if pid and pid in ent:
            p = ent[pid]
            pessoas[pid] = {
                "id": pid,
                "nome": p.get("nome"),
                "partido": p.get("partido"),
                "cargo_atual": p.get("cargo_atual"),
            }
    return {
        "ok": True,
        "caso": c,
        "regs": regs,
        "pessoas": pessoas,
        "source": "kb_gateway",
        "disclaimer": DISCLAIMER,
    }
