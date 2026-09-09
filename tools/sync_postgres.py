#!/usr/bin/env python3
"""Sincroniza KB JSON → PostgreSQL."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "atlas-brasil-kb-v2.json"
URL = os.environ.get(
    "DATABASE_URL", "postgresql://atlas:atlasbrasil@localhost:5432/atlas_brasil"
)


def main() -> int:
    try:
        import psycopg
    except ImportError:
        print("pip install 'psycopg[binary]'", file=sys.stderr)
        return 2

    kb = json.loads(KB.read_text(encoding="utf-8"))
    try:
        conn = psycopg.connect(URL)
    except Exception as e:
        print(f"Postgres indisponivel: {e}", file=sys.stderr)
        return 1

    with conn.cursor() as cur:
        for table in (
            "registros_pessoa_caso",
            "relacoes",
            "timeline",
            "fluxos_financeiros",
            "documentos",
            "casos",
            "entidades",
        ):
            cur.execute(f"TRUNCATE {table} CASCADE")

        for e in kb.get("entidades", []):
            cur.execute(
                """
                INSERT INTO entidades (id,tipo,nome,partido,cargo_atual,no_poder_2026,uf,tags,aliases,isolada,nota)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    e["id"],
                    e.get("tipo"),
                    e.get("nome"),
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
        for c in kb.get("casos", []):
            cur.execute(
                "INSERT INTO casos (id,nome,periodo,eixos,nota) VALUES (%s,%s,%s,%s,%s)",
                (
                    c["id"],
                    c.get("nome"),
                    c.get("periodo"),
                    c.get("eixos") or [],
                    c.get("nota"),
                ),
            )
        for d in kb.get("documentos", []):
            cur.execute(
                """
                INSERT INTO documentos (id,tipo,titulo,data,nivel_fonte,orgao,url,url_pendente,casos,nota)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    d["id"],
                    d.get("tipo"),
                    d.get("titulo"),
                    d.get("data"),
                    d.get("nivel_fonte"),
                    d.get("orgao"),
                    d.get("url") or d.get("url_ref"),
                    bool(d.get("url_pendente")),
                    d.get("casos") or [],
                    d.get("nota"),
                ),
            )
        for r in kb.get("relacoes", []):
            cur.execute(
                """
                INSERT INTO relacoes
                (id,origem,destino,tipo,periodo,contexto,justificativa_documental,grau_confirmacao,caso_id,fonte_ids,fontes,nota,url_pendente)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    r["id"],
                    r["origem"],
                    r["destino"],
                    r["tipo"],
                    r.get("periodo"),
                    r.get("contexto"),
                    r.get("justificativa_documental"),
                    r.get("grau_confirmacao"),
                    r.get("caso_id"),
                    r.get("fonte_ids") or [],
                    r.get("fontes") or [],
                    r.get("nota"),
                    bool(r.get("url_pendente")),
                ),
            )
        for rpc in kb.get("registros_pessoa_caso", []):
            cur.execute(
                """
                INSERT INTO registros_pessoa_caso
                (id,pessoa_id,caso_id,status,camada,acusacao,situacao_atual,fonte_ids,fontes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    rpc["id"],
                    rpc["pessoa_id"],
                    rpc["caso_id"],
                    rpc.get("status"),
                    rpc.get("camada"),
                    rpc.get("acusacao"),
                    rpc.get("situacao_atual"),
                    rpc.get("fonte_ids") or [],
                    rpc.get("fontes") or [],
                ),
            )
        for t in kb.get("timeline", []):
            cur.execute(
                """
                INSERT INTO timeline (id,data,eixo,titulo,caso_ids,governo_id,fontes)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    t["id"],
                    t.get("data"),
                    t.get("eixo"),
                    t.get("titulo"),
                    t.get("caso_ids") or [],
                    t.get("governo_id"),
                    t.get("fontes") or [],
                ),
            )
        for f in kb.get("fluxos_financeiros") or []:
            cur.execute(
                "INSERT INTO fluxos_financeiros (id, payload) VALUES (%s, %s::jsonb)",
                (f["id"], json.dumps(f, ensure_ascii=False)),
            )
        cur.execute(
            """
            INSERT INTO meta_sistema (chave, valor) VALUES ('kb_meta', %s::jsonb)
            ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = NOW()
            """,
            (json.dumps(kb.get("meta") or {}, ensure_ascii=False),),
        )
        conn.commit()
    conn.close()
    print(
        f"Postgres sync OK ents={len(kb.get('entidades',[]))} rel={len(kb.get('relacoes',[]))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
