"""Quarentena da coleta de remuneração — não descarta o raw da fonte."""

from __future__ import annotations

from typing import Any

from src.models.compensation.canonical import QuarantineItem

REASON_CODES = (
    "AMBIGUOUS_MAGISTRATE",
    "UNKNOWN_COURT",
    "INVALID_AMOUNT",
    "INVALID_PERIOD",
    "SCHEMA_CHANGED",
    "TOTAL_ROW",
    "MISSING_REQUIRED_FIELD",
    "EMPTY_FILE",
    "UNSUPPORTED_FORMAT",
    "ENCODING_ERROR",
    "DUPLICATE_ROW",
)


def make_quarantine(
    reason_code: str,
    *,
    payload: dict[str, Any] | None = None,
    entity_hint: str | None = None,
    raw_record_id: str | None = None,
) -> dict[str, Any]:
    if reason_code not in REASON_CODES:
        payload = {**(payload or {}), "reason_custom": reason_code}
        reason_code = "SCHEMA_CHANGED"
    item = QuarantineItem(
        reason_code=reason_code,
        payload=payload or {},
        entity_hint=entity_hint,
        raw_record_id=raw_record_id,
    )
    return item.to_dict()


def persist_quarantine(items: list[dict[str, Any]], *, run_id: str) -> None:
    try:
        from pipelines.control_plane import quarantine_put
    except Exception:
        return
    for item in items:
        try:
            quarantine_put(
                source_id=item.get("source_id") or "cnj_magistrate_compensation",
                reason_code=item["reason_code"],
                payload=item.get("payload") or {},
                dataset_id=item.get("dataset_id") or "cnj_magistrate_compensation",
                run_id=run_id,
                entity_hint=item.get("entity_hint"),
            )
        except Exception:
            continue
