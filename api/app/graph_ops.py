"""Operações de grafo no backend (espelho do network-metrics / graph-engine)."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from app.kb_loader import load_kb

METRIC_DISCLAIMER = (
    "Centralidade é medida estrutural — não equivale a poder político ou culpa."
)


def _year(periodo: str | None) -> int | None:
    if not periodo:
        return None
    for i, ch in enumerate(periodo):
        if ch.isdigit():
            try:
                return int(periodo[i : i + 4])
            except Exception:
                return None
    return None


def _edges(de: str | None = None, ate: str | None = None):
    kb = load_kb()
    nodes = {}
    for e in kb.get("entidades", []):
        if e.get("isolada"):
            continue
        nodes[e["id"]] = {"id": e["id"], "nome": e["nome"], "tipo": e["tipo"]}
    for c in kb.get("casos", []):
        nodes[c["id"]] = {"id": c["id"], "nome": c["nome"], "tipo": "caso"}

    edges = []
    for r in kb.get("relacoes", []):
        if r["origem"] not in nodes or r["destino"] not in nodes:
            continue
        y = _year(r.get("periodo"))
        if de and y is not None and y < int(de):
            continue
        if ate and y is not None and y > int(ate):
            continue
        edges.append(
            {
                "id": r["id"],
                "from": r["origem"],
                "to": r["destino"],
                "tipo": r["tipo"],
                "periodo": r.get("periodo"),
                "grau_confirmacao": r.get("grau_confirmacao"),
                "justificativa_documental": r.get("justificativa_documental"),
                "fonte_ids": r.get("fonte_ids") or [],
            }
        )
    for rpc in kb.get("registros_pessoa_caso", []):
        if rpc["pessoa_id"] not in nodes or rpc["caso_id"] not in nodes:
            continue
        edges.append(
            {
                "id": rpc["id"],
                "from": rpc["pessoa_id"],
                "to": rpc["caso_id"],
                "tipo": "participou_de",
                "grau_confirmacao": rpc.get("camada"),
                "fonte_ids": rpc.get("fonte_ids") or [],
            }
        )
    return nodes, edges


def _adj(edges):
    adj = defaultdict(list)
    for e in edges:
        adj[e["from"]].append(e)
        adj[e["to"]].append(e)
    return adj


def subgraph(centro: str | None, depth: int, de=None, ate=None) -> dict[str, Any]:
    # Preferir Neo4j quando centro definido e sem filtro temporal estrito
    if centro and de is None and ate is None:
        try:
            from app.neo4j_client import subgraph_cypher

            neo = subgraph_cypher(centro, depth)
            if neo and neo.get("nodes"):
                return {
                    **neo,
                    "centro": centro,
                    "profundidade": depth,
                    "metric_disclaimer": METRIC_DISCLAIMER,
                }
        except Exception:
            pass

    nodes, edges = _edges(de, ate)
    if centro is None:
        clusters = defaultdict(list)
        deg = defaultdict(int)
        for e in edges:
            deg[e["from"]] += 1
            deg[e["to"]] += 1
        for n in nodes.values():
            if deg[n["id"]] == 0 and n["tipo"] != "caso":
                continue
            key = {
                "pessoa": "politica",
                "empresa": "empresas",
                "instituicao": "instituicoes",
                "caso": "casos",
                "partido": "partidos",
                "faccao": "crime_organizado",
                "operacao": "operacoes",
            }.get(n["tipo"], "outros")
            clusters[key].append(n)
        return {"clusters": dict(clusters), "edge_count": len(edges), "motor": "api"}

    adj = _adj(edges)
    kept_n = {centro}
    kept_e = []
    frontier = [centro]
    for _ in range(depth):
        nxt = []
        for u in frontier:
            for e in adj.get(u, []):
                other = e["to"] if e["from"] == u else e["from"]
                if e not in kept_e:
                    kept_e.append(e)
                if other not in kept_n:
                    kept_n.add(other)
                    nxt.append(other)
        frontier = nxt
    return {
        "centro": centro,
        "profundidade": depth,
        "nodes": [nodes[i] for i in kept_n if i in nodes],
        "edges": kept_e,
        "motor": "api",
    }


def shortest_paths(a: str, b: str, max_hops: int = 6) -> dict[str, Any]:
    try:
        from app.neo4j_client import shortest_path_cypher

        neo = shortest_path_cypher(a, b, max_hops)
        if neo is not None:
            return {**neo, "metric_disclaimer": METRIC_DISCLAIMER}
    except Exception:
        pass

    nodes, edges = _edges()
    if a not in nodes or b not in nodes:
        return {"found": False, "paths": []}
    adj = _adj(edges)
    q = deque([[a]])
    paths = []
    while q and len(paths) < 3:
        path = q.popleft()
        last = path[-1]
        if len(path) - 1 > max_hops:
            continue
        if last == b and len(path) > 1:
            elist = []
            for i in range(len(path) - 1):
                for e in adj[path[i]]:
                    if {e["from"], e["to"]} == {path[i], path[i + 1]}:
                        elist.append(e)
                        break
            paths.append(
                {
                    "node_ids": path,
                    "nos": [nodes[i] for i in path],
                    "edges": elist,
                    "resumo": {
                        "nos": len(path),
                        "relacoes": len(elist),
                        "tipos": list({e["tipo"] for e in elist}),
                    },
                }
            )
            continue
        for e in adj.get(last, []):
            other = e["to"] if e["from"] == last else e["from"]
            if other in path:
                continue
            q.append(path + [other])
    return {"found": bool(paths), "a": a, "b": b, "paths": paths, "motor": "api"}


def meeting_points(a: str, b: str, depth: int = 2) -> dict[str, Any]:
    nodes, edges = _edges()
    adj = _adj(edges)

    def ego(c):
        s = {c}
        fr = [c]
        for _ in range(depth):
            nxt = []
            for u in fr:
                for e in adj.get(u, []):
                    o = e["to"] if e["from"] == u else e["from"]
                    if o not in s:
                        s.add(o)
                        nxt.append(o)
            fr = nxt
        return s

    inter = (ego(a) & ego(b)) - {a, b}
    by = defaultdict(list)
    for i in inter:
        n = nodes.get(i)
        if n:
            by[n["tipo"]].append(n)
    return {
        "a": a,
        "b": b,
        "pontos": dict(by),
        "total": len(inter),
        "motor": "api",
    }


def hubs(metric="degree", tipo="todos", de=None, ate=None, por_periodo=False):
    nodes, edges = _edges(de, ate)
    deg = defaultdict(int)
    for e in edges:
        deg[e["from"]] += 1
        deg[e["to"]] += 1
    ranking = []
    for nid, n in nodes.items():
        if tipo != "todos" and n["tipo"] != tipo:
            continue
        if deg[nid] == 0:
            continue
        ranking.append(
            {
                "id": nid,
                "nome": n["nome"],
                "tipo": n["tipo"],
                "score": deg[nid],
                "raw": deg[nid],
            }
        )
    ranking.sort(key=lambda x: -x["score"])
    for i, r in enumerate(ranking[:30], 1):
        r["rank"] = i
    out = {
        "metric": metric,
        "disclaimer": METRIC_DISCLAIMER,
        "ranking": ranking[:30],
    }
    if por_periodo:
        wins = [
            ("1985", "1994", "1985–1994"),
            ("1995", "2002", "1995–2002"),
            ("2003", "2010", "2003–2010"),
            ("2011", "2018", "2011–2018"),
            ("2019", "2026", "2019–2026"),
        ]
        out["periodos"] = [
            {
                "label": lab,
                "hubs": hubs(metric, tipo, d, a, False)["ranking"][:5],
            }
            for d, a, lab in wins
        ]
    return out


def communities(mode="comunidades", de=None, ate=None):
    nodes, edges = _edges(de, ate)
    adj_n = defaultdict(set)
    for e in edges:
        adj_n[e["from"]].add(e["to"])
        adj_n[e["to"]].add(e["from"])
    labels = {i: i for i in nodes}
    ids = list(nodes.keys())
    for _ in range(25):
        changed = 0
        for u in sorted(ids):
            neigh = adj_n.get(u) or set()
            if not neigh:
                continue
            counts = defaultdict(int)
            for v in neigh:
                counts[labels[v]] += 1
            best = max(counts.items(), key=lambda kv: (kv[1], -ord(kv[0][0]) if kv[0] else 0))[0]
            if best != labels[u]:
                labels[u] = best
                changed += 1
        if not changed:
            break
    groups = defaultdict(list)
    for i, lab in labels.items():
        groups[lab].append(i)
    communities_list = []
    for i, (lab, members) in enumerate(
        sorted(groups.items(), key=lambda kv: -len(kv[1])), 1
    ):
        if len(members) < 2:
            continue
        communities_list.append(
            {
                "id": f"com_{i}",
                "size": len(members),
                "membros": [
                    {"id": m, "nome": nodes[m]["nome"], "tipo": nodes[m]["tipo"]}
                    for m in members
                    if m in nodes
                ],
            }
        )
    if mode == "pontes":
        deg = defaultdict(int)
        for e in edges:
            deg[e["from"]] += 1
            deg[e["to"]] += 1
        bridges = sorted(
            (
                {
                    "rank": 0,
                    "id": i,
                    "nome": nodes[i]["nome"],
                    "tipo": nodes[i]["tipo"],
                    "betweenness": deg[i],
                }
                for i in nodes
                if deg[i] >= 2
            ),
            key=lambda x: -x["betweenness"],
        )[:15]
        for i, b in enumerate(bridges, 1):
            b["rank"] = i
        return {
            "bridges": bridges,
            "communities_count": len(communities_list),
            "disclaimer": METRIC_DISCLAIMER,
        }
    return {"communities": communities_list, "disclaimer": METRIC_DISCLAIMER}
