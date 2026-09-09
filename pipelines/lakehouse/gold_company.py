"""Projeção COMPANY amostra (fila interesse) → Gold canônico."""

from __future__ import annotations

import polars as pl

DOMAIN = "empresas_organizacoes"


def _str(df: pl.DataFrame, name: str, default: str | None = None) -> pl.Expr:
    if name in df.columns:
        return pl.col(name).cast(pl.Utf8, strict=False)
    return pl.lit(default).cast(pl.Utf8)


def to_gold_company(silver: pl.DataFrame) -> pl.DataFrame:
    if silver.is_empty():
        return pl.DataFrame()
    situ = (
        _str(silver, "situacao_cadastral")
        if "situacao_cadastral" in silver.columns
        else _str(silver, "status")
    )
    cnae = (
        _str(silver, "cnae_principal")
        if "cnae_principal" in silver.columns
        else _str(silver, "cnae_fiscal")
    )
    out = silver.select(
        _str(silver, "company_id").alias("company_id"),
        pl.lit("COMPANY").alias("canonical_model"),
        pl.lit(DOMAIN).alias("atlas_domain"),
        pl.lit("entity").alias("data_type"),
        _str(silver, "cnpj").alias("cnpj"),
        _str(silver, "cnpj_basico").alias("cnpj_basico"),
        _str(silver, "razao_social").alias("razao_social"),
        _str(silver, "nome_fantasia").alias("nome_fantasia"),
        situ.alias("status_label"),
        _str(silver, "data_situacao").alias("status_as_of"),
        _str(silver, "natureza_juridica").alias("natureza_juridica"),
        _str(silver, "data_abertura").alias("data_abertura"),
        _str(silver, "porte").alias("porte"),
        _str(silver, "capital_social").alias("capital_social"),
        _str(silver, "uf").alias("uf"),
        _str(silver, "municipio").alias("municipio"),
        cnae.alias("cnae_principal"),
        pl.lit("cnpj_interest_queue").alias("discovery_channel"),
        _str(silver, "source_id", "receita_cnpj").alias("source_id"),
        _str(silver, "dataset_id", "receita.cnpj").alias("dataset_id"),
        _str(silver, "retrieved_at").alias("retrieved_at"),
    )
    return out.filter(
        pl.col("company_id").is_not_null()
        & (pl.col("company_id") != "")
        & pl.col("cnpj").is_not_null()
        & (pl.col("cnpj").str.len_chars() == 14)
    )
