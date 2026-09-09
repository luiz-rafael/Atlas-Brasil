"""Serving PERSON — Postgres first; fallback KB gateway.

O Atlas documenta; não acusa.
"""

import unicodedata
import json
import re
from typing import Any

from app.db import get_conn
from app.kb_loader import load_kb

DISCLAIMER = (
    "O Atlas não acusa. O Atlas documenta. "
    "Processo, investigação ou menção ≠ culpa. "
    "Cargo/mandato documentado ≠ responsabilidade por indicadores do território."
)

LIST_FIELDS = (
    "id",
    "nome",
    "tipo",
    "partido",
    "cargo_atual",
    "uf",
    "foto_url",
    "no_poder_2026",
    "tags",
    "despesas_resumo",
)

_RE_CONGRESSO = re.compile(r"deputad|senador|camara|senado", re.I)
_RE_EXEC = re.compile(
    r"executivo|ministro|presidencia|ministro_stf|judiciario", re.I
)
_RE_STF = re.compile(r"ministro_stf|judiciario", re.I)
_RE_GOV = re.compile(r"governador|tem_mandato_governador|fase7", re.I)


def _escopo_match(e: dict[str, Any], escopo: str | None) -> bool:
    if not escopo:
        return True
    s = escopo.lower()
    cargo = (e.get("cargo_atual") or "").lower()
    tags = e.get("tags") or []
    mandatos = e.get("mandatos") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []
    if isinstance(mandatos, str):
        try:
            mandatos = json.loads(mandatos)
        except Exception:
            mandatos = []

    if s == "congresso":
        return (
            "deputad" in cargo
            or "senador" in cargo
            or "senadora" in cargo
            or any(_RE_CONGRESSO.search(t or "") for t in tags)
        )
    if s in ("presidencia", "executivo"):
        return (
            "president" in cargo
            or "vice" in cargo
            or "ministr" in cargo
            or any(_RE_EXEC.search(t or "") for t in tags)
        )
    if s in ("stf", "judiciario"):
        return any(_RE_STF.search(t or "") for t in tags) or "stf" in cargo
    if s in ("governadores", "estados"):
        return (
            "governador" in cargo
            or any(_RE_GOV.search(t or "") for t in tags)
            or any(
                "governador" in str(m.get("cargo") or "").lower() for m in mandatos
            )
        )
    return True


def _slim_list_item(
    e: dict[str, Any], reg_count: int = 0, status_badge: str | None = None
) -> dict[str, Any]:
    out = {k: e.get(k) for k in LIST_FIELDS}
    out["registros_count"] = reg_count
    if status_badge:
        out["status_badge"] = status_badge
    return out


def _slim_pessoa(e: dict[str, Any]) -> dict[str, Any]:
    out = dict(e)
    leg = out.get("legislativo_resumo")
    if not isinstance(leg, dict):
        return out
    lista = leg.get("proposicoes_lista") or []
    out["legislativo_resumo"] = {
        **leg,
        "proposicao_ids": None,
        "proposicoes_lista": lista[:80],
        "proposicoes_sample": (leg.get("proposicoes_sample") or lista)[:12],
        "votos_por_proposicao": (leg.get("votos_por_proposicao") or [])[:30],
        "votos_projetos": (leg.get("votos_projetos") or [])[:24],
    }
    return out


def _fontes_of(e: dict[str, Any]) -> list[str]:
    if e.get("perfil_fontes"):
        return list(e["perfil_fontes"])
    out: list[str] = []
    if e.get("pagina_oficial"):
        out.append(e["pagina_oficial"])
    for s in e.get("source_ids") or []:
        if isinstance(s, str) and s.startswith("cam:"):
            out.append(
                f"https://dadosabertos.camara.leg.br/api/v2/deputados/{s[4:]}"
            )
        elif isinstance(s, str) and s.startswith("sen:"):
            out.append(
                f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{s[4:]}"
            )
    return out


def _pg_list_rows() -> list[dict[str, Any]] | None:
    conn = get_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT person_id, nome, partido, cargo_atual, uf, foto_url,
                       no_poder_2026, tags, mandatos, despesas_resumo,
                       status_badge, registros_count
                FROM persons
                ORDER BY nome
                """
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            if not rows:
                return None
            for r in rows:
                r["id"] = r.pop("person_id")
                r["tipo"] = "pessoa"
                for k in ("tags", "mandatos", "despesas_resumo"):
                    v = r.get(k)
                    if isinstance(v, str):
                        try:
                            r[k] = json.loads(v)
                        except Exception:
                            pass
            return rows
    except Exception:
        return None


def _fold(s: str) -> str:
    """Remove acentos para busca (José ≈ jose)."""
    norm = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in norm if unicodedata.category(c) != "Mn").lower()


def list_pessoas(
    *,
    q: str | None = None,
    no_poder: str | None = None,
    escopo: str | None = None,
    partido: str | None = None,
    uf: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    pg_rows = _pg_list_rows()
    source = "postgres"
    if pg_rows is None:
        source = "kb_gateway"
        kb = load_kb()
        regs = kb.get("registros_pessoa_caso") or []
        reg_by: dict[str, list] = {}
        for r in regs:
            pid = r.get("pessoa_id")
            if pid:
                reg_by.setdefault(pid, []).append(r)
        pg_rows = []
        for e in kb.get("entidades") or []:
            if e.get("tipo") != "pessoa" or e.get("isolada"):
                continue
            plist = reg_by.get(e["id"]) or []
            badge = plist[0].get("status") if plist else None
            pg_rows.append(
                {
                    **{k: e.get(k) for k in LIST_FIELDS},
                    "id": e["id"],
                    "tipo": "pessoa",
                    "tags": e.get("tags") or [],
                    "mandatos": e.get("mandatos") or [],
                    "registros_count": len(plist),
                    "status_badge": badge,
                }
            )

    items: list[dict[str, Any]] = []
    qn = _fold((q or "").strip())
    uf_n = (uf or "").strip().upper()
    for e in pg_rows:
        if not _escopo_match(e, escopo):
            continue
        if partido and (e.get("partido") or "").lower() != partido.lower():
            continue
        if uf_n and (e.get("uf") or "").upper() != uf_n:
            continue
        if no_poder == "sim" and not e.get("no_poder_2026"):
            continue
        if no_poder == "nao" and e.get("no_poder_2026"):
            continue
        if qn:
            blob = _fold(
                " ".join(
                    [
                        e.get("nome") or "",
                        e.get("partido") or "",
                        e.get("cargo_atual") or "",
                        e.get("uf") or "",
                    ]
                )
            )
            # tokens: "jose silva" exige ambos
            tokens = [t for t in qn.split() if t]
            if tokens and not all(t in blob for t in tokens):
                continue
        items.append(
            _slim_list_item(
                e,
                int(e.get("registros_count") or 0),
                e.get("status_badge"),
            )
        )

    total = len(items)
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))
    return {
        "ok": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items[offset : offset + limit],
        "disclaimer": DISCLAIMER,
        "source": source,
    }


def get_pessoa(person_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT profile FROM person_profiles WHERE person_id = %s",
                    (person_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    profile = row[0]
                    if isinstance(profile, str):
                        profile = json.loads(profile)
                    out = dict(profile)
                    out["disclaimer"] = DISCLAIMER
                    out["source"] = "postgres"
                    return out
        except Exception:
            pass

    kb = load_kb()
    e = next(
        (
            x
            for x in (kb.get("entidades") or [])
            if x.get("id") == person_id and x.get("tipo") == "pessoa"
        ),
        None,
    )
    if not e:
        return None
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
    casos: dict[str, dict] = {}
    caso_idx = {c["id"]: c for c in (kb.get("casos") or []) if c.get("id")}
    for r in regs:
        cid = r.get("caso_id")
        c = caso_idx.get(cid) if cid else None
        if c:
            casos[c["id"]] = {"id": c["id"], "nome": c.get("nome")}

    labels: dict[str, str] = {person_id: slim.get("nome") or person_id}
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
        "disclaimer": DISCLAIMER,
        "source": "kb_gateway",
    }
