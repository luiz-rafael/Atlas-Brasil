"""Cliente Neo4j — ping + ego/path Cypher com evidência nas edges."""

from __future__ import annotations

import os
from typing import Any

_driver = None
_available: bool | None = None


def neo4j_uri() -> str:
    return os.getenv("NEO4J_URI", "bolt://localhost:7687")


def get_driver():
    global _driver
    if _driver is not None:
        return _driver
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return None
    try:
        _driver = GraphDatabase.driver(
            neo4j_uri(),
            auth=(
                os.getenv("NEO4J_USER", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "atlasbrasil"),
            ),
            connection_timeout=3.0,
        )
        return _driver
    except Exception:
        return None


def ping_neo4j() -> bool:
    global _available
    d = get_driver()
    if not d:
        _available = False
        return False
    try:
        d.verify_connectivity()
        _available = True
        return True
    except Exception:
        _available = False
        return False


def count_nodes() -> int:
    d = get_driver()
    if not d or not ping_neo4j():
        return 0
    try:
        with d.session() as s:
            row = s.run("MATCH (n:Entidade) RETURN count(n) AS c").single()
            return int(row["c"]) if row else 0
    except Exception:
        return 0


def subgraph_cypher(centro: str, depth: int = 1) -> dict[str, Any] | None:
    if not ping_neo4j():
        return None
    depth = max(1, min(int(depth), 3))
    d = get_driver()
    if not d:
        return None
    try:
        with d.session() as s:
            exists = s.run(
                "MATCH (n:Entidade {id: $id}) RETURN n.id AS id, n.nome AS nome, n.tipo AS tipo",
                id=centro,
            ).single()
            if not exists:
                return None

            q = f"""
            MATCH (c:Entidade {{id: $id}})-[r:RELACAO*1..{depth}]-(o:Entidade)
            UNWIND r AS rel
            WITH collect(DISTINCT c) + collect(DISTINCT o) AS ns,
                 collect(DISTINCT rel) AS rs
            RETURN
              [n IN ns | {{id: n.id, nome: n.nome, tipo: n.tipo, partido: n.partido, uf: n.uf}}] AS nodes,
              [rel IN rs | {{
                id: rel.id,
                tipo: rel.tipo,
                grau: rel.grau,
                justificativa: rel.justificativa,
                fonte_ids: rel.fonte_ids,
                from: startNode(rel).id,
                to: endNode(rel).id
              }}] AS edges
            """
            row = s.run(q, id=centro).single()
            if not row:
                return {
                    "nodes": [
                        {
                            "id": exists["id"],
                            "nome": exists["nome"],
                            "tipo": exists["tipo"],
                        }
                    ],
                    "edges": [],
                    "source": "neo4j",
                }
            nodes = [dict(n) for n in (row["nodes"] or []) if n and n.get("id")]
            # dedupe
            seen = set()
            nodes_u = []
            for n in nodes:
                if n["id"] in seen:
                    continue
                seen.add(n["id"])
                nodes_u.append(n)
            edges = []
            seen_e = set()
            for e in row["edges"] or []:
                if not e:
                    continue
                eid = e.get("id") or f"{e.get('from')}-{e.get('to')}-{e.get('tipo')}"
                if eid in seen_e:
                    continue
                seen_e.add(eid)
                edges.append(
                    {
                        "id": eid,
                        "from": e.get("from"),
                        "to": e.get("to"),
                        "tipo": e.get("tipo"),
                        "grau_confirmacao": e.get("grau"),
                        "justificativa_documental": e.get("justificativa"),
                        "fonte_ids": list(e.get("fonte_ids") or []),
                    }
                )
            return {"nodes": nodes_u, "edges": edges, "source": "neo4j"}
    except Exception:
        return None


def shortest_path_cypher(a: str, b: str, max_len: int = 6) -> dict[str, Any] | None:
    if not ping_neo4j():
        return None
    max_len = max(1, min(int(max_len), 8))
    d = get_driver()
    if not d:
        return None
    try:
        with d.session() as s:
            rows = list(
                s.run(
                    f"""
                    MATCH (sa:Entidade {{id: $a}}), (sb:Entidade {{id: $b}}),
                          path = shortestPath((sa)-[:RELACAO*1..{max_len}]-(sb))
                    RETURN [n IN nodes(path) | {{id: n.id, nome: n.nome, tipo: n.tipo}}] AS nos,
                           [rel IN relationships(path) | {{
                             id: rel.id, tipo: rel.tipo, grau: rel.grau,
                             justificativa: rel.justificativa,
                             fonte_ids: rel.fonte_ids,
                             from: startNode(rel).id, to: endNode(rel).id
                           }}] AS edges
                    LIMIT 3
                    """,
                    a=a,
                    b=b,
                )
            )
            paths = []
            for row in rows:
                nos = [dict(n) for n in (row["nos"] or [])]
                edges = []
                for e in row["edges"] or []:
                    edges.append(
                        {
                            "id": e.get("id"),
                            "from": e.get("from"),
                            "to": e.get("to"),
                            "tipo": e.get("tipo"),
                            "grau_confirmacao": e.get("grau"),
                            "justificativa_documental": e.get("justificativa"),
                            "fonte_ids": list(e.get("fonte_ids") or []),
                        }
                    )
                paths.append(
                    {
                        "node_ids": [n["id"] for n in nos],
                        "nos": nos,
                        "edges": edges,
                        "resumo": {"nos": len(nos), "arestas": len(edges)},
                    }
                )
            return {
                "found": bool(paths),
                "paths": paths,
                "source": "neo4j",
                "aviso": "Path ≠ culpa. Compartilhar aresta ≠ aliança ilícita.",
            }
    except Exception:
        return None
