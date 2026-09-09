#!/usr/bin/env python3
"""
Gold FASE 7 — governadores eleitos → pessoa canônica + UF + mandato.

- Nós estado: uf_{SG}
- Nós mandato: tenure_gov_*
- Relação exerce_cargo_governador (pessoa → estado)
- Relação mandato_em (pessoa → tenure)
- Merge ER: nome+UF → p_cam_/p_sen_ quando possível; senão p_tse_{sq}
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"

UF_NOMES = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def tenure_vigente(inicio: str | None, fim: str | None, hoje: date | None = None) -> bool:
    hoje = hoje or date.today()
    try:
        ini = date.fromisoformat((inicio or "")[:10]) if inicio else None
        fim_d = date.fromisoformat((fim or "")[:10]) if fim else None
    except ValueError:
        return False
    if ini and hoje < ini:
        return False
    if fim_d and hoje >= fim_d:
        return False
    return bool(ini or fim_d)


def norm_name(s: str | None) -> str:
    s = (s or "").upper()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def match_canonical(
    nome_norm: str,
    uf: str,
    by_nome: dict[str, list[str]],
    ents: dict[str, dict],
) -> str | None:
    """Match só por nome completo (≥2 tokens) + UF compatível. Sem subset (evita ROCHA)."""
    tokens = [t for t in (nome_norm or "").split() if t]
    if len(tokens) < 2:
        return None
    hits = list(by_nome.get(nome_norm) or [])
    # também tentar sem título militar comum
    for drop in ("CORONEL", "GENERAL", "DOUTOR", "DR", "CAPITAO", "CAPITÃO"):
        if tokens[0] == drop and len(tokens) >= 3:
            alt = " ".join(tokens[1:])
            hits.extend(by_nome.get(alt) or [])
            break

    def uf_ok(pid: str) -> bool:
        e = ents.get(pid) or {}
        eu = (e.get("uf") or "").upper()[:2]
        # aceita se entidade sem UF ou mesma UF
        return (not eu) or eu == uf

    hits = [h for h in dict.fromkeys(hits) if uf_ok(h)]
    casa = [h for h in hits if h.startswith(("p_cam_", "p_sen_"))]
    if len(casa) == 1:
        return casa[0]
    if len(hits) == 1:
        return hits[0]
    return None


def scrub_governor_artifacts(ents: dict[str, dict], rels: dict[str, dict]) -> None:
    """Remove merge anterior de governadores para reaplicar sem ER sujo."""
    for eid in [eid for eid in ents if eid.startswith("tenure_gov_")]:
        ents.pop(eid, None)

    drop_tipos = {"exerceu_mandato", "exerce_cargo_governador", "mandato_no_estado"}
    for rid in [
        rid
        for rid, r in rels.items()
        if (r.get("tipo") or "") in drop_tipos
        and (
            str(r.get("destino") or "").startswith(("tenure_gov_", "uf_"))
            or str(r.get("origem") or "").startswith("tenure_gov_")
            or (r.get("tipo") == "exerce_cargo_governador")
        )
    ]:
        # só remove se ligado a tenure gov ou é exerce_cargo_governador
        r = rels.get(rid) or {}
        if r.get("tipo") == "exerce_cargo_governador":
            rels.pop(rid, None)
        elif str(r.get("destino") or "").startswith("tenure_gov_") or str(
            r.get("origem") or ""
        ).startswith("tenure_gov_"):
            rels.pop(rid, None)
        elif r.get("tipo") == "mandato_no_estado" and str(r.get("origem") or "").startswith(
            "tenure_gov_"
        ):
            rels.pop(rid, None)

    for e in ents.values():
        if e.get("tipo") != "pessoa":
            continue
        mans = [
            m
            for m in (e.get("mandatos") or [])
            if not str(m.get("id") or "").startswith("tenure_gov_")
        ]
        if mans:
            e["mandatos"] = mans
        else:
            e.pop("mandatos", None)
        e["tags"] = [
            t
            for t in (e.get("tags") or [])
            if t not in ("governador", "fase7", "tem_mandato_governador")
        ]



def main() -> int:
    mandatos = _load_jsonl(LAKE / "silver" / "governadores" / "mandatos_latest.jsonl")
    if not mandatos:
        print("silver mandatos vazio — rode silver_governadores.py", file=sys.stderr)
        return 1
    if not GOLD.exists():
        print("gold ausente", file=sys.stderr)
        return 1

    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}
    scrub_governor_artifacts(ents, rels)

    by_nome: dict[str, list[str]] = {}
    for e in ents.values():
        if e.get("tipo") != "pessoa":
            continue
        for n in [e.get("nome"), *(e.get("aliases") or [])]:
            nn = norm_name(n)
            if nn:
                by_nome.setdefault(nn, []).append(e["id"])

    did = "doc_tse_governadores"
    docs[did] = {
        "id": did,
        "tipo": "dados_abertos",
        "titulo": "TSE — Candidatos eleitos a Governador",
        "nivel_fonte": "1_primaria",
        "orgao": "tse",
        "url": "https://dadosabertos.tse.jus.br/",
        "casos": [],
    }

    n_pessoa = 0
    n_er = 0
    n_tenure = 0
    n_uf = 0
    pessoas_unicas: set[str] = set()

    for m in mandatos:
        uf = (m.get("uf") or "").upper()[:2]
        if not uf:
            continue
        uf_id = f"uf_{uf}"
        if uf_id not in ents:
            ents[uf_id] = {
                "id": uf_id,
                "tipo": "estado",
                "nome": UF_NOMES.get(uf, uf),
                "uf": uf,
                "tags": ["coletado", "uf", "fase7"],
                "source_ids": [f"ibge_uf:{uf}"],
            }
            n_uf += 1

        sq = m.get("sq_candidato") or ""
        stub_id = m.get("person_id") or f"p_tse_{sq}"
        nn = m.get("nome_norm") or norm_name(m.get("nome_urna") or m.get("nome"))
        pid = match_canonical(nn, uf, by_nome, ents)
        if not pid:
            # tentar nome civil completo
            pid = match_canonical(norm_name(m.get("nome")), uf, by_nome, ents)
        if pid:
            n_er += 1
        else:
            pid = stub_id

        if pid not in ents:
            vigente = tenure_vigente(m.get("inicio"), m.get("fim"))
            ents[pid] = {
                "id": pid,
                "tipo": "pessoa",
                "nome": m.get("nome_urna") or m.get("nome") or f"Governador {uf}",
                "partido": m.get("partido"),
                "uf": uf,
                "cargo_atual": "Governador" if vigente else "Ex-governador",
                "no_poder_2026": vigente,
                "tags": ["coletado", "governador", "fase7", "tem_mandato_governador"],
                "source_ids": [f"tse:{sq}"] if sq else [],
                "aliases": [m.get("nome")] if m.get("nome") and m.get("nome") != m.get("nome_urna") else [],
            }
            by_nome.setdefault(nn, []).append(pid)
        else:
            pessoa = ents[pid]
            sids = list(pessoa.get("source_ids") or [])
            tag = f"tse:{sq}"
            if sq and tag not in sids:
                sids.append(tag)
                pessoa["source_ids"] = sids
            tags = list(pessoa.get("tags") or [])
            for t in ("governador", "fase7", "tem_mandato_governador"):
                if t not in tags:
                    tags.append(t)
            pessoa["tags"] = tags
            vigente = tenure_vigente(m.get("inicio"), m.get("fim"))
            cargo = (pessoa.get("cargo_atual") or "").lower()
            # só sobrescreve cargo em stub TSE / já governador; Casa federal mantém
            if str(pid).startswith("p_tse_") or "governador" in cargo or not cargo:
                if vigente:
                    pessoa["cargo_atual"] = "Governador"
                    pessoa["uf"] = uf
                    pessoa["no_poder_2026"] = True
                    if m.get("partido"):
                        pessoa["partido"] = m.get("partido")
                elif not pessoa.get("no_poder_2026"):
                    pessoa["cargo_atual"] = pessoa.get("cargo_atual") or "Ex-governador"
            if m.get("partido") and not pessoa.get("partido"):
                pessoa["partido"] = m.get("partido")
            al = list(pessoa.get("aliases") or [])
            for a in (m.get("nome"), m.get("nome_urna")):
                if a and a != pessoa.get("nome") and a not in al:
                    al.append(a)
            pessoa["aliases"] = al

        pessoa = ents[pid]
        mand_list = list(pessoa.get("mandatos") or [])
        mid = m.get("id")
        if not any(x.get("id") == mid for x in mand_list):
            mand_list.append(
                {
                    "id": mid,
                    "cargo": "Governador",
                    "uf": uf,
                    "partido": m.get("partido"),
                    "ano_eleicao": m.get("ano_eleicao"),
                    "inicio": m.get("inicio"),
                    "fim": m.get("fim"),
                    "fonte": "tse_ckan",
                }
            )
            pessoa["mandatos"] = mand_list
        # timeline: mais recente primeiro
        pessoa = ents[pid]
        if pessoa.get("mandatos"):
            pessoa["mandatos"] = sorted(
                pessoa["mandatos"],
                key=lambda x: (x.get("ano_eleicao") or 0, x.get("inicio") or ""),
                reverse=True,
            )
        pessoas_unicas.add(pid)
        n_pessoa += 1

        tid = mid or f"tenure_gov_{uf}_{m.get('ano_eleicao')}"
        ents[tid] = {
            "id": tid,
            "tipo": "mandato",
            "nome": f"Governador {uf} ({m.get('ano_eleicao')})",
            "cargo": "Governador",
            "uf": uf,
            "periodo_inicio": m.get("inicio"),
            "periodo_fim": m.get("fim"),
            "tags": ["coletado", "office_tenure", "fase7"],
            "source_ids": [f"tse_tenure:{sq}"],
        }
        n_tenure += 1

        rid_m = f"r_{pid}_{tid}_mandato"
        rels[rid_m] = {
            "id": rid_m,
            "origem": pid,
            "destino": tid,
            "tipo": "exerceu_mandato",
            "periodo": f"{m.get('inicio') or ''}–{m.get('fim') or ''}",
            "contexto": f"Mandato de Governador — {uf}",
            "justificativa_documental": (
                f"Eleito Governador {uf} em {m.get('ano_eleicao')} (TSE SQ {sq})"
            ),
            "grau_confirmacao": "fato_documentado",
            "fonte_ids": [did],
            "fontes": ["tse_ckan"],
        }
        rid_u = f"r_{pid}_{uf_id}_gov_{m.get('ano_eleicao') or 'x'}"
        rels[rid_u] = {
            "id": rid_u,
            "origem": pid,
            "destino": uf_id,
            "tipo": "exerce_cargo_governador",
            "periodo": str(m.get("ano_eleicao") or ""),
            "contexto": f"Governador do {UF_NOMES.get(uf, uf)}",
            "justificativa_documental": (
                f"Resultado TSE {m.get('ano_eleicao')}: ELEITO · {m.get('nome_urna') or m.get('nome')}"
            ),
            "grau_confirmacao": "fato_documentado",
            "fonte_ids": [did],
            "fontes": ["tse_ckan"],
        }
        rid_tu = f"r_{tid}_{uf_id}_admin"
        rels[rid_tu] = {
            "id": rid_tu,
            "origem": tid,
            "destino": uf_id,
            "tipo": "mandato_no_estado",
            "periodo": f"{m.get('inicio') or ''}–{m.get('fim') or ''}",
            "contexto": "Office tenure → Estado",
            "justificativa_documental": f"Mandato estadual {uf}",
            "grau_confirmacao": "fato_documentado",
            "fonte_ids": [did],
            "fontes": ["tse_ckan"],
        }

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["governadores_gold"] = {
        "em": utc_now(),
        "pessoas": len(pessoas_unicas),
        "er_nome": n_er,
        "mandatos": n_tenure,
        "ufs": n_uf,
        "silver": len(mandatos),
    }
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    print(
        f"OK gold governadores: pessoas={len(pessoas_unicas)} er={n_er} "
        f"tenures={n_tenure} ufs_novas={n_uf}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
