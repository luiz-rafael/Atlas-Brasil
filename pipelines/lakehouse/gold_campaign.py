"""Gold CAMPAIGN_EXPENSE a partir do silver TSE prestação."""

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


def to_gold_campaign_expense(silver: pl.DataFrame) -> pl.DataFrame:
    if silver.is_empty():
        return pl.DataFrame()
    ids = []
    for row in silver.iter_rows(named=True):
        key = "|".join(
            [
                str(row.get("sq_candidato") or ""),
                str(row.get("ano") or ""),
                str(row.get("cnpj") or ""),
                str(row.get("nome_fornecedor") or ""),
                str(row.get("valor") or ""),
            ]
        )
        dig = hashlib.sha1(key.encode()).hexdigest()[:20]
        ids.append(f"cex_{dig}")
    base = silver.with_columns(pl.Series("expense_id", ids))
    out = base.select(
        pl.col("expense_id"),
        pl.lit("CAMPAIGN_EXPENSE").alias("canonical_model"),
        pl.lit(DOMAIN).alias("atlas_domain"),
        pl.lit("event").alias("data_type"),
        _str(base, "person_id").alias("person_id"),
        _str(base, "sq_candidato").alias("candidate_seq"),
        _str(base, "nome").alias("candidate_name"),
        _int(base, "ano").alias("election_year"),
        _str(base, "cnpj").alias("supplier_cnpj"),
        _str(base, "nome_fornecedor").alias("supplier_name"),
        _num(base, "valor").alias("amount"),
        _num(base, "qtd").alias("quantity"),
        pl.lit("BRL").alias("currency"),
        _str(base, "fonte", "tse_prestacao").alias("source_id"),
        pl.lit("tse.prestacao_despesas").alias("dataset_id"),
    )
    return out.filter(pl.col("expense_id").is_not_null())
