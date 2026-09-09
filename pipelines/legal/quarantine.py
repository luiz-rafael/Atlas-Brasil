"""Quarentena Justiça — nunca descartar silenciosamente."""

from __future__ import annotations

import hashlib
import json
from typing import Any

REASONS = (
    "AMBIGUOUS_PERSON",
    "INVALID_PROCESS_NUMBER",
    "UNKNOWN_COURT",
    "UNKNOWN_TPU_CODE",
    "INVALID_DATE",
    "MISSING_ROLE",
    "ENTITY_CONFLICT",
    "SOURCE_SCHEMA_CHANGED",
)


def quarantine_record(
    reason: str,
    *,
    source_id: str = "cnj_datajud",
    raw_record_id: str | None = None,
    payload: Any = None,
    notes: str | None = None,
    retrieved_at: str | None = None,
) -> dict:
    if reason not in REASONS:
        notes = f"{notes or ''}; reason_custom={reason}".strip("; ")
        reason = "SOURCE_SCHEMA_CHANGED"
    blob = json.dumps({"reason": reason, "payload": payload}, ensure_ascii=False, sort_keys=True, default=str)
    qid = "q_" + hashlib.sha1(blob.encode()).hexdigest()[:20]
    return {
        "quarantine_id": qid,
        "reason": reason,
        "source_id": source_id,
        "raw_record_id": raw_record_id,
        "payload": payload,
        "status": "OPEN",
        "created_at": retrieved_at,
        "notes": notes,
    }
