"""
GDS-lite (Fase 3): Louvain/label-propagation local.
Tenta Neo4j GDS se plugin disponível; senão usa communities() da API.
"""

from __future__ import annotations

import os
from typing import Any

from app.graph_ops import communities, hubs


def louvain(de: str | None = None, ate: str | None = None) -> dict[str, Any]:
    neo = _try_neo4j_gds()
    if neo:
        return neo
    base = communities(mode="comunidades", de=de, ate=ate)
    return {
        "algorithm": "label_propagation_local",
        "engine": "atlas_gds_lite",
        "note": "Neo4j GDS plugin não detectado — usando LPA local (mesmo contrato).",
        **base,
    }


def ranking_centralidade(metric: str = "degree") -> dict[str, Any]:
    return {
        "algorithm": metric,
        "engine": "atlas_gds_lite",
        **hubs(metric=metric),
    }


def _try_neo4j_gds() -> dict[str, Any] | None:
    uri = os.getenv("NEO4J_URI")
    if not uri:
        return None
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            uri,
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "atlasbrasil")),
        )
        with driver.session() as session:
            # verifica se gds está instalado
            try:
                session.run("RETURN gds.version() AS v").single()
            except Exception:
                driver.close()
                return None
            # projetar grafo efêmero e Louvain
            session.run(
                """
                CALL gds.graph.project.cypher(
                  'atlas_tmp',
                  'MATCH (n) RETURN id(n) AS id',
                  'MATCH (a)-[r]->(b) RETURN id(a) AS source, id(b) AS target'
                )
                YIELD graphName
                """
            )
            rows = session.run(
                """
                CALL gds.louvain.stream('atlas_tmp')
                YIELD nodeId, communityId
                RETURN gds.util.asNode(nodeId).id AS id,
                       gds.util.asNode(nodeId).nome AS nome,
                       communityId
                """
            )
            groups: dict[Any, list] = {}
            for r in rows:
                groups.setdefault(r["communityId"], []).append(
                    {"id": r["id"], "nome": r["nome"]}
                )
            try:
                session.run("CALL gds.graph.drop('atlas_tmp', false)")
            except Exception:
                pass
        driver.close()
        communities_list = [
            {"id": f"gds_{i}", "size": len(m), "membros": m}
            for i, m in enumerate(sorted(groups.values(), key=len, reverse=True), 1)
            if len(m) >= 2
        ]
        return {
            "algorithm": "louvain",
            "engine": "neo4j_gds",
            "communities": communities_list,
            "disclaimer": "Comunidades estruturais — não implicam aliança ilícita.",
        }
    except Exception:
        return None
