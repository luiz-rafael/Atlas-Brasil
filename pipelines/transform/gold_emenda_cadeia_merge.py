#!/usr/bin/env python3
"""
Gold — cadeia emenda → execução documental → beneficiário (CNPJ/órgão).

Relações:
  emenda --executada_via_documento--> (implícito no resumo)
  emenda --beneficiou--> empresa|orgao
  pessoa já tem autor_de_emenda

Enriquece emendas_resumo na pessoa com beneficiários top.
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


def emenda_id_for(codigo: str, ents: dict) -> str | None:
    tag = f"cgu_emenda:{codigo}"
    for e in ents.values():
        if e.get("tipo") != "emenda":
            continue
        if e.get("codigo") == codigo:
            return e["id"]
        sids = e.get("source_ids") or []
        if tag in sids or codigo in sids:
            return e["id"]
    # fallback hash igual ao gold_cgu
    return f"em_{hashlib.sha1(codigo.encode()).hexdigest()[:12]}"


def main() -> int:
    resumos = _load_jsonl(LAKE / "silver" / "emenda_transferencias" / "resumo_latest.jsonl")
    if not resumos:
        print("silver emenda_transferencias vazio", file=sys.stderr)
        return 1
    if not GOLD.exists():
        print("gold ausente", file=sys.stderr)
        return 1

    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}

    did = "doc_cgu_emenda_documentos"
    docs[did] = {
        "id": did,
        "tipo": "dados_abertos",
        "titulo": "Portal da Transparência — documentos de emendas parlamentares",
        "nivel_fonte": "1_primaria",
        "orgao": "cgu",
        "url": "https://portaldatransparencia.gov.br/",
        "casos": [],
    }

    n_em = 0
    n_ben = 0
    n_rel = 0
    by_person: dict[str, list[dict]] = {}

    for row in resumos:
        codigo = str(row.get("codigo_emenda") or "")
        if not codigo:
            continue
        eid = emenda_id_for(codigo, ents)
        if eid not in ents:
            ents[eid] = {
                "id": eid,
                "tipo": "emenda",
                "nome": f"Emenda {codigo}",
                "codigo": codigo,
                "ano": row.get("ano"),
                "localidade": row.get("localidade"),
                "tags": ["coletado", "cgu_portal"],
                "source_ids": [f"cgu_emenda:{codigo}"],
            }
        em = ents[eid]
        bens = row.get("beneficiarios") or []
        em["execucao_resumo"] = {
            "qtd_documentos": row.get("qtd_documentos"),
            "valor_documentos": row.get("valor_total"),
            "beneficiarios": bens[:8],
            "fonte": "cgu_emenda_documentos",
            "fonte_url": row.get("fonte_url"),
        }
        tags = list(em.get("tags") or [])
        if "tem_execucao_documental" not in tags:
            tags.append("tem_execucao_documental")
        em["tags"] = tags
        n_em += 1

        pid = row.get("person_id")
        if pid:
            by_person.setdefault(pid, []).append(
                {
                    "codigo": codigo,
                    "emenda_id": eid,
                    "ano": row.get("ano"),
                    "localidade": row.get("localidade"),
                    "qtd_documentos": row.get("qtd_documentos"),
                    "valor_docs": row.get("valor_total"),
                    "beneficiarios": bens[:5],
                }
            )

        for b in bens:
            cnpj = only_digits(b.get("cnpj"))
            nome = (b.get("nome") or "").strip()
            orgao_nome = (b.get("orgao") or "").strip()
            dest_id = None
            if len(cnpj) == 14:
                dest_id = f"e_cnpj_{cnpj}"
                if dest_id not in ents:
                    ents[dest_id] = {
                        "id": dest_id,
                        "tipo": "empresa",
                        "nome": nome or f"CNPJ {cnpj}",
                        "cnpj": cnpj,
                        "tags": ["coletado", "beneficiario_emenda"],
                        "source_ids": [f"cgu_fav:{cnpj}"],
                    }
                else:
                    tags_e = list(ents[dest_id].get("tags") or [])
                    if "beneficiario_emenda" not in tags_e:
                        tags_e.append("beneficiario_emenda")
                    ents[dest_id]["tags"] = tags_e
                    if nome and str(ents[dest_id].get("nome") or "").startswith("CNPJ"):
                        ents[dest_id]["nome"] = nome
            elif orgao_nome or nome:
                label = orgao_nome or nome
                dest_id = f"o_em_{hashlib.sha1(label.upper().encode()).hexdigest()[:12]}"
                if dest_id not in ents:
                    ents[dest_id] = {
                        "id": dest_id,
                        "tipo": "instituicao",
                        "nome": label,
                        "tags": ["coletado", "beneficiario_emenda", "orgao"],
                        "source_ids": [f"cgu_org:{label[:40]}"],
                    }
            if not dest_id:
                continue
            n_ben += 1
            rid = f"r_{eid}_{dest_id}_em_ben"
            rels[rid] = {
                "id": rid,
                "origem": eid,
                "destino": dest_id,
                "tipo": "emenda_beneficiou",
                "periodo": str(row.get("ano") or ""),
                "contexto": f"Execução documental da emenda {codigo}",
                "justificativa_documental": (
                    f"Documento Portal/CGU · {nome or orgao_nome or cnpj} "
                    f"· R$ {b.get('valor')} · {b.get('qtd')} doc(s)"
                ),
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [did],
                "fontes": ["cgu_emenda_documentos"],
                "nota": "Favorecido em documento de empenho/pagamento — não implica irregularidade.",
            }
            n_rel += 1

    # enriquece emendas_resumo na pessoa
    n_pessoa = 0
    for pid, extras in by_person.items():
        pessoa = ents.get(pid)
        if not pessoa:
            continue
        base = list(pessoa.get("emendas_resumo") or [])
        by_cod = {str(x.get("codigo")): dict(x) for x in base if x.get("codigo")}
        for ex in extras:
            cod = str(ex["codigo"])
            slot = by_cod.get(cod) or {
                "codigo": cod,
                "emenda_id": ex.get("emenda_id"),
                "ano": ex.get("ano"),
                "localidade": ex.get("localidade"),
            }
            slot["qtd_documentos"] = ex.get("qtd_documentos")
            slot["valor_docs"] = ex.get("valor_docs")
            slot["beneficiarios"] = ex.get("beneficiarios")
            if not slot.get("emenda_id"):
                slot["emenda_id"] = ex.get("emenda_id")
            by_cod[cod] = slot
        pessoa["emendas_resumo"] = list(by_cod.values())
        tags = list(pessoa.get("tags") or [])
        if "tem_emenda_execucao" not in tags:
            tags.append("tem_emenda_execucao")
        pessoa["tags"] = tags
        n_pessoa += 1

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["emenda_cadeia_gold"] = {
        "em": utc_now(),
        "emendas": n_em,
        "beneficiarios": n_ben,
        "rels": n_rel,
        "pessoas": n_pessoa,
    }
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    print(
        f"OK gold emenda cadeia: emendas={n_em} bens={n_ben} "
        f"rels={n_rel} pessoas={n_pessoa}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
