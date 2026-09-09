#!/usr/bin/env python3
"""Valida a regra de ouro do grafo AntiSistema.

Nenhuma relação pode existir sem justificativa_documental + fontes.
Também checa IDs órfãos e campos mínimos do schema v1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "antisistema-kb-v1.json"

REQUIRED_REL_FIELDS = (
    "id",
    "origem",
    "destino",
    "tipo",
    "justificativa_documental",
    "grau_confirmacao",
    "fontes",
)


def load_kb() -> dict:
    with KB_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def validate(kb: dict) -> list[str]:
    errors: list[str] = []
    entity_ids = {e["id"] for e in kb.get("entidades", [])}
    case_ids = {c["id"] for c in kb.get("casos", [])}
    # casos também podem ser referenciados como destino de relação
    known = entity_ids | case_ids

    for rel in kb.get("relacoes", []):
        rid = rel.get("id", "<sem-id>")
        for field in REQUIRED_REL_FIELDS:
            if field not in rel or rel[field] in (None, "", []):
                errors.append(f"relação {rid}: campo obrigatório ausente: {field}")
        just = str(rel.get("justificativa_documental", "")).strip()
        if len(just) < 10:
            errors.append(
                f"relação {rid}: justificativa_documental insuficiente (regra de ouro)"
            )
        fontes = rel.get("fontes") or []
        if not isinstance(fontes, list) or len(fontes) < 1:
            errors.append(f"relação {rid}: precisa de ao menos 1 fonte")
        for endpoint in (rel.get("origem"), rel.get("destino")):
            if endpoint and endpoint not in known and not str(endpoint).startswith("c_"):
                # destino pode ser caso_id mesmo se não estiver em entidades
                if endpoint not in case_ids and endpoint not in entity_ids:
                    errors.append(f"relação {rid}: ID órfão: {endpoint}")

    for rpc in kb.get("registros_pessoa_caso", []):
        rid = rpc.get("id", "<sem-id>")
        if rpc.get("pessoa_id") not in entity_ids:
            errors.append(f"registro {rid}: pessoa_id órfão")
        if rpc.get("caso_id") not in case_ids:
            errors.append(f"registro {rid}: caso_id órfão")
        if not rpc.get("fontes"):
            errors.append(f"registro {rid}: sem fontes")
        if rpc.get("status") and rpc.get("camada") not in ("fato", "acusacao", "hipotese"):
            errors.append(f"registro {rid}: camada inválida")

    for fluxo in kb.get("fluxos_financeiros", []):
        fid = fluxo.get("id", "<sem-id>")
        if not fluxo.get("fontes"):
            errors.append(f"fluxo {fid}: sem fontes")
        # impedir promover valor suspeito a comprovado sem campo
        if fluxo.get("valor_comprovado_desviado") and fluxo.get("grau_confirmacao") in (
            "alegacao_sem_prova",
            "hipotese_jornalistica",
        ):
            errors.append(
                f"fluxo {fid}: valor_comprovado_desviado incompatível com grau fraco"
            )

    return errors


def main() -> int:
    if not KB_PATH.exists():
        print(f"ERRO: KB não encontrada em {KB_PATH}", file=sys.stderr)
        return 2
    kb = load_kb()
    errors = validate(kb)
    rel_n = len(kb.get("relacoes", []))
    rpc_n = len(kb.get("registros_pessoa_caso", []))
    print(f"KB {kb.get('meta', {}).get('versao')} — {KB_PATH.name}")
    print(f"entidades={len(kb.get('entidades', []))} registros={rpc_n} relacoes={rel_n}")
    if errors:
        print(f"FALHOU: {len(errors)} problema(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("OK: regra de ouro e integridade referencial básicas passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
