#!/usr/bin/env python3
"""Carrega gold KB -> Neo4j (batch UNWIND)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_default_kb = ROOT / "data" / "atlas-brasil-kb-web.json"
if not _default_kb.is_file():
    _default_kb = ROOT / "data" / "atlas-brasil-kb-gold.json"
GOLD = Path(os.getenv("GOLD_KB_PATH", str(_default_kb)))
URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "atlasbrasil")
BATCH = int(os.getenv("NEO4J_BATCH", "500"))


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def main() -> int:
    if os.getenv("NEO4J_SKIP", "0") == "1":
        print("NEO4J_SKIP=1 — skip")
        return 0
    if not GOLD.exists():
        print(f"gold ausente: {GOLD}", file=sys.stderr)
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("neo4j driver ausente — skip", file=sys.stderr)
        return 0

    try:
        driver = GraphDatabase.driver(
            URI,
            auth=(USER, PASSWORD),
            connection_timeout=5.0,
            max_connection_lifetime=60,
        )
        driver.verify_connectivity()
    except Exception as e:
        print(f"Neo4j indisponivel ({e}) — skip", file=sys.stderr)
        return 0

    ents = [
        {
            "id": e["id"],
            "nome": e["nome"],
            "tipo": e["tipo"],
            "partido": e.get("partido"),
            "cargo": e.get("cargo_atual"),
            "uf": e.get("uf"),
            "tags": e.get("tags") or [],
        }
        for e in (kb.get("entidades") or [])
    ]
    rels = [
        {
            "origem": r["origem"],
            "destino": r["destino"],
            "rid": r["id"],
            "tipo": r["tipo"],
            "grau": r.get("grau_confirmacao"),
            "just": (r.get("justificativa_documental") or "")[:500],
            "fids": r.get("fonte_ids") or [],
        }
        for r in (kb.get("relacoes") or [])
    ]

    with driver.session() as session:
        for batch in chunks(ents, BATCH):
            session.run(
                """
                UNWIND $rows AS e
                MERGE (n:Entidade {id: e.id})
                SET n.nome = e.nome, n.tipo = e.tipo, n.partido = e.partido,
                    n.cargo_atual = e.cargo, n.uf = e.uf, n.tags = e.tags
                """,
                rows=batch,
            )
        for batch in chunks(rels, BATCH):
            session.run(
                """
                UNWIND $rows AS r
                MATCH (a:Entidade {id: r.origem}), (b:Entidade {id: r.destino})
                MERGE (a)-[rel:RELACAO {id: r.rid}]->(b)
                SET rel.tipo = r.tipo, rel.grau = r.grau,
                    rel.justificativa = r.just, rel.fonte_ids = r.fids
                """,
                rows=batch,
            )
    driver.close()
    print(f"OK neo4j: {len(ents)} nos, {len(rels)} arestas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
