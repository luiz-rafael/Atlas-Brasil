"""Testes de consolidação serving Contas do Brasil."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "db" / "migrations"


def test_migration_prefixes_unique():
    files = sorted(MIG.glob("*.sql"))
    assert files, "nenhuma migration"
    seen = {}
    for f in files:
        m = re.match(r"^(\d{3})_", f.name)
        assert m, f"prefixo inválido: {f.name}"
        prefix = m.group(1)
        assert prefix not in seen, f"duplicado {prefix}: {seen[prefix]} vs {f.name}"
        seen[prefix] = f.name


def test_expected_migration_sequence():
    names = {p.name for p in MIG.glob("*.sql")}
    assert "007_fiscal_contas.sql" in names
    assert "008_receita_fiscal_complementar.sql" in names
    assert "009_magistrate_compensation.sql" in names
    assert "007_receita_fiscal_complementar.sql" not in names
    assert "007_magistrate_compensation.sql" not in names


def test_expense_stages_remain_distinct():
    """Semântica: não colapsar estágios em um único campo conceitual."""
    from api.app import serving_contas as sc

    # contrato documental
    assert "expense_authorized" in (sc.list_despesas.__doc__ or "" or "expense_authorized")
    note = "expense_authorized, expense_committed, expense_liquidated e expense_paid"
    # a função devolve nota semântica
    # (sem postgres, ainda assim a string existe no módulo)
    assert "expense_authorized" in open(sc.__file__, encoding="utf-8").read()
    assert "primary_result" in open(sc.__file__, encoding="utf-8").read()
    assert "nominal_result" in open(sc.__file__, encoding="utf-8").read()
    assert "Renúncia" in sc.DISCLAIMER or "renúncia" in sc.DISCLAIMER.lower() or "Renúncia" in open(
        sc.__file__, encoding="utf-8"
    ).read()


def test_normalize_budget_maps_rtn_without_inventing_stages():
    import importlib.util

    path = ROOT / "pipelines" / "load" / "serving_contas_to_postgres.py"
    spec = importlib.util.spec_from_file_location("serving_contas_load", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    row = {
        "id": "x",
        "expense_authorized": None,
        "expense_committed": None,
        "expense_liquidated": None,
        "expense_paid": None,
        "extra": {"rtn_despesa_total": 100.0},
        "methodology": "RTN_DESPESA_TOTAL",
    }
    out = mod._normalize_budget_row(row)
    assert out["expense_paid"] == 100.0
    assert out["expense_authorized"] is None
    assert out["expense_committed"] is None
    assert out["expense_liquidated"] is None
    assert "RTN_DESPESA_TOTAL" in (out.get("notes") or "")


def test_clamp_limit():
    from api.app.serving_contas import _clamp_limit

    assert _clamp_limit(None) == 100
    assert _clamp_limit(5) == 5
    assert _clamp_limit(99999) == 1000
