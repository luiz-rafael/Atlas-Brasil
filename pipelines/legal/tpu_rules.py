"""
Motor determinístico TPU → LEGAL_EVENT (conservador).

NÃO usa IA para inventar CONDENADO/ABSOLVIDO.
Só emite event_type quando o código TPU estiver na tabela explícita.
Caso contrário → UNKNOWN (não cria aresta acusatória).
"""

from __future__ import annotations

# Códigos TPU nacionais — lista inicial mínima (expandir com tabela oficial CNJ).
# Fontes: Tabelas Processuais Unificadas / movimentos parametrizados DataJud.
# Preferir códigos de baixa ambiguidade; sentenças genéricas ficam UNKNOWN.

TPU_TO_EVENT: dict[int, str] = {
    # exemplos conservadores — arquivamento / baixa (não implica absolvição)
    22: "ARCHIVED_HINT",  # Baixa Definitiva (verificar tabela vigente)
    246: "ARCHIVED_HINT",
    # distribuição / autuação — processo existe
    26: "CASE_DISTRIBUTED",
    51: "CASE_AUTUADO",
}

# Relação Atlas só quando event_type mapear com alta confiança + evidência de polo.
# Por padrão NENHUM código vira CONVICTED_IN / ACQUITTED_IN automaticamente.
EVENT_TO_RELATION: dict[str, str] = {
    # intencionalmente vazio na v1 — relações acusatórias vêm de outras fontes + evidência
}


def classify_movement(code: int | str | None, description: str | None = None) -> dict:
    """Retorna classificação determinística de um movimento."""
    try:
        c = int(str(code).strip()) if code is not None and str(code).strip() else None
    except ValueError:
        c = None
    event = TPU_TO_EVENT.get(c) if c is not None else None
    if not event:
        return {
            "event_type": "UNKNOWN",
            "relation_type": None,
            "confidence": "none",
            "classification_method": "tpu_rules_v1",
            "human_verified": False,
            "movement_code": c,
            "notes": "Código TPU sem regra determinística; não inventar status.",
        }
    return {
        "event_type": event,
        "relation_type": EVENT_TO_RELATION.get(event),
        "confidence": "low",
        "classification_method": "tpu_rules_v1",
        "human_verified": False,
        "movement_code": c,
        "notes": description or None,
    }
