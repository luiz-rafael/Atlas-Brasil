#!/usr/bin/env python3
"""Smoke Cypher: path Lula↔Bolsonaro + contagens."""
from neo4j import GraphDatabase

d = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "atlasbrasil"))
with d.session() as s:
    n = s.run("MATCH (n:Entity) RETURN count(n) AS c").single()["c"]
    r = s.run("MATCH ()-[rel]->() RETURN count(rel) AS c").single()["c"]
    print(f"entities={n} relationships={r}")
    row = s.run(
        """
        MATCH (a:Entity {id: $a}), (b:Entity {id: $b})
        MATCH p = shortestPath((a)-[*..6]-(b))
        RETURN [x IN nodes(p) | x.nome] AS nos
        """,
        a="p_lula",
        b="p_jair",
    ).single()
    print("path_lula_jair:", row["nos"] if row else None)
d.close()
