"""Parser genérico: mapeia aliases e envia o resto para COMPENSATION_COMPONENT."""

from __future__ import annotations

from typing import Any

from src.pipelines.cnj.compensation.parsers.cnj_portaria_63 import (
    parse_contracheque_row,
    parse_rubrica_row,
)
from src.pipelines.cnj.compensation.parsers.detect import canonical_header


def parse_generic_sheet(
    records: list[dict[str, Any]],
    layout: dict[str, Any],
    *,
    court_id: str | None,
    year: int | None,
    month: int | None,
    raw_record_id: str | None,
) -> list[dict[str, Any]]:
    kind = layout.get("sheet_kind") or "unknown"
    layout_id = layout.get("layout_id") or "generic_tabular"
    rows: list[dict[str, Any]] = []
    if kind in {"personal_advantages", "indemnities", "eventual_advantages"}:
        for rec in records:
            parsed = parse_rubrica_row(
                rec,
                category=kind,
                court_id=court_id,
                year=year,
                month=month,
                raw_record_id=raw_record_id,
                layout_id=layout_id,
            )
            if parsed:
                rows.append(parsed)
        return rows
    # Trata como contracheque/wide
    for rec in records:
        mapped = {canonical_header(k): v for k, v in rec.items()}
        parsed = parse_contracheque_row(
            mapped,
            court_id=court_id,
            year=year,
            month=month,
            raw_record_id=raw_record_id,
            layout_id=layout_id,
        )
        if parsed:
            rows.append(parsed)
    return rows
