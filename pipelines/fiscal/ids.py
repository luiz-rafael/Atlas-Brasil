"""Chaves naturais / IDs determinísticos da camada fiscal."""

from __future__ import annotations

import hashlib
import re


def _slug(s: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (s or "").strip())
    return t.strip("_").lower()[:80] or "x"


def natural_key(*parts: object) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def budget_execution_id(
    *,
    territory_id: str,
    government_level: str,
    reference_period: str,
    dataset_id: str,
    function_code: str | None = None,
    agency_code: str | None = None,
    action_code: str | None = None,
    expense_group_code: str | None = None,
) -> str:
    nk = natural_key(
        territory_id,
        government_level,
        reference_period,
        dataset_id,
        function_code,
        agency_code,
        action_code,
        expense_group_code,
    )
    return f"pbe_{nk}"


def fiscal_result_id(
    *,
    territory_id: str,
    reference_period: str,
    methodology: str,
    dataset_id: str,
) -> str:
    return f"fro_{natural_key(territory_id, reference_period, methodology, dataset_id)}"


def public_debt_id(
    *,
    reference_period: str,
    debt_indicator: str,
    debt_type: str | None,
    dataset_id: str,
    indexer: str | None = None,
    currency: str | None = None,
) -> str:
    return f"pdo_{natural_key(reference_period, debt_indicator, debt_type, dataset_id, indexer, currency)}"


def personnel_id(
    *,
    territory_id: str,
    government_level: str,
    reference_period: str,
    agency_id: str | None,
    dataset_id: str,
) -> str:
    return f"pex_{natural_key(territory_id, government_level, reference_period, agency_id, dataset_id)}"


def period_ym(year: int, month: int) -> str:
    return f"{int(year):04d}-{int(month):02d}"


def period_year(year: int) -> str:
    return f"{int(year):04d}"


def territory_uf(sigla: str) -> str:
    return f"uf_{_slug(sigla).upper()}" if sigla else "unknown"


def territory_mun(ibge7: int | str) -> str:
    return f"mun_{ibge7}"
