"""Projeção Silver → Gold canônico (domínio dinheiro_publico).

Gold ≠ dump da fonte: schema de produto + provenance mínima.
Não inclui magistrados / COMPANY em massa.
"""

from __future__ import annotations

from typing import Any

import polars as pl

DOMAIN = "dinheiro_publico"
DATA_TYPE = "observation"

DEBT_GOLD_COLS = [
    "id",
    "canonical_model",
    "atlas_domain",
    "data_type",
    "territory_id",
    "reference_period",
    "debt_indicator",
    "debt_type",
    "stock",
    "issuance",
    "redemption",
    "amortization",
    "interest",
    "average_cost",
    "average_maturity",
    "indexer",
    "currency",
    "amount_scale",
    "source_id",
    "dataset_id",
    "methodology",
    "published_at",
    "retrieved_at",
    "revised",
    "notes",
]

FISCAL_GOLD_COLS = [
    "id",
    "canonical_model",
    "atlas_domain",
    "data_type",
    "territory_id",
    "reference_period",
    "primary_revenue",
    "primary_expense",
    "primary_result",
    "nominal_result",
    "interest",
    "currency",
    "amount_scale",
    "source_id",
    "dataset_id",
    "methodology",
    "published_at",
    "retrieved_at",
    "revised",
    "notes",
]


def _str_col(df: pl.DataFrame, name: str, default: str | None = None) -> pl.Expr:
    if name in df.columns:
        return pl.col(name).cast(pl.Utf8, strict=False)
    return pl.lit(default).cast(pl.Utf8)


def _num_col(df: pl.DataFrame, name: str) -> pl.Expr:
    if name in df.columns:
        return pl.col(name).cast(pl.Float64, strict=False)
    return pl.lit(None).cast(pl.Float64)


def _bool_col(df: pl.DataFrame, name: str) -> pl.Expr:
    if name in df.columns:
        return pl.col(name).cast(pl.Boolean, strict=False).fill_null(False)
    return pl.lit(False)


def to_gold_public_debt(silver: pl.DataFrame) -> pl.DataFrame:
    """Silver public_debt_observation → gold PUBLIC_DEBT_OBSERVATION."""
    if silver.is_empty():
        return pl.DataFrame(schema={c: pl.Utf8 for c in DEBT_GOLD_COLS})

    out = silver.select(
        _str_col(silver, "id").alias("id"),
        pl.lit("PUBLIC_DEBT_OBSERVATION").alias("canonical_model"),
        pl.lit(DOMAIN).alias("atlas_domain"),
        pl.lit(DATA_TYPE).alias("data_type"),
        pl.lit("terr_br").alias("territory_id"),
        _str_col(silver, "reference_period").alias("reference_period"),
        _str_col(silver, "debt_indicator").alias("debt_indicator"),
        _str_col(silver, "debt_type").alias("debt_type"),
        _num_col(silver, "stock").alias("stock"),
        _num_col(silver, "issuance").alias("issuance"),
        _num_col(silver, "redemption").alias("redemption"),
        _num_col(silver, "amortization").alias("amortization"),
        _num_col(silver, "interest").alias("interest"),
        _num_col(silver, "average_cost").alias("average_cost"),
        _num_col(silver, "average_maturity").alias("average_maturity"),
        _str_col(silver, "indexer").alias("indexer"),
        _str_col(silver, "currency", "BRL").alias("currency"),
        _str_col(silver, "amount_scale", "units").alias("amount_scale"),
        _str_col(silver, "source_id", "tesouro").alias("source_id"),
        _str_col(silver, "dataset_id").alias("dataset_id"),
        _str_col(silver, "methodology").alias("methodology"),
        _str_col(silver, "published_at").alias("published_at"),
        _str_col(silver, "retrieved_at").alias("retrieved_at"),
        _bool_col(silver, "revised").alias("revised"),
        _str_col(silver, "notes").alias("notes"),
    )
    # produto: exige id + debt_indicator
    return out.filter(
        pl.col("id").is_not_null()
        & (pl.col("id") != "")
        & pl.col("debt_indicator").is_not_null()
        & (pl.col("debt_indicator") != "")
    )


def to_gold_fiscal_result(silver: pl.DataFrame) -> pl.DataFrame:
    """Silver fiscal_result_observation → gold FISCAL_RESULT_OBSERVATION."""
    if silver.is_empty():
        return pl.DataFrame(schema={c: pl.Utf8 for c in FISCAL_GOLD_COLS})

    out = silver.select(
        _str_col(silver, "id").alias("id"),
        pl.lit("FISCAL_RESULT_OBSERVATION").alias("canonical_model"),
        pl.lit(DOMAIN).alias("atlas_domain"),
        pl.lit(DATA_TYPE).alias("data_type"),
        _str_col(silver, "territory_id", "terr_br").alias("territory_id"),
        _str_col(silver, "reference_period").alias("reference_period"),
        _num_col(silver, "primary_revenue").alias("primary_revenue"),
        _num_col(silver, "primary_expense").alias("primary_expense"),
        _num_col(silver, "primary_result").alias("primary_result"),
        _num_col(silver, "nominal_result").alias("nominal_result"),
        _num_col(silver, "interest").alias("interest"),
        _str_col(silver, "currency", "BRL").alias("currency"),
        _str_col(silver, "amount_scale", "millions").alias("amount_scale"),
        _str_col(silver, "source_id", "tesouro").alias("source_id"),
        _str_col(silver, "dataset_id").alias("dataset_id"),
        _str_col(silver, "methodology").alias("methodology"),
        _str_col(silver, "published_at").alias("published_at"),
        _str_col(silver, "retrieved_at").alias("retrieved_at"),
        _bool_col(silver, "revised").alias("revised"),
        _str_col(silver, "notes").alias("notes"),
    )
    return out.filter(
        pl.col("id").is_not_null()
        & (pl.col("id") != "")
        & pl.col("methodology").is_not_null()
        & (pl.col("methodology") != "")
    )


def gold_table_meta(table: str) -> dict[str, Any]:
    if table == "public_debt_observation":
        return {
            "canonical_model": "PUBLIC_DEBT_OBSERVATION",
            "atlas_domain": DOMAIN,
            "api_hint": "/v1/contas/divida",
        }
    if table == "fiscal_result_observation":
        return {
            "canonical_model": "FISCAL_RESULT_OBSERVATION",
            "atlas_domain": DOMAIN,
            "api_hint": "/v1/contas/resultado",
        }
    return {}
