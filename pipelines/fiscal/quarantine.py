"""Quarentena fiscal — nunca descartar silenciosamente; nunca tratar ausente como zero."""

from __future__ import annotations

import hashlib
import json
from typing import Any

FISCAL_REASONS = (
    "INVALID_AMOUNT",
    "INVALID_PERIOD",
    "UNKNOWN_TERRITORY",
    "UNKNOWN_FISCAL_CONCEPT",
    "SCHEMA_CHANGED",
    "DUPLICATE_CONFLICT",
    "MISSING_REQUIRED_FIELD",
)


def quarantine_fiscal(
    reason: str,
    *,
    source_id: str,
    raw_record_id: str | None = None,
    payload: Any = None,
    notes: str | None = None,
    retrieved_at: str | None = None,
) -> dict:
    if reason not in FISCAL_REASONS:
        notes = f"{notes or ''}; reason_custom={reason}".strip("; ")
        reason = "SCHEMA_CHANGED"
    blob = json.dumps(
        {"reason": reason, "payload": payload, "source_id": source_id},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    qid = "q_fisc_" + hashlib.sha1(blob.encode()).hexdigest()[:18]
    return {
        "quarantine_id": qid,
        "reason": reason,
        "source_id": source_id,
        "raw_record_id": raw_record_id,
        "payload": payload,
        "status": "OPEN",
        "created_at": retrieved_at,
        "notes": notes,
        "domain": "fiscal",
    }
