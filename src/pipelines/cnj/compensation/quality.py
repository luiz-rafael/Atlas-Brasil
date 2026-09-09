"""Quality checks da remuneração de magistrados."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from src.connectors.cnj.compensation.courts import COURTS_BY_ID


def _money_ok(value: Any) -> bool:
    if value is None:
        return True
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def run_quality(
    *,
    magistrates: list[dict],
    compensations: list[dict],
    components: list[dict],
    quarantine: list[dict],
    layouts: list[dict],
    discovery: dict | None = None,
) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    if not compensations and (discovery or {}).get("counts", {}).get("files"):
        errors.append(
            {
                "code": "NO_PARSED_ROWS",
                "detail": "Arquivos encontrados mas nenhuma linha de magistrado após validação.",
            }
        )

    seen_keys: dict[tuple, list[str]] = defaultdict(list)
    courts = set()
    periods = set()
    for row in compensations:
        courts.add(row.get("court_id"))
        if row.get("reference_year") and row.get("reference_month"):
            periods.add(f"{row['reference_year']:04d}-{int(row['reference_month']):02d}")
        year, month = row.get("reference_year"), row.get("reference_month")
        if year is None or month is None or not (1 <= int(month) <= 12):
            warnings.append(
                {
                    "code": "INVALID_PERIOD",
                    "compensation_id": row.get("id"),
                    "year": year,
                    "month": month,
                }
            )
        court = row.get("court_id")
        if court and court not in COURTS_BY_ID and court != "unknown":
            warnings.append({"code": "UNKNOWN_COURT", "court_id": court, "id": row.get("id")})
        for field in ("gross_total", "discounts", "net_total", "base_subsidy"):
            if not _money_ok(row.get(field)):
                errors.append(
                    {
                        "code": "INVALID_AMOUNT",
                        "field": field,
                        "id": row.get("id"),
                    }
                )
        key = (row.get("magistrate_id"), row.get("court_id"), year, month, row.get("raw_record_id"))
        seen_keys[key].append(row.get("id"))

        gross, disc, net = row.get("gross_total"), row.get("discounts"), row.get("net_total")
        if gross is not None and disc is not None and net is not None:
            expected = float(gross) - float(disc)
            if abs(expected - float(net)) > 0.05:
                warnings.append(
                    {
                        "code": "GROSS_MINUS_DISCOUNTS_NE_NET",
                        "id": row.get("id"),
                        "gross_total": gross,
                        "discounts": disc,
                        "net_total": net,
                        "gross_minus_discounts": round(expected, 2),
                        "note": (
                            "Não assumir identidade matemática. Diárias, órgão de origem "
                            "e teto variam entre tribunais."
                        ),
                    }
                )

    for key, ids in seen_keys.items():
        if len(ids) > 1:
            warnings.append({"code": "DUPLICATE_ROW", "key": [str(x) for x in key], "ids": ids})

    layout_ids = Counter(str(l.get("layout_id")) for l in layouts)
    schema_changed = sum(1 for l in layouts if l.get("confidence") in {"none", "low"})
    q_reasons = Counter(q.get("reason_code") for q in quarantine)

    coverage = {
        "courts": sorted(c for c in courts if c),
        "court_count": len([c for c in courts if c and c != "unknown"]),
        "periods": sorted(periods),
        "period_count": len(periods),
        "magistrates": len(magistrates),
        "compensations": len(compensations),
        "components": len(components),
        "layouts": dict(layout_ids),
        "quarantine_reasons": dict(q_reasons),
        "catalog_courts": len(COURTS_BY_ID),
    }

    critical = bool(errors)
    return {
        "ok": not critical,
        "errors": errors,
        "warnings": warnings,
        "coverage": coverage,
        "schema_changed_sheets": schema_changed,
        "editorial_notes": [
            "gross_total não é sinônimo de subsídio base.",
            "net_total não é valor bruto.",
            "Não rotular pagamento elevado como irregular.",
            "Não inferir supersalário apenas pelo total.",
            "Mostrar composição (componentes) antes de interpretar.",
            "Ausência de campo não vira zero.",
        ],
    }


def build_coverage(
    *,
    discovery: dict,
    download: dict,
    quality: dict,
    magistrates: list[dict],
    compensations: list[dict],
) -> dict[str, Any]:
    courts_found = sorted({m.get("court_id") for m in magistrates if m.get("court_id")})
    periods = sorted(
        {
            f"{c['reference_year']:04d}-{int(c['reference_month']):02d}"
            for c in compensations
            if c.get("reference_year") and c.get("reference_month")
        }
    )
    return {
        "source_id": "cnj_magistrate_compensation",
        "dataset_id": "cnj_magistrate_compensation",
        "portal_url": discovery.get("portal_url"),
        "coverage_start": periods[0] if periods else None,
        "coverage_end": periods[-1] if periods else None,
        "coverage_status": _status(discovery, download, compensations),
        "courts_found": courts_found,
        "periods_found": periods,
        "files_listed": (discovery.get("counts") or {}).get("files"),
        "files_saved": (download.get("counts") or {}).get("saved"),
        "inbox_files": (discovery.get("counts") or {}).get("inbox"),
        "remote_files": (discovery.get("counts") or {}).get("remote"),
        "quality_ok": quality.get("ok"),
        "notes": (
            "Cobertura é a efetivamente encontrada nesta run (portal + tribunais + inbox). "
            "Não inventar histórico. Painel Qlik sem URL estável exige dump na inbox."
        ),
        "incompatibilities": discovery.get("incompatibilities") or [],
    }


def _status(discovery: dict, download: dict, compensations: list) -> str:
    if compensations:
        return "PARTIAL" if (discovery.get("counts") or {}).get("inbox") else "AVAILABLE"
    if (download.get("counts") or {}).get("saved"):
        return "PARTIAL"
    if discovery.get("portal_ok"):
        return "PARTIAL"
    return "UNAVAILABLE"
