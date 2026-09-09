#!/usr/bin/env python3
"""Valida ATLAS BRASIL KB (v2) — regra de ouro do grafo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "atlas-brasil-kb-v2.json"
TAX_PATH = ROOT / "data" / "atlas-brasil-taxonomias-v2.json"

REQUIRED_REL = (
    "id",
    "origem",
    "destino",
    "tipo",
    "justificativa_documental",
    "grau_confirmacao",
    "fontes",
)

# tipos extras aceitos (legado + enrich)
EXTRA_TIPOS = {
    "conhece",
    "trabalhou_com",
    "citado_por",
    "investigado_junto",
    "indicou",
    "nomeou",
    "julgou",
    "delatou",
    "foi_delatado_por",
    "financiou",
    "contratou",
    "recebeu_dinheiro_de_empresa_ligada",
    "filiado",
    "membro_de",
    "controla",
    "investigou",
    "familiar_de",
    "condenado",
    "participou_de",
    "anulou_provas_de",
    "integrante_de",
    "lideranca_de",
    "rival_de",
    "dissidencia_de",
    "conexao_potencial",
    "investigado_mesmo_caso",
    "alegacao_nao_confirmada",
}


def all_relation_types(tax: dict) -> set[str]:
    tipos = set(EXTRA_TIPOS)
    for group in tax.get("tipos_relacao", {}).values():
        tipos.update(group)
    return tipos


def validate(kb: dict, tax: dict) -> list[str]:
    errors: list[str] = []
    allowed = all_relation_types(tax)
    entity_ids = {e["id"] for e in kb.get("entidades", [])}
    case_ids = {c["id"] for c in kb.get("casos", [])}
    doc_ids = {d["id"] for d in kb.get("documentos", [])}
    known = entity_ids | case_ids

    for doc in kb.get("documentos", []):
        did = doc.get("id", "<sem-id>")
        url = doc.get("url") or doc.get("url_ref") or ""
        if url and not str(url).startswith("http"):
            errors.append(f"documento {did}: url deve ser HTTPS/HTTP completo (ou vazio)")
        if not url:
            # aviso suave — não bloqueia se url_pendente editorial
            pass

    for rel in kb.get("relacoes", []):
        rid = rel.get("id", "<sem-id>")
        for field in REQUIRED_REL:
            if field not in rel or rel[field] in (None, "", []):
                errors.append(f"relação {rid}: ausente {field}")
        just = str(rel.get("justificativa_documental", "")).strip()
        if len(just) < 10:
            errors.append(f"relação {rid}: justificativa_documental insuficiente")
        if not rel.get("fontes"):
            errors.append(f"relação {rid}: sem fontes")
        if not rel.get("fonte_ids"):
            errors.append(f"relação {rid}: sem fonte_ids")
        for fid in rel.get("fonte_ids") or []:
            if fid not in doc_ids:
                errors.append(f"relação {rid}: fonte_id órfão {fid}")
        tipo = rel.get("tipo")
        if tipo and tipo not in allowed:
            errors.append(f"relação {rid}: tipo desconhecido '{tipo}'")
        for endpoint in (rel.get("origem"), rel.get("destino")):
            if endpoint and endpoint not in known:
                errors.append(f"relação {rid}: ID órfão {endpoint}")

    for rpc in kb.get("registros_pessoa_caso", []):
        rid = rpc.get("id", "<sem-id>")
        if rpc.get("pessoa_id") not in entity_ids:
            errors.append(f"registro {rid}: pessoa_id órfão")
        if rpc.get("caso_id") not in case_ids:
            errors.append(f"registro {rid}: caso_id órfão")
        if not rpc.get("fontes"):
            errors.append(f"registro {rid}: sem fontes")
        if rpc.get("camada") not in ("fato", "acusacao", "hipotese"):
            errors.append(f"registro {rid}: camada inválida")

    for fluxo in kb.get("fluxos_financeiros", []):
        fid = fluxo.get("id", "<sem-id>")
        if not fluxo.get("fontes"):
            errors.append(f"fluxo {fid}: sem fontes")
        if fluxo.get("valor_comprovado_desviado") and fluxo.get("grau_confirmacao") in (
            "alegacao_sem_prova",
            "hipotese_jornalistica",
        ):
            errors.append(f"fluxo {fid}: comprovado incompatível com grau fraco")

    # Centrão não pode ser tipado como org criminosa sem prova
    for rel in kb.get("relacoes", []):
        if rel.get("destino") == "conceito_centrao" and rel.get("tipo") in (
            "condenado",
            "reu",
            "investigado_mesmo_caso",
        ):
            errors.append(
                f"relação {rel.get('id')}: Centrão não pode receber tipo jurídico criminal sem dossiê individual"
            )

    # órfãos sem isolada
    linked = set()
    for rel in kb.get("relacoes", []):
        linked.add(rel.get("origem"))
        linked.add(rel.get("destino"))
    for rpc in kb.get("registros_pessoa_caso", []):
        linked.add(rpc.get("pessoa_id"))
        linked.add(rpc.get("caso_id"))
    for e in kb.get("entidades", []):
        if e["id"] not in linked and not e.get("isolada") and e.get("tipo") in (
            "pessoa",
            "empresa",
            "partido",
            "faccao",
            "organizacao_criminosa",
            "operacao",
        ):
            errors.append(f"entidade {e['id']}: sem aresta e sem flag isolada")

    return errors


def main() -> int:
    if not KB_PATH.exists():
        print(f"ERRO: {KB_PATH}", file=sys.stderr)
        return 2
    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))
    tax = json.loads(TAX_PATH.read_text(encoding="utf-8")) if TAX_PATH.exists() else {}
    errors = validate(kb, tax)
    print(f"ATLAS BRASIL KB {kb.get('meta', {}).get('versao')}")
    print(
        f"entidades={len(kb.get('entidades', []))} "
        f"registros={len(kb.get('registros_pessoa_caso', []))} "
        f"relacoes={len(kb.get('relacoes', []))} "
        f"timeline={len(kb.get('timeline', []))} "
        f"casos={len(kb.get('casos', []))}"
    )
    if errors:
        print(f"FALHOU: {len(errors)}")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("OK: regra de ouro + taxonomia + integridade.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
