#!/usr/bin/env python3
"""
FASE 6 — cruzamento documental (somente quando as chaves batem).

Cria relação `mesmo_cnpj_emenda_e_contrato` entre:
  - destino de emenda_beneficiou (empresa)
  - destino de fornecido_por (empresa)
quando o CNPJ é idêntico.

Também anota caminhos curtos em meta e no nó empresa.
Não inventa vínculo político→empresa sem documento.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"


def main() -> int:
    if not GOLD.exists():
        print("gold ausente", file=sys.stderr)
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}

    did = "doc_cruzamento_cnpj"
    docs[did] = {
        "id": did,
        "tipo": "metodologia",
        "titulo": "Cruzamento CNPJ emenda (CGU) × contrato (PNCP)",
        "nivel_fonte": "2_derivada",
        "orgao": "atlas",
        "url": None,
        "casos": [],
    }

    emenda_emp: dict[str, list[str]] = {}
    contrato_emp: dict[str, list[str]] = {}
    for r in rels.values():
        if r.get("tipo") == "emenda_beneficiou":
            d = r.get("destino") or ""
            if d.startswith("e_cnpj_"):
                emenda_emp.setdefault(d, []).append(r.get("origem") or "")
        if r.get("tipo") == "fornecido_por":
            d = r.get("destino") or ""
            if d.startswith("e_cnpj_"):
                contrato_emp.setdefault(d, []).append(r.get("origem") or "")

    inter = sorted(set(emenda_emp) & set(contrato_emp))
    n_rel = 0
    caminhos = []
    for eid in inter:
        emp = ents.get(eid) or {}
        emendas = [x for x in emenda_emp[eid] if x]
        contratos = [x for x in contrato_emp[eid] if x]
        for em_id in emendas[:12]:
            for ctr_id in contratos[:12]:
                rid = f"r_cross_{em_id}_{ctr_id}_{eid[-8:]}"
                rels[rid] = {
                    "id": rid,
                    "origem": em_id,
                    "destino": ctr_id,
                    "tipo": "compartilha_fornecedor_cnpj",
                    "periodo": "",
                    "contexto": f"Mesmo CNPJ ({emp.get('cnpj') or eid}) em emenda e contrato",
                    "justificativa_documental": (
                        f"Empresa {emp.get('nome') or eid} é favorecida da emenda "
                        f"e fornecedora do contrato PNCP. "
                        "Não implica irregularidade — coincidência de CNPJ."
                    ),
                    "grau_confirmacao": "fato_documentado",
                    "fonte_ids": [did],
                    "fontes": ["cgu_emenda_documentos", "pncp"],
                    "via_empresa": eid,
                    "nota": "Cruzamento por chave CNPJ — revisar caso a caso.",
                }
                n_rel += 1
        tags = list(emp.get("tags") or [])
        if "cruzamento_emenda_contrato" not in tags:
            tags.append("cruzamento_emenda_contrato")
        emp["tags"] = tags
        emp["cruzamento"] = {
            "emendas": emendas[:8],
            "contratos": contratos[:8],
            "fonte": "cnpj_match",
        }
        ents[eid] = emp
        caminhos.append(
            {
                "empresa_id": eid,
                "cnpj": emp.get("cnpj"),
                "nome": emp.get("nome"),
                "emendas": emendas[:8],
                "contratos": contratos[:8],
            }
        )

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["cruzamento_f6"] = {
        "em": utc_now(),
        "empresas_cnpj_emenda": len(emenda_emp),
        "empresas_cnpj_contrato": len(contrato_emp),
        "intersecao": len(inter),
        "rels": n_rel,
        "amostra": caminhos[:20],
    }
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    print(
        f"OK cruzamento F6: intersecao={len(inter)} "
        f"emenda_cnpjs={len(emenda_emp)} contrato_cnpjs={len(contrato_emp)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
