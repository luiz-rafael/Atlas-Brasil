"""Registros canônicos MAGISTRATE / MAGISTRATE_COMPENSATION / COMPENSATION_COMPONENT."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Categorias metodológicas — não são “salário”.
COMPENSATION_CATEGORIES = (
    "base_subsidy",
    "personal_advantages",
    "eventual_advantages",
    "indemnities",
    "retroactive_payments",
    "other_components",
    "discounts",
)


@dataclass
class Magistrate:
    magistrate_id: str
    normalized_name: str
    court_id: str
    position: str | None = None
    source_id: str = "cnj_magistrate_compensation"
    source_person_identifier: str | None = None
    display_name: str | None = None
    resolution_method: str | None = None
    resolution_confidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MagistrateCompensation:
    """Uma competência = um evento financeiro. Não é SCD2."""

    id: str
    magistrate_id: str
    court_id: str
    reference_year: int | None
    reference_month: int | None
    reference_period: str | None
    base_subsidy: float | None = None
    personal_advantages: float | None = None
    eventual_advantages: float | None = None
    indemnities: float | None = None
    retroactive_payments: float | None = None
    other_components: float | None = None
    gross_total: float | None = None
    discounts: float | None = None
    net_total: float | None = None
    source_id: str = "cnj_magistrate_compensation"
    dataset_id: str | None = "cnj_magistrate_compensation"
    raw_record_id: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None
    original_file_url: str | None = None
    original_file_source: str | None = None
    layout_id: str | None = None
    position: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompensationComponent:
    id: str
    compensation_id: str
    component_code: str | None
    component_name: str
    component_category: str
    amount: float | None
    source_id: str = "cnj_magistrate_compensation"
    raw_record_id: str | None = None
    source_column: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QuarantineItem:
    reason_code: str
    payload: dict[str, Any] = field(default_factory=dict)
    entity_hint: str | None = None
    raw_record_id: str | None = None
    source_id: str = "cnj_magistrate_compensation"
    dataset_id: str = "cnj_magistrate_compensation"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
