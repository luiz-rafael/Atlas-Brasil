#!/usr/bin/env python3
"""Materializa PERSON + editorial_cases a partir da KB de produto (web).

Usa data/atlas-brasil-kb-web.json (escopo produto), não o gold completo.
Uso:
  python -u pipelines/ops/load_persons.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from app.serving_pessoas import _fontes_of, _slim_pessoa  # noqa: E402

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
)
WEB_KB = ROOT / "data" / "atlas-brasil-kb-web.json"
FALLBACK_KB = ROOT / "data" / "atlas-brasil-kb-gold.json"


def load_product_kb() -> dict:
    path = WEB_KB if WEB_KB.is_file() else FALLBACK_KB
    print(f"KB={path} size_mb={path.stat().st_size // (1024 * 1024)}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_profile(kb: dict, e: dict) -> dict:
    person_id = e["id"]
    slim = _slim_pessoa(e)
    regs = [
        r
        for r in (kb.get("registros_pessoa_caso") or [])
        if r.get("pessoa_id") == person_id
    ]
    rels = [
        r
        for r in (kb.get("relacoes") or [])
        if r.get("origem") == person_id or r.get("destino") == person_id
    ]
    caso_idx = {c["id"]: c for c in (kb.get("casos") or []) if c.get("id")}
    casos = {}
    for r in regs:
        cid = r.get("caso_id")
        c = caso_idx.get(cid) if cid else None
        if c:
            casos[c["id"]] = {"id": c["id"], "nome": c.get("nome")}

    labels = {person_id: slim.get("nome") or person_id}
    ent_idx = {x["id"]: x for x in (kb.get("entidades") or []) if x.get("id")}
    for r in rels:
        for nid in (r.get("origem"), r.get("destino")):
            if not nid or nid in labels:
                continue
            node = ent_idx.get(nid) or caso_idx.get(nid)
            labels[nid] = (node or {}).get("nome") or nid

    ids = {person_id}
    for r in rels:
        if r.get("origem"):
            ids.add(r["origem"])
        if r.get("destino"):
            ids.add(r["destino"])
    graph_nodes = []
    for nid in ids:
        node = ent_idx.get(nid) or caso_idx.get(nid)
        graph_nodes.append(
            {
                "id": nid,
                "nome": (node or {}).get("nome") or nid,
                "tipo": (node or {}).get("tipo")
                or ("caso" if nid in caso_idx else "desconhecido"),
            }
        )
    graph_edges = [
        {
            "id": r.get("id"),
            "from": r.get("origem"),
            "to": r.get("destino"),
            "tipo": r.get("tipo"),
            "grau_confirmacao": r.get("grau_confirmacao"),
            "justificativa_documental": r.get("justificativa_documental"),
            "contexto": r.get("contexto"),
            "periodo": r.get("periodo"),
        }
        for r in rels
    ]
    return {
        "ok": True,
        "pessoa": slim,
        "rels": rels,
        "regs": regs,
        "casos": casos,
        "labels": labels,
        "fontes": _fontes_of(e),
        "graphNodes": graph_nodes,
        "graphEdges": graph_edges,
        "source": "postgres",
    }


def main() -> int:
    import psycopg
    from psycopg.types.json import Jsonb

    kb = load_product_kb()
    ents = [
        e
        for e in (kb.get("entidades") or [])
        if e.get("tipo") == "pessoa" and e.get("id") and not e.get("isolada")
    ]
    regs = kb.get("registros_pessoa_caso") or []
    reg_by: dict[str, list] = {}
    for r in regs:
        pid = r.get("pessoa_id")
        if pid:
            reg_by.setdefault(pid, []).append(r)

    print(f"persons={len(ents)} casos={len(kb.get('casos') or [])}")

    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE person_profiles, persons, editorial_cases CASCADE")
            n = 0
            for e in ents:
                pid = e["id"]
                plist = reg_by.get(pid) or []
                badge = plist[0].get("status") if plist else None
                cur.execute(
                    """
                    INSERT INTO persons (
                      person_id, nome, partido, cargo_atual, uf, foto_url,
                      no_poder_2026, tags, mandatos, despesas_resumo,
                      status_badge, registros_count, aliases, source_ids
                    ) VALUES (
                      %(person_id)s, %(nome)s, %(partido)s, %(cargo_atual)s, %(uf)s, %(foto_url)s,
                      %(no_poder_2026)s, %(tags)s, %(mandatos)s, %(despesas_resumo)s,
                      %(status_badge)s, %(registros_count)s, %(aliases)s, %(source_ids)s
                    )
                    ON CONFLICT (person_id) DO UPDATE SET
                      nome = EXCLUDED.nome,
                      partido = EXCLUDED.partido,
                      cargo_atual = EXCLUDED.cargo_atual,
                      uf = EXCLUDED.uf,
                      foto_url = EXCLUDED.foto_url,
                      no_poder_2026 = EXCLUDED.no_poder_2026,
                      tags = EXCLUDED.tags,
                      mandatos = EXCLUDED.mandatos,
                      despesas_resumo = EXCLUDED.despesas_resumo,
                      status_badge = EXCLUDED.status_badge,
                      registros_count = EXCLUDED.registros_count,
                      aliases = EXCLUDED.aliases,
                      source_ids = EXCLUDED.source_ids,
                      updated_at = NOW()
                    """,
                    {
                        "person_id": pid,
                        "nome": e.get("nome") or pid,
                        "partido": e.get("partido"),
                        "cargo_atual": e.get("cargo_atual"),
                        "uf": e.get("uf"),
                        "foto_url": e.get("foto_url"),
                        "no_poder_2026": bool(e.get("no_poder_2026")),
                        "tags": Jsonb(e.get("tags") or []),
                        "mandatos": Jsonb(e.get("mandatos") or []),
                        "despesas_resumo": Jsonb(e.get("despesas_resumo"))
                        if e.get("despesas_resumo") is not None
                        else None,
                        "status_badge": badge,
                        "registros_count": len(plist),
                        "aliases": Jsonb(e.get("aliases") or []),
                        "source_ids": Jsonb(e.get("source_ids") or []),
                    },
                )
                profile = build_profile(kb, e)
                cur.execute(
                    """
                    INSERT INTO person_profiles (person_id, profile)
                    VALUES (%s, %s)
                    ON CONFLICT (person_id) DO UPDATE SET
                      profile = EXCLUDED.profile,
                      updated_at = NOW()
                    """,
                    (pid, Jsonb(profile)),
                )
                n += 1
                if n % 200 == 0:
                    print(f"  … {n}/{len(ents)}")
                    conn.commit()

            c_n = 0
            for c in kb.get("casos") or []:
                cid = c.get("id")
                if not cid:
                    continue
                cur.execute(
                    """
                    INSERT INTO editorial_cases (case_id, nome, periodo, eixos, resumo, payload)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (case_id) DO UPDATE SET
                      nome = EXCLUDED.nome,
                      periodo = EXCLUDED.periodo,
                      eixos = EXCLUDED.eixos,
                      resumo = EXCLUDED.resumo,
                      payload = EXCLUDED.payload,
                      updated_at = NOW()
                    """,
                    (
                        cid,
                        c.get("nome") or cid,
                        c.get("periodo"),
                        Jsonb(c.get("eixos") or []),
                        c.get("resumo") or c.get("sinopse"),
                        Jsonb(c),
                    ),
                )
                c_n += 1
        conn.commit()

    print(f"OK persons={n} editorial_cases={c_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
