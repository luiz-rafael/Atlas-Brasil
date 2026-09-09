"""Serving COMPANY — gateway leve (Fase A/F).

Lista a partir de Postgres companies (amostra) ou KB.
"""

from __future__ import annotations

from typing import Any

from app.db import get_conn
from app.kb_loader import load_kb

DISCLAIMER = (
    "O Atlas não acusa. O Atlas documenta. "
    "Empresa em processo ou contrato ≠ culpa."
)


def list_empresas(
    *,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    conn = get_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM companies")
                total_pg = cur.fetchone()[0]
                if total_pg:
                    limit = max(1, min(int(limit), 2000))
                    offset = max(0, int(offset))
                    if q and q.strip():
                        qn = f"%{q.strip()}%"
                        cur.execute(
                            """
                            SELECT company_id, razao_social, nome_fantasia, cnpj, uf
                            FROM companies
                            WHERE razao_social ILIKE %s
                               OR nome_fantasia ILIKE %s
                               OR cnpj LIKE %s
                            ORDER BY razao_social
                            LIMIT %s OFFSET %s
                            """,
                            (qn, qn, f"%{q.strip()}%", limit, offset),
                        )
                        cur2 = conn.cursor()
                        cur2.execute(
                            """
                            SELECT COUNT(*) FROM companies
                            WHERE razao_social ILIKE %s
                               OR nome_fantasia ILIKE %s
                               OR cnpj LIKE %s
                            """,
                            (qn, qn, f"%{q.strip()}%"),
                        )
                        total = cur2.fetchone()[0]
                        cur2.close()
                    else:
                        cur.execute(
                            """
                            SELECT company_id, razao_social, nome_fantasia, cnpj, uf
                            FROM companies
                            ORDER BY razao_social
                            LIMIT %s OFFSET %s
                            """,
                            (limit, offset),
                        )
                        total = total_pg
                    cols = [d[0] for d in cur.description]
                    items = [dict(zip(cols, r)) for r in cur.fetchall()]
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
    for e in kb.get("entidades") or []:
        if e.get("tipo") != "empresa":
            continue
        if qn and qn not in (e.get("nome") or "").lower():
            continue
        items.append(
            {
                "company_id": e.get("id"),
                "razao_social": e.get("nome"),
                "cnpj": e.get("cnpj"),
                "uf": e.get("uf"),
            }
        )
    total = len(items)
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))
    return {
        "ok": True,
        "total": total,
        "items": items[offset : offset + limit],
        "source": "kb_gateway",
        "disclaimer": DISCLAIMER,
    }


def get_empresa(company_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT company_id, razao_social, nome_fantasia, cnpj, uf,
                           porte, cnae_fiscal, municipio, source
                    FROM companies
                    WHERE company_id = %s OR cnpj = %s
                    LIMIT 1
                    """,
                    (company_id, company_id),
                )
                row = cur.fetchone()
                if row:
                    cols = [d[0] for d in cur.description]
                    return {
                        "ok": True,
                        "empresa": dict(zip(cols, row)),
                        "source": "postgres",
                        "disclaimer": DISCLAIMER,
                    }
        except Exception:
            pass

    kb = load_kb()
    for e in kb.get("entidades") or []:
        if e.get("tipo") == "empresa" and e.get("id") == company_id:
            return {
                "ok": True,
                "empresa": e,
                "source": "kb_gateway",
                "disclaimer": DISCLAIMER,
            }
    return None
