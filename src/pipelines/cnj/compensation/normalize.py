"""BRONZE → SILVER: tipagem, período, totais. Ausência permanece null."""

from __future__ import annotations

import hashlib
from typing import Any

from src.models.compensation.canonical import CompensationComponent, MagistrateCompensation
from src.models.compensation.money import decimal_to_float, parse_amount
from src.pipelines.cnj.compensation.quarantine import make_quarantine


def _period(year: int | None, month: int | None) -> str | None:
    if year and month:
        return f"{int(year):04d}-{int(month):02d}"
    if year:
        return f"{int(year):04d}"
    return None


def _comp_id(compensation_id: str, component: dict) -> str:
    basis = "|".join(
        [
            compensation_id,
            str(component.get("component_code") or ""),
            str(component.get("component_name") or ""),
            str(component.get("component_category") or ""),
        ]
    )
    return "cc_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def normalize_rows(
    bronze_rows: list[dict[str, Any]],
    *,
    retrieved_at: str,
    dataset_id: str = "cnj_magistrate_compensation",
) -> dict[str, Any]:
    compensations: list[dict] = []
    components: list[dict] = []
    quarantine: list[dict] = []

    for row in bronze_rows:
        year = row.get("reference_year")
        month = row.get("reference_month")
        try:
            year = int(year) if year not in (None, "") else None
        except (TypeError, ValueError):
            year = None
        try:
            month = int(month) if month not in (None, "") else None
        except (TypeError, ValueError):
            month = None
        if month is not None and not (1 <= month <= 12):
            month = None

        if year is None or month is None:
            quarantine.append(
                make_quarantine(
                    "INVALID_PERIOD",
                    payload={
                        "row_key": row.get("row_key"),
                        "year": row.get("reference_year"),
                        "month": row.get("reference_month"),
                        "filename": row.get("filename"),
                    },
                    entity_hint=row.get("normalized_name"),
                    raw_record_id=row.get("raw_record_id"),
                )
            )

        if not row.get("court_id"):
            quarantine.append(
                make_quarantine(
                    "UNKNOWN_COURT",
                    payload={
                        "row_key": row.get("row_key"),
                        "filename": row.get("filename"),
                        "name": row.get("display_name"),
                    },
                    entity_hint=row.get("normalized_name"),
                    raw_record_id=row.get("raw_record_id"),
                )
            )

        if not row.get("normalized_name") and not row.get("source_person_identifier"):
            quarantine.append(
                make_quarantine(
                    "MISSING_REQUIRED_FIELD",
                    payload={"row_key": row.get("row_key"), "field": "name"},
                    raw_record_id=row.get("raw_record_id"),
                )
            )
            continue

        # Valores: revalida; None permanece None.
        money_fields = (
            "base_subsidy",
            "personal_advantages",
            "eventual_advantages",
            "indemnities",
            "retroactive_payments",
            "other_components",
            "gross_total",
            "discounts",
            "net_total",
        )
        amounts: dict[str, float | None] = {}
        invalid_amount = False
        for field in money_fields:
            raw = row.get(field)
            if raw is None:
                amounts[field] = None
                continue
            parsed = parse_amount(raw)
            if parsed is None and raw not in (None, ""):
                invalid_amount = True
                amounts[field] = None
            else:
                amounts[field] = decimal_to_float(parsed)
        if invalid_amount:
            quarantine.append(
                make_quarantine(
                    "INVALID_AMOUNT",
                    payload={"row_key": row.get("row_key"), "filename": row.get("filename")},
                    entity_hint=row.get("normalized_name"),
                    raw_record_id=row.get("raw_record_id"),
                )
            )

        period = _period(year, month)
        cid_basis = "|".join(
            [
                str(row.get("court_id") or "unknown"),
                str(row.get("row_key") or ""),
                period or "",
                str(row.get("raw_record_id") or ""),
            ]
        )
        compensation_id = "comp_" + hashlib.sha1(cid_basis.encode("utf-8")).hexdigest()[:20]

        rec = MagistrateCompensation(
            id=compensation_id,
            magistrate_id="",  # preenchido no resolve
            court_id=row.get("court_id") or "unknown",
            reference_year=year,
            reference_month=month,
            reference_period=period,
            base_subsidy=amounts["base_subsidy"],
            personal_advantages=amounts["personal_advantages"],
            eventual_advantages=amounts["eventual_advantages"],
            indemnities=amounts["indemnities"],
            retroactive_payments=amounts["retroactive_payments"],
            other_components=amounts["other_components"],
            gross_total=amounts["gross_total"],
            discounts=amounts["discounts"],
            net_total=amounts["net_total"],
            dataset_id=dataset_id,
            raw_record_id=row.get("raw_record_id"),
            retrieved_at=retrieved_at,
            original_file_url=row.get("original_file_url"),
            original_file_source=row.get("original_file_source"),
            layout_id=row.get("layout_id"),
            position=row.get("position"),
        )
        payload = rec.to_dict()
        payload["normalized_name"] = row.get("normalized_name")
        payload["display_name"] = row.get("display_name")
        payload["source_person_identifier"] = row.get("source_person_identifier")
        payload["row_key"] = row.get("row_key")
        compensations.append(payload)

        for comp in row.get("components") or []:
            amount = parse_amount(comp.get("amount"))
            if amount is None:
                continue
            item = CompensationComponent(
                id=_comp_id(compensation_id, comp),
                compensation_id=compensation_id,
                component_code=comp.get("component_code"),
                component_name=str(comp.get("component_name") or comp.get("component_code") or "rubrica"),
                component_category=str(comp.get("component_category") or "other_components"),
                amount=decimal_to_float(amount),
                raw_record_id=row.get("raw_record_id"),
                source_column=comp.get("source_column"),
            )
            components.append(item.to_dict())

    return {
        "compensations": compensations,
        "components": components,
        "quarantine": quarantine,
    }
