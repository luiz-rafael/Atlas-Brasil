#!/usr/bin/env python3
"""
Gold merge — campanhas TSE → empresas fornecedoras.

Cria:
  - nós empresa (e_cnpj_*)
  - relação pagou_despesa_campanha_a (pessoa canônica → empresa)
  - campos campanhas_resumo / despesas_campanha na pessoa

Resolve p_tse_{sq} → p_cam_/p_sen_ via source_ids tse:{sq}.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def only_digits(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def main() -> int:
    silver = LAKE / "silver" / "campanhas" / "resumo_latest.jsonl"
    resumos = _load_jsonl(silver)
    if not resumos:
        print("silver campanhas vazio — rode silver_campanhas.py", file=sys.stderr)
        return 1
    if not GOLD.exists():
        print("gold ausente", file=sys.stderr)
        return 1

    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}

    # sq -> person_id canônico + índice por UF/sobrenome
    sq_to_pid: dict[str, str] = {}
    by_uf_sobre: dict[str, list[tuple[str, str]]] = {}

    def _norm(s: str | None) -> str:
        import unicodedata

        s = (s or "").upper()
        s = "".join(
            c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
        )
        return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()

    def _match_nome(camp_nn: str, pessoa_nn: str) -> bool:
        if not camp_nn or not pessoa_nn:
            return False
        if camp_nn == pessoa_nn:
            return True
        ta, tb = set(camp_nn.split()), set(pessoa_nn.split())
        if not ta or not tb:
            return False
        if ta <= tb or tb <= ta:
            return True
        # compartilham sobrenome (último token) + pelo menos um prenome
        if camp_nn.split()[-1] != pessoa_nn.split()[-1]:
            return False
        return len(ta & tb) >= 2

    for e in ents.values():
        if e.get("tipo") != "pessoa":
            continue
        eid = e.get("id") or ""
        if eid.startswith("p_tse_"):
            sq_to_pid.setdefault(eid.replace("p_tse_", "", 1), eid)
        for sid in e.get("source_ids") or []:
            s = str(sid)
            if s.startswith("tse:"):
                sq = s[4:]
                if eid.startswith(("p_cam_", "p_sen_")):
                    sq_to_pid[sq] = eid
                else:
                    sq_to_pid.setdefault(sq, eid)
        uf = (e.get("uf") or "").upper()[:2]
        names = [_norm(e.get("nome"))]
        names.extend(_norm(a) for a in (e.get("aliases") or []))
        for nn in names:
            if not nn or not uf:
                continue
            sobre = nn.split()[-1]
            by_uf_sobre.setdefault(f"{uf}|{sobre}", []).append((nn, eid))

    did = "doc_tse_prestacao_campanha"
    docs[did] = {
        "id": did,
        "tipo": "dados_abertos",
        "titulo": "TSE — Prestação de contas eleitorais (despesas candidatos)",
        "nivel_fonte": "1_primaria",
        "orgao": "tse",
        "url": "https://dadosabertos.tse.jus.br/",
        "casos": [],
    }

    n_link = 0
    n_forn = 0
    n_pessoa = 0
    n_er = 0
    for row in resumos:
        sq = only_digits(row.get("sq_candidato"))
        if not sq:
            continue
        pid = sq_to_pid.get(sq)
        if not pid:
            camp_nn = row.get("nome_norm") or _norm(row.get("nome"))
            uf = (row.get("uf") or "").upper()[:2]
            sobre = camp_nn.split()[-1] if camp_nn else ""
            cands = by_uf_sobre.get(f"{uf}|{sobre}") or []
            hits = [eid for nn, eid in cands if _match_nome(camp_nn, nn)]
            # prefere p_cam_/p_sen_
            hits_casa = [h for h in hits if h.startswith(("p_cam_", "p_sen_"))]
            pick = hits_casa[0] if len(hits_casa) == 1 else (hits[0] if len(hits) == 1 else None)
            if pick:
                pid = pick
                n_er += 1
                pessoa0 = ents.get(pid)
                if pessoa0 is not None:
                    sids = list(pessoa0.get("source_ids") or [])
                    tag = f"tse:{sq}"
                    if tag not in sids:
                        sids.append(tag)
                        pessoa0["source_ids"] = sids
                sq_to_pid[sq] = pid
        if not pid:
            pid = row.get("person_id")
        if not pid:
            continue
        if pid not in ents and str(pid).startswith("p_tse_"):
            ents[pid] = {
                "id": pid,
                "tipo": "pessoa",
                "nome": row.get("nome") or f"Candidato TSE {sq}",
                "tags": ["coletado", "tse_prestacao", "stub"],
                "source_ids": [f"tse:{sq}"],
                "uf": row.get("uf"),
            }
        if pid not in ents:
            continue

        pessoa = ents[pid]
        ano = row.get("ano")
        pessoa["campanhas_resumo"] = {
            "ano": ano,
            "cargo": row.get("cargo"),
            "uf": row.get("uf"),
            "total_despesas": row.get("total_despesas"),
            "qtd_despesas": row.get("qtd_despesas"),
            "fonte": "tse_prestacao",
            "fonte_url": row.get("fonte_url") or "https://dadosabertos.tse.jus.br/",
            "sq_candidato": sq,
            "nome_urna": row.get("nome"),
        }
        pessoa["despesas_campanha"] = (row.get("fornecedores") or [])[:12]
        tags = list(pessoa.get("tags") or [])
        if "tem_campanha_tse" not in tags:
            tags.append("tem_campanha_tse")
        pessoa["tags"] = tags
        n_pessoa += 1

        for forn in row.get("fornecedores") or []:
            cnpj = only_digits(forn.get("cnpj"))
            nome_f = (forn.get("nome") or "").strip()
            if len(cnpj) == 14:
                emp_id = f"e_cnpj_{cnpj}"
            elif nome_f:
                emp_id = f"e_nome_{hashlib.sha1(nome_f.upper().encode()).hexdigest()[:12]}"
            else:
                continue
            if emp_id not in ents:
                ents[emp_id] = {
                    "id": emp_id,
                    "tipo": "empresa",
                    "nome": nome_f or f"CNPJ {cnpj}",
                    "tags": ["coletado", "tse_prestacao", "fornecedor_campanha"],
                    "cnpj": cnpj if len(cnpj) == 14 else None,
                    "source_ids": [f"tse_forn:{cnpj or nome_f}"],
                }
            else:
                if nome_f and str(ents[emp_id].get("nome") or "").startswith("CNPJ"):
                    ents[emp_id]["nome"] = nome_f
                tags_e = list(ents[emp_id].get("tags") or [])
                if "fornecedor_campanha" not in tags_e:
                    tags_e.append("fornecedor_campanha")
                ents[emp_id]["tags"] = tags_e

            rid = f"r_{pid}_{emp_id}_camp_forn_{ano or 'x'}"
            rels[rid] = {
                "id": rid,
                "origem": pid,
                "destino": emp_id,
                "tipo": "pagou_despesa_campanha_a",
                "periodo": str(ano or ""),
                "contexto": f"Campanha eleitoral {ano or ''} — fornecedor TSE",
                "justificativa_documental": (
                    f"Despesa eleitoral contratada (TSE): {nome_f or cnpj} "
                    f"· R$ {forn.get('valor')} · {forn.get('qtd')} registro(s)"
                ),
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [did],
                "fontes": ["tse_prestacao"],
                "nota": "Fornecedor de campanha — não implica irregularidade.",
            }
            n_forn += 1
            n_link += 1

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["campanhas_gold"] = {
        "em": utc_now(),
        "pessoas": n_pessoa,
        "rels_fornecedor": n_forn,
        "er_nome_uf": n_er,
        "resumos_silver": len(resumos),
    }
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    print(f"OK gold campanhas: pessoas={n_pessoa} forn_rels={n_forn} er_nome={n_er}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
