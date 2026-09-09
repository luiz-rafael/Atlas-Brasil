"""Testes unitários — camada fiscal Contas do Brasil."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.fiscal.concepts import NON_EQUIVALENT, SERIES_RTN, concept_note
from pipelines.fiscal.ids import (
    budget_execution_id,
    fiscal_result_id,
    period_ym,
    public_debt_id,
)
from pipelines.fiscal.models import FiscalResultObservation
from pipelines.fiscal.quarantine import FISCAL_REASONS, quarantine_fiscal
from pipelines.fiscal.rtn_client import parse_period, pivot_wanted_series


def test_ids_deterministic():
    a = fiscal_result_id(
        territory_id="terr_br",
        reference_period="2024-01",
        methodology="RTN_ABOVE_THE_LINE",
        dataset_id="tesouro.rtn_fiscal_result",
    )
    b = fiscal_result_id(
        territory_id="terr_br",
        reference_period="2024-01",
        methodology="RTN_ABOVE_THE_LINE",
        dataset_id="tesouro.rtn_fiscal_result",
    )
    assert a == b
    assert a.startswith("fro_")
    c = fiscal_result_id(
        territory_id="terr_br",
        reference_period="2024-01",
        methodology="RTN_BELOW_THE_LINE",
        dataset_id="tesouro.rtn_fiscal_result",
    )
    assert a != c


def test_budget_and_debt_ids():
    assert budget_execution_id(
        territory_id="uf_SP",
        government_level="STATE",
        reference_period="2023",
        dataset_id="siconfi.dca",
    ).startswith("pbe_")
    assert public_debt_id(
        reference_period="2024-01",
        debt_indicator="DPF_STOCK",
        debt_type="Dívida Interna",
        dataset_id="tesouro.dpf_estoque",
    ).startswith("pdo_")
    assert period_ym(2024, 3) == "2024-03"


def test_quarantine_reasons():
    for r in (
        "INVALID_AMOUNT",
        "INVALID_PERIOD",
        "UNKNOWN_TERRITORY",
        "UNKNOWN_FISCAL_CONCEPT",
        "SCHEMA_CHANGED",
        "DUPLICATE_CONFLICT",
        "MISSING_REQUIRED_FIELD",
    ):
        assert r in FISCAL_REASONS
    q = quarantine_fiscal(
        "INVALID_PERIOD",
        source_id="tesouro",
        payload={"period": "x"},
    )
    assert q["reason"] == "INVALID_PERIOD"
    assert q["domain"] == "fiscal"
    q2 = quarantine_fiscal("NOT_A_REAL_REASON", source_id="tesouro")
    assert q2["reason"] == "SCHEMA_CHANGED"


def test_pivot_rtn_series():
    regs = [
        {
            "codigoSerie": "10.04.1",
            "data": "2024-01-01T00:00:00.000Z",
            "valor": -10.5,
        },
        {
            "codigoSerie": "10.01.1",
            "data": "2024-01-01T00:00:00.000Z",
            "valor": 100.0,
        },
        {
            "codigoSerie": "10.08.1",
            "data": "2024-01-01T00:00:00.000Z",
            "valor": 50.0,
        },
        {
            "codigoSerie": "99.99.9",
            "data": "2024-01-01T00:00:00.000Z",
            "valor": 1.0,
        },
    ]
    by = pivot_wanted_series(regs)
    assert "2024-01" in by
    assert by["2024-01"]["primary_result_above"] == -10.5
    assert by["2024-01"]["primary_revenue"] == 100.0
    assert by["2024-01"]["interest"] == 50.0
    assert "primary_expense" not in by["2024-01"]


def test_parse_period():
    y, m, p = parse_period("2024-07-01T00:00:00.000Z")
    assert (y, m, p) == (2024, 7, "2024-07")


def test_concepts_not_collapsed():
    assert "arrecadacao_tributaria_rf" in NON_EQUIVALENT["receita"]
    assert "dpf_estoque" in NON_EQUIVALENT["divida"]
    assert "dbgg" in NON_EQUIVALENT["divida"]
    note = concept_note("DPF", "DBGG")
    assert "não são equivalentes" in note
    assert SERIES_RTN["resultado_primario_gc"]["codigo_serie"] == "10.04.1"


def test_model_roundtrip():
    obs = FiscalResultObservation(
        id="fro_x",
        source_id="tesouro",
        dataset_id="tesouro.rtn_fiscal_result",
        territory_id="terr_br",
        reference_period="2024-01",
        primary_result=1.0,
        methodology="RTN_ABOVE_THE_LINE",
    )
    d = obs.to_dict()
    assert d["primary_result"] == 1.0
    assert d["amount_scale"] == "millions"


if __name__ == "__main__":
    test_ids_deterministic()
    test_budget_and_debt_ids()
    test_quarantine_reasons()
    test_pivot_rtn_series()
    test_parse_period()
    test_concepts_not_collapsed()
    test_model_roundtrip()
    print("OK tests/fiscal/test_fiscal_layer.py")
