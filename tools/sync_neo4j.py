#!/usr/bin/env python3
"""Sincroniza data/atlas-brasil-kb-v2.json → Neo4j (idempotente)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "atlas-brasil-kb-v2.json"

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "atlasbrasil")

LABEL_MAP = {
    "pessoa": "Pessoa",
    "empresa": "Empresa",
    "partido": "Partido",
    "instituicao": "Instituicao",
    "conceito": "Conceito",
    "faccao": "Faccao",
    "organizacao_criminosa": "Faccao",
    "operacao": "Operacao",
    "territorio": "Territorio",
}


def sanitize_rel_type(tipo: str) -> str:
    t = (tipo or "RELACIONADO").upper().replace("-", "_").replace(" ", "_")
    return "".join(c if c.isalnum() or c == "_" else "_" for c in t)


def main() -> int:
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("Instale: pip install neo4j", file=sys.stderr)
        return 2

    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    try:
        driver.verify_connectivity()
    except Exception as e:
        print(f"Neo4j indisponível em {URI}: {e}", file=sys.stderr)
        return 1

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        for stmt in (
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT caso_id IF NOT EXISTS FOR (c:Caso) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:Documento) REQUIRE d.id IS UNIQUE",
        ):
            try:
                session.run(stmt)
            except Exception:
                pass

        for e in kb.get("entidades", []):
            if e.get("isolada"):
                continue
            label = LABEL_MAP.get(e.get("tipo", ""), "Entity")
            session.run(
                f"""
                MERGE (n:Entity {{id: $id}})
                SET n: {label},
                    n.nome = $nome,
                    n.tipo = $tipo,
                    n.partido = $partido,
                    n.cargo_atual = $cargo,
                    n.no_poder_2026 = $poder,
                    n.uf = $uf,
                    n.tags = $tags
                """,
                id=e["id"],
                nome=e.get("nome"),
                tipo=e.get("tipo"),
                partido=e.get("partido"),
                cargo=e.get("cargo_atual"),
                poder=bool(e.get("no_poder_2026")),
                uf=e.get("uf"),
                tags=e.get("tags") or [],
            )

        for c in kb.get("casos", []):
            session.run(
                """
                MERGE (n:Caso:Entity {id: $id})
                SET n.nome = $nome, n.tipo = 'caso',
                    n.periodo = $periodo, n.eixos = $eixos
                """,
                id=c["id"],
                nome=c.get("nome"),
                periodo=c.get("periodo"),
                eixos=c.get("eixos") or [],
            )

        for d in kb.get("documentos", []):
            url = d.get("url") or d.get("url_ref") or ""
            session.run(
                """
                MERGE (n:Documento:Entity {id: $id})
                SET n.nome = $titulo, n.titulo = $titulo, n.tipo = 'documento',
                    n.url = $url, n.orgao = $orgao, n.data = $data,
                    n.nivel_fonte = $nivel, n.casos = $casos
                """,
                id=d["id"],
                titulo=d.get("titulo"),
                url=url,
                orgao=d.get("orgao"),
                data=d.get("data"),
                nivel=d.get("nivel_fonte"),
                casos=d.get("casos") or [],
            )
            for cid in d.get("casos") or []:
                session.run(
                    """
                    MATCH (doc:Documento {id: $did}), (c:Caso {id: $cid})
                    MERGE (doc)-[:DOCUMENTA]->(c)
                    """,
                    did=d["id"],
                    cid=cid,
                )

        for g in kb.get("governos", []) or []:
            session.run(
                """
                MERGE (n:Governo:Entity {id: $id})
                SET n.nome = $nome, n.tipo = 'governo',
                    n.inicio = $inicio, n.fim = $fim
                """,
                id=g["id"],
                nome=g.get("presidente") or g["id"],
                inicio=g.get("inicio"),
                fim=g.get("fim"),
            )

        n_rel = 0
        for r in kb.get("relacoes", []):
            rtype = sanitize_rel_type(r.get("tipo", "RELACIONADO"))
            fonte_ids = r.get("fonte_ids") or []
            session.run(
                f"""
                MATCH (a:Entity {{id: $origem}}), (b:Entity {{id: $destino}})
                MERGE (a)-[rel:{rtype} {{id: $rid}}]->(b)
                SET rel.periodo = $periodo,
                    rel.contexto = $contexto,
                    rel.justificativa_documental = $just,
                    rel.grau_confirmacao = $grau,
                    rel.caso_id = $caso_id,
                    rel.fonte_ids = $fonte_ids,
                    rel.fontes = $fontes,
                    rel.tipo = $tipo
                """,
                origem=r["origem"],
                destino=r["destino"],
                rid=r["id"],
                periodo=r.get("periodo"),
                contexto=r.get("contexto"),
                just=r.get("justificativa_documental"),
                grau=r.get("grau_confirmacao"),
                caso_id=r.get("caso_id"),
                fonte_ids=fonte_ids,
                fontes=r.get("fontes") or [],
                tipo=r.get("tipo"),
            )
            n_rel += 1

        n_part = 0
        for rpc in kb.get("registros_pessoa_caso", []):
            session.run(
                """
                MATCH (p:Entity {id: $pid}), (c:Caso {id: $cid})
                MERGE (p)-[r:PARTICIPOU_DE {id: $rid}]->(c)
                SET r.status = $status,
                    r.camada = $camada,
                    r.acusacao = $acusacao,
                    r.situacao_atual = $sit,
                    r.fonte_ids = $fonte_ids,
                    r.fontes = $fontes,
                    r.tipo = 'participou_de'
                """,
                pid=rpc["pessoa_id"],
                cid=rpc["caso_id"],
                rid=rpc["id"],
                status=rpc.get("status"),
                camada=rpc.get("camada"),
                acusacao=rpc.get("acusacao"),
                sit=rpc.get("situacao_atual"),
                fonte_ids=rpc.get("fonte_ids") or [],
                fontes=rpc.get("fontes") or [],
            )
            n_part += 1

        n_fluxo = 0
        for f in kb.get("fluxos_financeiros", []) or []:
            session.run(
                """
                MATCH (c:Caso {id: $cid})
                MERGE (fl:Fluxo:Entity {id: $fid})
                SET fl.nome = $natureza, fl.tipo = 'fluxo',
                    fl.origem_txt = $origem, fl.destino_txt = $destino,
                    fl.grau_confirmacao = $grau,
                    fl.fonte_ids = $fonte_ids,
                    fl.fontes = $fontes
                MERGE (fl)-[:FLUXO_DE]->(c)
                """,
                cid=f["caso_id"],
                fid=f["id"],
                natureza=f.get("natureza"),
                origem=f.get("origem"),
                destino=f.get("destino"),
                grau=f.get("grau_confirmacao"),
                fonte_ids=f.get("fonte_ids") or [],
                fontes=f.get("fontes") or [],
            )
            n_fluxo += 1

        # Fulltext index for search
        try:
            session.run(
                """
                CREATE FULLTEXT INDEX entity_search IF NOT EXISTS
                FOR (n:Entity) ON EACH [n.nome, n.titulo]
                """
            )
        except Exception:
            pass

    driver.close()
    print(
        f"Sync OK -> Neo4j {URI}: "
        f"relacoes={n_rel} participacoes={n_part} fluxos={n_fluxo}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
