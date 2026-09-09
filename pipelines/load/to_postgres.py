#!/usr/bin/env python3
"""Carrega gold KB -> Postgres (upsert entidades/relações/documentos)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD = Path(os.getenv("GOLD_KB_PATH", ROOT / "data" / "atlas-brasil-kb-gold.json"))
DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://atlas:atlasbrasil@localhost:5433/atlas_brasil",
)


def main() -> int:
    if not GOLD.exists():
        print(f"gold ausente: {GOLD}", file=sys.stderr)
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))

    try:
        import psycopg
    except ImportError:
        print("psycopg não instalado — export JSON já basta para o front", file=sys.stderr)
        return 0

    try:
        conn = psycopg.connect(DSN)
    except Exception as e:
        print(f"Postgres indisponível ({e}) — skip load", file=sys.stderr)
        return 0

    ents = kb.get("entidades") or []
    rels = kb.get("relacoes") or []
    docs = kb.get("documentos") or []

    with conn:
        with conn.cursor() as cur:
            for e in ents:
                cur.execute(
                    """
                    INSERT INTO entidades (id, tipo, nome, partido, cargo_atual, no_poder_2026, uf, tags, aliases, isolada, nota)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET
                      tipo=EXCLUDED.tipo, nome=EXCLUDED.nome, partido=EXCLUDED.partido,
                      cargo_atual=EXCLUDED.cargo_atual, no_poder_2026=EXCLUDED.no_poder_2026,
                      uf=EXCLUDED.uf, tags=EXCLUDED.tags, aliases=EXCLUDED.aliases,
                      isolada=EXCLUDED.isolada, updated_at=NOW()
                    """,
                    (
                        e["id"],
                        e["tipo"],
                        e["nome"],
                        e.get("partido"),
                        e.get("cargo_atual"),
                        bool(e.get("no_poder_2026")),
                        e.get("uf"),
                        e.get("tags") or [],
                        e.get("aliases") or [],
                        bool(e.get("isolada")),
                        e.get("nota"),
                    ),
                )
            for d in docs:
                cur.execute(
                    """
                    INSERT INTO documentos (id, tipo, titulo, data, nivel_fonte, orgao, url, url_pendente, casos)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET
                      tipo=EXCLUDED.tipo, titulo=EXCLUDED.titulo, data=EXCLUDED.data,
                      nivel_fonte=EXCLUDED.nivel_fonte, orgao=EXCLUDED.orgao, url=EXCLUDED.url,
                      casos=EXCLUDED.casos
                    """,
                    (
                        d["id"],
                        d.get("tipo"),
                        d.get("titulo") or d["id"],
                        d.get("data"),
                        d.get("nivel_fonte"),
                        d.get("orgao"),
                        d.get("url"),
                        False,
                        d.get("casos") or [],
                    ),
                )
            for r in rels:
                cur.execute(
                    """
                    INSERT INTO relacoes (
                      id, origem, destino, tipo, periodo, contexto,
                      justificativa_documental, grau_confirmacao, caso_id, fontes, fonte_ids
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET
                      origem=EXCLUDED.origem, destino=EXCLUDED.destino, tipo=EXCLUDED.tipo,
                      periodo=EXCLUDED.periodo, contexto=EXCLUDED.contexto,
                      justificativa_documental=EXCLUDED.justificativa_documental,
                      grau_confirmacao=EXCLUDED.grau_confirmacao,
                      fontes=EXCLUDED.fontes, fonte_ids=EXCLUDED.fonte_ids
                    """,
                    (
                        r["id"],
                        r["origem"],
                        r["destino"],
                        r["tipo"],
                        r.get("periodo"),
                        r.get("contexto"),
                        r.get("justificativa_documental") or "",
                        r.get("grau_confirmacao") or "fato_documentado",
                        r.get("caso_id"),
                        r.get("fontes") or [],
                        r.get("fonte_ids") or [],
                    ),
                )
    conn.close()
    print(f"OK postgres: {len(ents)} entidades, {len(rels)} relações, {len(docs)} docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
