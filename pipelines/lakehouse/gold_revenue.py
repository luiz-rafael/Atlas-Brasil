"""Gold PUBLIC_REVENUE_OBSERVATION a partir do extract Receita arrecadação."""

from __future__ import annotations

import hashlib

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


def to_gold_public_revenue(silver: pl.DataFrame) -> pl.DataFrame:
    if silver.is_empty():
        return pl.DataFrame()
    ids = []
    periods = []
    for row in silver.iter_rows(named=True):
        ano = row.get("ano")
        mes = row.get("mes")
        try:
            period = f"{int(ano):04d}-{int(mes):02d}"
        except (TypeError, ValueError):
            period = str(ano or "")
        periods.append(period)
        key = f"{period}|{row.get('territory_id')}|{row.get('rubrica')}"
        dig = hashlib.sha1(key.encode()).hexdigest()[:20]
        ids.append(f"prv_{dig}")
    base = silver.with_columns(
        pl.Series("id", ids),
        pl.Series("reference_period", periods),
    )
    out = base.select(
        pl.col("id"),
        pl.lit("PUBLIC_REVENUE_OBSERVATION").alias("canonical_model"),
        pl.lit(DOMAIN).alias("atlas_domain"),
        pl.lit("observation").alias("data_type"),
        _str(base, "territory_id", "terr_br").alias("territory_id"),
        pl.col("reference_period"),
        _int(base, "ano").alias("reference_year"),
        _int(base, "mes").alias("reference_month"),
        _str(base, "rubrica").alias("revenue_line"),
        _num(base, "valor").alias("amount"),
        _num(base, "valor_milhoes").alias("amount_millions"),
        pl.lit("BRL").alias("currency"),
        pl.lit("millions_source_unit").alias("amount_scale_note"),
        _str(base, "fonte", "receita_arrecadacao").alias("source_id"),
        pl.lit("receita.arrecadacao_federal").alias("dataset_id"),
        pl.lit(
            "Arrecadacao federal RFB — nao cobre toda receita publica BR"
        ).alias("methodology_note"),
        _str(base, "nota").alias("notes"),
    )
    return out.filter(pl.col("id").is_not_null() & pl.col("revenue_line").is_not_null())
