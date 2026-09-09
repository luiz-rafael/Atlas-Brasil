"""Derivação conservadora de CASE_STATUS a partir de movimentos (RULE_DERIVED)."""

from __future__ import annotations

# Códigos TPU — expandir com tabela oficial; defaults conservadores.
ARCHIVED_CODES = {22, 246, 861}  # baixa / arquivamento (verificar TPU vigente)
SUSPENDED_CODES = {265, 11025}  # suspensão (exemplos — validar)

STATUSES = ("EM_ANDAMENTO", "ENCERRADO", "SUSPENSO", "ARQUIVADO", "INCERTO")


def derive_status(movements: list[dict]) -> dict:
    """
    Retorna status atual + movimento âncora.
    Sem movimentos → INCERTO.
    Não mapeia condenação/absolvição — só andamento operacional.
    """
    if not movements:
        return {
            "status": "INCERTO",
            "status_source": "RULE_DERIVED",
            "confidence": "none",
            "derived_from_movement_id": None,
            "notes": "Sem movimentos para derivar status",
        }

    def _ts(m: dict) -> str:
        return str(m.get("movement_date") or m.get("movement_timestamp") or "")

    ordered = sorted(movements, key=_ts)
    last = ordered[-1]
    try:
        code = int(last.get("movement_code")) if last.get("movement_code") is not None else None
    except (TypeError, ValueError):
        code = None

    if code in ARCHIVED_CODES:
        status = "ARQUIVADO"
        conf = "low"
    elif code in SUSPENDED_CODES:
        status = "SUSPENSO"
        conf = "low"
    else:
        # default: em andamento se há movimento recente; não afirmar ENCERRADO sem regra explícita
        status = "EM_ANDAMENTO"
        conf = "low"

    return {
        "status": status,
        "status_source": "RULE_DERIVED",
        "confidence": conf,
        "derived_from_movement_id": last.get("movement_id"),
        "notes": "Status operacional; não implica desfecho de mérito (condenação/absolvição).",
    }
