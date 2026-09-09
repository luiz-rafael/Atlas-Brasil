"""Gold CONTRACT a partir do silver PNCP."""

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


def to_gold_contract(silver: pl.DataFrame) -> pl.DataFrame:
    if silver.is_empty():
        return pl.DataFrame()
    # contract_id estável
    ids = []
    for row in silver.iter_rows(named=True):
        raw = str(row.get("id_externo") or row.get("numero") or "")
        dig = hashlib.sha1(f"pncp|{raw}".encode()).hexdigest()[:20]
        ids.append(f"ctr_{dig}")
    base = silver.with_columns(pl.Series("contract_id", ids))
    out = base.select(
        pl.col("contract_id"),
        pl.lit("CONTRACT").alias("canonical_model"),
        pl.lit(DOMAIN).alias("atlas_domain"),
        pl.lit("event").alias("data_type"),
        _str(base, "id_externo").alias("external_id"),
        _str(base, "numero").alias("contract_number"),
        _str(base, "compra_pncp").alias("procurement_id"),
        _str(base, "cnpj").alias("cnpj"),
        _str(base, "nome_fornecedor").alias("supplier_name"),
        _str(base, "orgao").alias("agency_name"),
        _str(base, "orgao_cnpj").alias("agency_cnpj"),
        _str(base, "uf").alias("uf"),
        _num(base, "valor").alias("amount"),
        _str(base, "objeto").alias("object"),
        _str(base, "data").alias("signed_at"),
        _str(base, "fonte", "pncp").alias("source_id"),
        pl.lit("pncp.contratos").alias("dataset_id"),
        _str(base, "fetched_at").alias("retrieved_at"),
        _str(base, "raw_ref").alias("evidence_ref"),
    )
    return out.filter(pl.col("contract_id").is_not_null())
