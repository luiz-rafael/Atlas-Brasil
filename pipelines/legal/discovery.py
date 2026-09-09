"""
Gate de descoberta DataJud — 3 níveis:

1) OFFICIAL_REFERENCE — NPU vindo de STF/STJ/MPF/CGU/etc. ligado a entidade Atlas
2) COMPANY_CONTEXT — descoberta confiável por CNPJ (sem dump indiscriminado)
3) KNOWN_REFRESH — atualização de processos já no Atlas (só se last_movement mudou)

Regra: sem entidade Atlas + evidência → IGNORE/QUARANTINE (não promove a canônico).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pipelines.legal.npu import digits_only, format_npu
from pipelines.legal.quarantine import quarantine_record

DISCOVERY_TYPES = (
    "OFFICIAL_REFERENCE",
    "COMPANY_CONTEXT",
    "PERSON_CONTEXT",
    "KNOWN_REFRESH",
    "MANUAL",
)

INGEST_OK = frozenset({"INGEST"})
INGEST_BLOCK = frozenset({"IGNORE", "QUARANTINE", "PENDING"})


def make_discovery(
    process_number: str,
    *,
    discovered_by_source: str,
    discovery_type: str,
    discovered_by_entity_id: str | None = None,
    discovery_reference: str | None = None,
    discovered_at: str | None = None,
    case_id: str | None = None,
) -> dict:
    d = digits_only(process_number)
    npu = format_npu(d) or process_number
    blob = f"{d}|{discovered_by_source}|{discovery_type}|{discovered_by_entity_id or ''}"
    did = "disc_" + hashlib.sha1(blob.encode()).hexdigest()[:16]
    return {
        "id": did,
        "case_id": case_id or (f"case_cnj_{d}" if len(d) == 20 else None),
        "process_number": npu,
        "process_number_normalized": d,
        "discovered_by_source": discovered_by_source,
        "discovered_by_entity_id": discovered_by_entity_id,
        "discovery_type": discovery_type if discovery_type in DISCOVERY_TYPES else "MANUAL",
        "discovery_reference": discovery_reference,
        "discovered_at": discovered_at,
        "ingest_decision": "PENDING",
        "decision_reason": None,
        "decided_at": None,
    }


def decide_ingest(discovery: dict, *, entity_exists: bool | None = None) -> dict:
    """
    PROCESS DISCOVERED → ligado a entidade Atlas? → evidência suficiente? → INGEST
    Caso contrário IGNORE / QUARANTINE.
    """
    out = dict(discovery)
    dtype = out.get("discovery_type")
    entity = out.get("discovered_by_entity_id")
    digits = out.get("process_number_normalized") or ""

    if len(digits) != 20:
        out["ingest_decision"] = "QUARANTINE"
        out["decision_reason"] = "INVALID_PROCESS_NUMBER"
        return out

    if dtype == "KNOWN_REFRESH":
        out["ingest_decision"] = "INGEST"
        out["decision_reason"] = "known_process_refresh"
        return out

    if dtype == "OFFICIAL_REFERENCE":
        if entity or out.get("discovery_reference"):
            out["ingest_decision"] = "INGEST"
            out["decision_reason"] = "official_npu_reference"
            return out
        out["ingest_decision"] = "QUARANTINE"
        out["decision_reason"] = "MISSING_ROLE"
        return out

    if dtype in ("COMPANY_CONTEXT", "PERSON_CONTEXT"):
        if not entity:
            out["ingest_decision"] = "IGNORE"
            out["decision_reason"] = "not_linked_to_atlas_entity"
            return out
        if entity_exists is False:
            out["ingest_decision"] = "QUARANTINE"
            out["decision_reason"] = "AMBIGUOUS_PERSON"
            return out
        out["ingest_decision"] = "INGEST"
        out["decision_reason"] = f"{dtype.lower()}_scoped"
        return out

    # MANUAL: exige entidade ou referência explícita
    if entity or out.get("discovery_reference"):
        out["ingest_decision"] = "INGEST"
        out["decision_reason"] = "manual_with_anchor"
        return out
    out["ingest_decision"] = "IGNORE"
    out["decision_reason"] = "no_atlas_scope"
    return out


def to_quarantine_if_needed(discovery: dict, retrieved_at: str | None = None) -> dict | None:
    if discovery.get("ingest_decision") != "QUARANTINE":
        return None
    return quarantine_record(
        discovery.get("decision_reason") or "MISSING_ROLE",
        source_id=str(discovery.get("discovered_by_source") or "discovery"),
        raw_record_id=discovery.get("id"),
        payload=discovery,
        notes="Não promovido a LEGAL_CASE canônico",
        retrieved_at=retrieved_at,
    )


def discovery_provenance_blurb(discovery: dict) -> str:
    """Texto UI: por que este processo aparece no Atlas."""
    src = discovery.get("discovered_by_source") or "?"
    npu = discovery.get("process_number") or discovery.get("process_number_normalized")
    return (
        f"Identificado a partir de: {src}\n"
        f"↓\n"
        f"processo nº {npu}\n"
        f"↓\n"
        f"enriquecido com dados do DataJud/CNJ"
    )
