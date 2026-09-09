"""Modelos canônicos Contas do Brasil (AGENT_B)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PublicBudgetExecution:
    id: str
    source_id: str
    dataset_id: str
    territory_id: str
    government_level: str
    reference_year: int
    reference_month: int | None
    reference_period: str
    revenue_forecast: float | None = None
    revenue_realized: float | None = None
    expense_authorized: float | None = None
    expense_committed: float | None = None
    expense_liquidated: float | None = None
    expense_paid: float | None = None
    restos_a_pagar: float | None = None
    function_code: str | None = None
    function_name: str | None = None
    subfunction_code: str | None = None
    subfunction_name: str | None = None
    agency_code: str | None = None
    agency_name: str | None = None
    budget_unit_code: str | None = None
    budget_unit_name: str | None = None
    program_code: str | None = None
    program_name: str | None = None
    action_code: str | None = None
    action_name: str | None = None
    expense_group_code: str | None = None
    expense_group_name: str | None = None
    currency: str = "BRL"
    amount_scale: str = "units"  # units | millions
    published_at: str | None = None
    retrieved_at: str | None = None
    raw_record_id: str | None = None
    revised: bool = False
    methodology: str | None = None
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FiscalResultObservation:
    id: str
    source_id: str
    dataset_id: str
    territory_id: str
    reference_period: str
    primary_revenue: float | None = None
    primary_expense: float | None = None
    primary_result: float | None = None
    nominal_result: float | None = None
    interest: float | None = None
    methodology: str = "RTN_ABOVE_THE_LINE"
    currency: str = "BRL"
    amount_scale: str = "millions"
    published_at: str | None = None
    retrieved_at: str | None = None
    raw_record_id: str | None = None
    revised: bool = False
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PublicDebtObservation:
    id: str
    source_id: str
    dataset_id: str
    reference_period: str
    debt_indicator: str
    debt_type: str | None = None
    stock: float | None = None
    issuance: float | None = None
    redemption: float | None = None
    amortization: float | None = None
    interest: float | None = None
    average_cost: float | None = None
    average_maturity: float | None = None
    indexer: str | None = None
    currency: str = "BRL"
    amount_scale: str = "units"
    methodology: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None
    raw_record_id: str | None = None
    revised: bool = False
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PersonnelExpenditure:
    id: str
    territory_id: str
    government_level: str
    reference_period: str
    source_id: str
    dataset_id: str
    agency_id: str | None = None
    active_personnel: float | None = None
    retired_personnel: float | None = None
    pensions: float | None = None
    gross_amount: float | None = None
    currency: str = "BRL"
    raw_record_id: str | None = None
    retrieved_at: str | None = None
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
