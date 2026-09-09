"""Projeção SICONFI Silver → Gold (PUBLIC_BUDGET_EXECUTION / PERSONNEL_EXPENDITURE)."""

from __future__ import annotations

import polars as pl

DOMAIN = "dinheiro_publico"


def _str(df: pl.DataFrame, name: str, default: str | None = None) -> pl.Expr:
    if name in df.columns:
        return pl.col(name).cast(pl.Utf8, strict=False)
    return pl.lit(default).cast(pl.Utf8)


def _num(df: pl.DataFrame, name: str) -> pl.Expr:
    if name in df.columns:
        return pl.col(name).cast(pl.Float64, strict=False)
    return pl.lit(None).cast(pl.Float64)


def _int(df: pl.DataFrame, name: str) -> pl.Expr:
    if name in df.columns:
        return pl.col(name).cast(pl.Int64, strict=False)
    return pl.lit(None).cast(pl.Int64)


def to_gold_public_budget_execution(silver: pl.DataFrame) -> pl.DataFrame:
    if silver.is_empty():
        return pl.DataFrame()
    out = silver.select(
        _str(silver, "id").alias("id"),
        pl.lit("PUBLIC_BUDGET_EXECUTION").alias("canonical_model"),
        pl.lit(DOMAIN).alias("atlas_domain"),
        pl.lit("observation").alias("data_type"),
        _str(silver, "territory_id").alias("territory_id"),
        _str(silver, "government_level").alias("government_level"),
        _str(silver, "reference_period").alias("reference_period"),
        _int(silver, "reference_year").alias("reference_year"),
        _num(silver, "revenue_forecast").alias("revenue_forecast"),
        _num(silver, "revenue_realized").alias("revenue_realized"),
        _num(silver, "expense_authorized").alias("expense_authorized"),
        _num(silver, "expense_committed").alias("expense_committed"),
        _num(silver, "expense_liquidated").alias("expense_liquidated"),
        _num(silver, "expense_paid").alias("expense_paid"),
        _num(silver, "restos_a_pagar").alias("restos_a_pagar"),
        _str(silver, "source_id", "siconfi").alias("source_id"),
        _str(silver, "dataset_id", "siconfi.dca").alias("dataset_id"),
        _str(silver, "retrieved_at").alias("retrieved_at"),
        _str(silver, "notes").alias("notes"),
    )
    return out.filter(pl.col("id").is_not_null() & (pl.col("id") != ""))


def to_gold_personnel_expenditure(silver: pl.DataFrame) -> pl.DataFrame:
    if silver.is_empty():
        return pl.DataFrame()
    out = silver.select(
        _str(silver, "id").alias("id"),
        pl.lit("PERSONNEL_EXPENDITURE").alias("canonical_model"),
        pl.lit(DOMAIN).alias("atlas_domain"),
        pl.lit("observation").alias("data_type"),
        _str(silver, "territory_id").alias("territory_id"),
        _str(silver, "government_level").alias("government_level"),
        _str(silver, "reference_period").alias("reference_period"),
        _num(silver, "gross_amount").alias("gross_amount"),
        _num(silver, "active_personnel").alias("active_personnel"),
        _num(silver, "retired_personnel").alias("retired_personnel"),
        _num(silver, "pensions").alias("pensions"),
        _str(silver, "currency", "BRL").alias("currency"),
        _str(silver, "source_id", "siconfi").alias("source_id"),
        _str(silver, "dataset_id", "siconfi.dca").alias("dataset_id"),
        _str(silver, "retrieved_at").alias("retrieved_at"),
        _str(silver, "notes").alias("notes"),
    )
    return out.filter(pl.col("id").is_not_null() & (pl.col("id") != ""))
