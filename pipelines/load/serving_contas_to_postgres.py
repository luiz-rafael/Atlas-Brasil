#!/usr/bin/env python3
"""
Loader Contas do Brasil / Receita complementar: silver fiscal → Postgres.

Idempotente (ON CONFLICT). Não carrega dump nacional CNPJ.
Não coloca séries fiscais no Neo4j.

Uso:
  python -u pipelines/load/serving_contas_to_postgres.py
  ATLAS_CONTAS_RENUNCIA_MODE=aggregate|full  (default aggregate)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE  # noqa: E402

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
)
FISCAL = LAKE / "silver" / "fiscal"
COMPANIES = LAKE / "silver" / "companies"
BATCH = int(os.getenv("ATLAS_CONTAS_BATCH", "2000") or "2000")
RENUNCIA_MODE = os.getenv("ATLAS_CONTAS_RENUNCIA_MODE", "aggregate").strip().lower()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect():
    import psycopg

    return psycopg.connect(DSN)


def iter_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def ensure_serving_runs(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS serving_load_runs (
          run_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          dataset TEXT NOT NULL,
          started_at TIMESTAMPTZ NOT NULL,
          finished_at TIMESTAMPTZ,
          records_read INT DEFAULT 0,
          records_inserted INT DEFAULT 0,
          records_updated INT DEFAULT 0,
          records_skipped INT DEFAULT 0,
          records_quarantined INT DEFAULT 0,
          status TEXT NOT NULL,
          error TEXT,
          meta JSONB DEFAULT '{}'::jsonb
        )
        """
    )


def start_run(cur, source: str, dataset: str) -> str:
    run_id = f"serving_{source}_{dataset}_{int(time.time())}"
    cur.execute(
        """
        INSERT INTO serving_load_runs
          (run_id, source, dataset, started_at, status)
        VALUES (%s, %s, %s, NOW(), 'RUNNING')
        """,
        (run_id, source, dataset),
    )
    return run_id


def finish_run(cur, run_id: str, stats: dict[str, Any], status: str = "OK", error: str | None = None) -> None:
    cur.execute(
        """
        UPDATE serving_load_runs SET
          finished_at = NOW(),
          records_read = %s,
          records_inserted = %s,
          records_updated = %s,
          records_skipped = %s,
          records_quarantined = %s,
          status = %s,
          error = %s,
          meta = %s::jsonb
        WHERE run_id = %s
        """,
        (
            stats.get("read", 0),
            stats.get("inserted", 0),
            stats.get("updated", 0),
            stats.get("skipped", 0),
            stats.get("quarantined", 0),
            status,
            error,
            json.dumps(stats.get("meta") or {}, ensure_ascii=False),
            run_id,
        ),
    )


def _normalize_budget_row(r: dict) -> dict:
    """Mapeia campos RTN (extra/primary_*) para colunas canônicas sem colapsar estágios."""
    out = dict(r)
    extra = out.get("extra") if isinstance(out.get("extra"), dict) else {}
    if out.get("revenue_realized") is None:
        v = out.get("primary_revenue_rtn") or extra.get("rtn_receita_total")
        if v is not None:
            out["revenue_realized"] = v
    # RTN despesa total ≠ empenho/liquidação/pagamento — guardamos em expense_paid
    # com methodology explícita (não inventar os outros estágios).
    if (
        out.get("expense_paid") is None
        and out.get("expense_liquidated") is None
        and out.get("expense_committed") is None
        and out.get("expense_authorized") is None
    ):
        v = out.get("primary_expense_rtn") or extra.get("rtn_despesa_total")
        if v is not None:
            out["expense_paid"] = v
            note = out.get("notes") or ""
            tag = "RTN_DESPESA_TOTAL mapeada em expense_paid (não é estágio SIAFI)."
            if tag not in note:
                out["notes"] = f"{note} {tag}".strip()
    return out


def upsert_budget(cur, rows: list[dict]) -> tuple[int, int]:
    sql = """
    INSERT INTO public_budget_execution (
      id, source_id, dataset_id, territory_id, government_level,
      reference_year, reference_month, reference_period,
      revenue_forecast, revenue_realized,
      expense_authorized, expense_committed, expense_liquidated, expense_paid,
      restos_a_pagar, function_code, function_name, subfunction_code, subfunction_name,
      agency_code, agency_name, budget_unit_code, budget_unit_name,
      program_code, program_name, action_code, action_name,
      expense_group_code, expense_group_name, currency, amount_scale,
      published_at, retrieved_at, raw_record_id, revised, methodology, notes, extra, updated_at
    ) VALUES (
      %(id)s, %(source_id)s, %(dataset_id)s, %(territory_id)s, %(government_level)s,
      %(reference_year)s, %(reference_month)s, %(reference_period)s,
      %(revenue_forecast)s, %(revenue_realized)s,
      %(expense_authorized)s, %(expense_committed)s, %(expense_liquidated)s, %(expense_paid)s,
      %(restos_a_pagar)s, %(function_code)s, %(function_name)s, %(subfunction_code)s, %(subfunction_name)s,
      %(agency_code)s, %(agency_name)s, %(budget_unit_code)s, %(budget_unit_name)s,
      %(program_code)s, %(program_name)s, %(action_code)s, %(action_name)s,
      %(expense_group_code)s, %(expense_group_name)s, %(currency)s, %(amount_scale)s,
      %(published_at)s, %(retrieved_at)s, %(raw_record_id)s, %(revised)s, %(methodology)s, %(notes)s,
      %(extra)s::jsonb, NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
      revenue_forecast = EXCLUDED.revenue_forecast,
      revenue_realized = EXCLUDED.revenue_realized,
      expense_authorized = EXCLUDED.expense_authorized,
      expense_committed = EXCLUDED.expense_committed,
      expense_liquidated = EXCLUDED.expense_liquidated,
      expense_paid = EXCLUDED.expense_paid,
      restos_a_pagar = EXCLUDED.restos_a_pagar,
      methodology = EXCLUDED.methodology,
      notes = EXCLUDED.notes,
      extra = EXCLUDED.extra,
      retrieved_at = EXCLUDED.retrieved_at,
      updated_at = NOW()
    """
    n = 0
    for raw in rows:
        r = _normalize_budget_row(raw)
        payload = {
            "id": r.get("id"),
            "source_id": r.get("source_id") or "unknown",
            "dataset_id": r.get("dataset_id") or "unknown",
            "territory_id": r.get("territory_id") or "terr_br",
            "government_level": r.get("government_level") or "UNKNOWN",
            "reference_year": r.get("reference_year"),
            "reference_month": r.get("reference_month"),
            "reference_period": r.get("reference_period") or "",
            "revenue_forecast": r.get("revenue_forecast"),
            "revenue_realized": r.get("revenue_realized"),
            "expense_authorized": r.get("expense_authorized"),
            "expense_committed": r.get("expense_committed"),
            "expense_liquidated": r.get("expense_liquidated"),
            "expense_paid": r.get("expense_paid"),
            "restos_a_pagar": r.get("restos_a_pagar"),
            "function_code": r.get("function_code"),
            "function_name": r.get("function_name"),
            "subfunction_code": r.get("subfunction_code"),
            "subfunction_name": r.get("subfunction_name"),
            "agency_code": r.get("agency_code"),
            "agency_name": r.get("agency_name"),
            "budget_unit_code": r.get("budget_unit_code"),
            "budget_unit_name": r.get("budget_unit_name"),
            "program_code": r.get("program_code"),
            "program_name": r.get("program_name"),
            "action_code": r.get("action_code"),
            "action_name": r.get("action_name"),
            "expense_group_code": r.get("expense_group_code"),
            "expense_group_name": r.get("expense_group_name"),
            "currency": r.get("currency") or "BRL",
            "amount_scale": r.get("amount_scale") or "units",
            "published_at": r.get("published_at"),
            "retrieved_at": r.get("retrieved_at"),
            "raw_record_id": r.get("raw_record_id"),
            "revised": bool(r.get("revised") or False),
            "methodology": r.get("methodology"),
            "notes": r.get("notes"),
            "extra": json.dumps(r.get("extra") or {}, ensure_ascii=False),
        }
        if not payload["id"]:
            continue
        cur.execute(sql, payload)
        n += 1
    return n, 0



def upsert_fiscal_result(cur, rows: list[dict]) -> int:
    sql = """
    INSERT INTO fiscal_result_observation (
      id, source_id, dataset_id, territory_id, reference_period,
      primary_revenue, primary_expense, primary_result, nominal_result, interest,
      methodology, currency, amount_scale, published_at, retrieved_at,
      raw_record_id, revised, notes, extra, updated_at
    ) VALUES (
      %(id)s, %(source_id)s, %(dataset_id)s, %(territory_id)s, %(reference_period)s,
      %(primary_revenue)s, %(primary_expense)s, %(primary_result)s, %(nominal_result)s, %(interest)s,
      %(methodology)s, %(currency)s, %(amount_scale)s, %(published_at)s, %(retrieved_at)s,
      %(raw_record_id)s, %(revised)s, %(notes)s, %(extra)s::jsonb, NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
      primary_revenue = EXCLUDED.primary_revenue,
      primary_expense = EXCLUDED.primary_expense,
      primary_result = EXCLUDED.primary_result,
      nominal_result = EXCLUDED.nominal_result,
      interest = EXCLUDED.interest,
      methodology = EXCLUDED.methodology,
      retrieved_at = EXCLUDED.retrieved_at,
      updated_at = NOW()
    """
    n = 0
    for r in rows:
        if not r.get("id") or not r.get("methodology"):
            continue
        cur.execute(
            sql,
            {
                "id": r["id"],
                "source_id": r.get("source_id") or "tesouro",
                "dataset_id": r.get("dataset_id") or "tesouro.rtn_fiscal_result",
                "territory_id": r.get("territory_id") or "terr_br",
                "reference_period": r.get("reference_period"),
                "primary_revenue": r.get("primary_revenue"),
                "primary_expense": r.get("primary_expense"),
                "primary_result": r.get("primary_result"),
                "nominal_result": r.get("nominal_result"),
                "interest": r.get("interest"),
                "methodology": r.get("methodology"),
                "currency": r.get("currency") or "BRL",
                "amount_scale": r.get("amount_scale") or "millions",
                "published_at": r.get("published_at"),
                "retrieved_at": r.get("retrieved_at"),
                "raw_record_id": r.get("raw_record_id"),
                "revised": bool(r.get("revised") or False),
                "notes": r.get("notes"),
                "extra": json.dumps(r.get("extra") or {}, ensure_ascii=False),
            },
        )
        n += 1
    return n


def upsert_debt(cur, rows: list[dict]) -> int:
    sql = """
    INSERT INTO public_debt_observation (
      id, source_id, dataset_id, reference_period, debt_indicator, debt_type,
      stock, issuance, redemption, amortization, interest,
      average_cost, average_maturity, indexer, currency, amount_scale,
      methodology, published_at, retrieved_at, raw_record_id, revised, notes, extra, updated_at
    ) VALUES (
      %(id)s, %(source_id)s, %(dataset_id)s, %(reference_period)s, %(debt_indicator)s, %(debt_type)s,
      %(stock)s, %(issuance)s, %(redemption)s, %(amortization)s, %(interest)s,
      %(average_cost)s, %(average_maturity)s, %(indexer)s, %(currency)s, %(amount_scale)s,
      %(methodology)s, %(published_at)s, %(retrieved_at)s, %(raw_record_id)s, %(revised)s,
      %(notes)s, %(extra)s::jsonb, NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
      stock = EXCLUDED.stock,
      issuance = EXCLUDED.issuance,
      redemption = EXCLUDED.redemption,
      amortization = EXCLUDED.amortization,
      interest = EXCLUDED.interest,
      average_cost = EXCLUDED.average_cost,
      average_maturity = EXCLUDED.average_maturity,
      retrieved_at = EXCLUDED.retrieved_at,
      updated_at = NOW()
    """
    n = 0
    for r in rows:
        if not r.get("id") or not r.get("debt_indicator"):
            continue
        cur.execute(
            sql,
            {
                "id": r["id"],
                "source_id": r.get("source_id") or "tesouro",
                "dataset_id": r.get("dataset_id") or "tesouro.debt",
                "reference_period": r.get("reference_period"),
                "debt_indicator": r.get("debt_indicator"),
                "debt_type": r.get("debt_type"),
                "stock": r.get("stock"),
                "issuance": r.get("issuance"),
                "redemption": r.get("redemption"),
                "amortization": r.get("amortization"),
                "interest": r.get("interest"),
                "average_cost": r.get("average_cost"),
                "average_maturity": r.get("average_maturity"),
                "indexer": r.get("indexer"),
                "currency": r.get("currency") or "BRL",
                "amount_scale": r.get("amount_scale") or "units",
                "methodology": r.get("methodology"),
                "published_at": r.get("published_at"),
                "retrieved_at": r.get("retrieved_at"),
                "raw_record_id": r.get("raw_record_id"),
                "revised": bool(r.get("revised") or False),
                "notes": r.get("notes"),
                "extra": json.dumps(r.get("extra") or {}, ensure_ascii=False),
            },
        )
        n += 1
    return n


def upsert_personnel(cur, rows: list[dict]) -> int:
    sql = """
    INSERT INTO personnel_expenditure (
      id, territory_id, government_level, agency_id, reference_period,
      active_personnel, retired_personnel, pensions, gross_amount,
      source_id, dataset_id, currency, raw_record_id, retrieved_at, notes, extra, updated_at
    ) VALUES (
      %(id)s, %(territory_id)s, %(government_level)s, %(agency_id)s, %(reference_period)s,
      %(active_personnel)s, %(retired_personnel)s, %(pensions)s, %(gross_amount)s,
      %(source_id)s, %(dataset_id)s, %(currency)s, %(raw_record_id)s, %(retrieved_at)s,
      %(notes)s, %(extra)s::jsonb, NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
      active_personnel = EXCLUDED.active_personnel,
      retired_personnel = EXCLUDED.retired_personnel,
      pensions = EXCLUDED.pensions,
      gross_amount = EXCLUDED.gross_amount,
      retrieved_at = EXCLUDED.retrieved_at,
      updated_at = NOW()
    """
    n = 0
    for r in rows:
        if not r.get("id"):
            continue
        cur.execute(
            sql,
            {
                "id": r["id"],
                "territory_id": r.get("territory_id") or "terr_br",
                "government_level": r.get("government_level") or "UNKNOWN",
                "agency_id": r.get("agency_id"),
                "reference_period": r.get("reference_period") or "",
                "active_personnel": r.get("active_personnel"),
                "retired_personnel": r.get("retired_personnel"),
                "pensions": r.get("pensions"),
                "gross_amount": r.get("gross_amount"),
                "source_id": r.get("source_id") or "siconfi",
                "dataset_id": r.get("dataset_id") or "siconfi.personnel",
                "currency": r.get("currency") or "BRL",
                "raw_record_id": r.get("raw_record_id"),
                "retrieved_at": r.get("retrieved_at"),
                "notes": r.get("notes"),
                "extra": json.dumps(r.get("extra") or {}, ensure_ascii=False),
            },
        )
        n += 1
    return n


def load_contencioso(cur) -> dict[str, int]:
    """Contencioso admin RFB → Postgres (≠ LEGAL_CASE)."""
    path = FISCAL / "admin_tax_contencioso_indicators_latest.jsonl"
    if not path.exists():
        path = FISCAL / "admin_tax_contencioso_latest.jsonl"
    read = written = 0
    for r in iter_jsonl(path):
        read += 1
        year = r.get("year")
        src_file = r.get("source_file") or "contencioso"
        case_key = r.get("admin_case_id") or r.get("entity_type") or "stock"
        raw_id = r.get("contencioso_obs_id") or f"atc_{year}_{src_file}_{case_key}"
        obs_id = "".join(
            ch if ch.isalnum() or ch in "_-" else "_" for ch in str(raw_id)
        )[:160]
        cur.execute(
            """
            INSERT INTO admin_tax_contencioso_observation (
              contencioso_obs_id, year, admin_case_id, entity_type,
              quantidade, valor, tempo_medio, territory_id,
              source_id, dataset_id, source_file, retrieved_at, raw, meta
            ) VALUES (
              %s, %s, %s, %s,
              %s, %s, %s, %s,
              %s, %s, %s, %s, %s::jsonb, %s::jsonb
            )
            ON CONFLICT (contencioso_obs_id) DO UPDATE SET
              quantidade = EXCLUDED.quantidade,
              valor = EXCLUDED.valor,
              tempo_medio = EXCLUDED.tempo_medio,
              retrieved_at = EXCLUDED.retrieved_at,
              meta = EXCLUDED.meta
            """,
            (
                obs_id,
                year,
                r.get("admin_case_id"),
                r.get("entity_type") or "ADMINISTRATIVE_TAX_CASE",
                r.get("quantidade"),
                r.get("valor"),
                r.get("tempo_medio"),
                r.get("territory_id") or "terr_br",
                r.get("fonte") or r.get("source_id") or "receita_contencioso",
                r.get("dataset_id") or "rfb.contencioso_admin",
                r.get("source_file"),
                r.get("retrieved_at") or utc_now(),
                json.dumps(r, ensure_ascii=False, default=str),
                json.dumps(
                    {
                        "nota": r.get("nota")
                        or "Contencioso administrativo — nao e LEGAL_CASE",
                        "period_label": r.get("period_label"),
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        written += 1
    return {"read": read, "written": written}


def load_renuncias_aggregate(cur) -> dict[str, int]:
    """Agrega silver tax_expenditure por ano → Postgres (serving, não 228k linhas).

    Também materializa top-N beneficiários por ano (cnpj_raiz + razão social).
    Fonte RFB agregada costuma trazer CNPJ raiz (8 dígitos), não 14 — company_id só
    quando houver 14. Renúncia ≠ pagamento.
    """
    from collections import defaultdict

    top_n = int(os.getenv("ATLAS_CONTAS_RENUNCIA_TOP", "80") or "80")
    totals: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)
    value_types: dict[int, str] = {}
    methodology = None
    # (year, cnpj_raiz) -> accum
    by_ben: dict[tuple[int, str], dict] = {}
    read = 0
    path = FISCAL / "tax_expenditure_latest.jsonl"
    for r in iter_jsonl(path):
        read += 1
        y = r.get("year")
        if not y:
            continue
        v = r.get("valor")
        if v is None:
            continue
        try:
            year = int(y)
            valor = float(v)
        except (TypeError, ValueError):
            continue
        totals[year] += valor
        counts[year] += 1
        value_types[year] = r.get("value_type") or "OBSERVED"
        methodology = methodology or r.get("methodology")

        raiz = (r.get("cnpj_raiz") or "").strip()
        razao = (r.get("razao_social") or "").strip()
        if not raiz and not razao:
            continue
        key = (year, raiz or f"name:{razao[:40]}")
        slot = by_ben.get(key)
        if slot is None:
            by_ben[key] = {
                "year": year,
                "cnpj": r.get("cnpj"),
                "cnpj_raiz": raiz or None,
                "company_id": r.get("company_id"),
                "razao_social": razao or None,
                "tributo": r.get("tributo"),
                "beneficio": r.get("beneficio") or "RENUNCIA_BENEFICIARIO",
                "regime": r.get("regime"),
                "setor": r.get("setor"),
                "cnae": r.get("cnae"),
                "valor": valor,
                "value_type": r.get("value_type") or "OBSERVED",
            }
        else:
            slot["valor"] += valor

    # limpa serving anterior (agg + tops) para evitar lixo
    cur.execute(
        """
        DELETE FROM tax_expenditure
        WHERE source_id = 'receita_renuncias'
          AND (
            beneficio = 'RENUNCIA_TOTAL_ANUAL'
            OR beneficio = 'RENUNCIA_BENEFICIARIO'
            OR cnpj_raiz IS NOT NULL
            OR razao_social IS NOT NULL
          )
        """
    )

    n = 0
    for year, valor in sorted(totals.items()):
        te_id = f"te_agg_br_{year}"
        cur.execute(
            """
            INSERT INTO tax_expenditure (
              tax_expenditure_id, year, tributo, beneficio, regime, setor, cnae,
              valor, value_type, methodology, cnpj, cnpj_raiz, company_id,
              razao_social, territory_id, source_id, dataset_id, source_file,
              retrieved_at, meta
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, NULL, NULL, NULL,
              NULL, 'terr_br', 'receita_renuncias', 'rfb.renuncias_agg', 'tax_expenditure_latest.jsonl',
              %s, %s::jsonb
            )
            ON CONFLICT (tax_expenditure_id) DO UPDATE SET
              valor = EXCLUDED.valor,
              value_type = EXCLUDED.value_type,
              methodology = EXCLUDED.methodology,
              meta = EXCLUDED.meta,
              retrieved_at = EXCLUDED.retrieved_at
            """,
            (
                te_id,
                year,
                "AGGREGATE",
                "RENUNCIA_TOTAL_ANUAL",
                None,
                None,
                None,
                valor,
                value_types.get(year, "OBSERVED"),
                methodology
                or "Soma anual do extrato RFB (agregado). Renúncia ≠ pagamento.",
                utc_now(),
                json.dumps(
                    {
                        "aggregation": "sum_by_year",
                        "rows_summed": counts[year],
                        "nota": "Renúncia fiscal não é pagamento público",
                        "semantic": "TAX_EXPENDITURE_ANNUAL_AGG",
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        n += 1

    # top-N beneficiários por ano
    by_year_list: dict[int, list[dict]] = defaultdict(list)
    for row in by_ben.values():
        by_year_list[row["year"]].append(row)

    ben_n = 0
    for year, rows in by_year_list.items():
        rows.sort(key=lambda x: x["valor"], reverse=True)
        for rank, row in enumerate(rows[: max(1, top_n)], start=1):
            raiz = row.get("cnpj_raiz") or "x"
            te_id = f"te_ben_{year}_{raiz}_{rank}"
            cur.execute(
                """
                INSERT INTO tax_expenditure (
                  tax_expenditure_id, year, tributo, beneficio, regime, setor, cnae,
                  valor, value_type, methodology, cnpj, cnpj_raiz, company_id,
                  razao_social, territory_id, source_id, dataset_id, source_file,
                  retrieved_at, meta
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s,
                  %s, 'terr_br', 'receita_renuncias', 'rfb.renuncias_ben', 'tax_expenditure_latest.jsonl',
                  %s, %s::jsonb
                )
                ON CONFLICT (tax_expenditure_id) DO UPDATE SET
                  valor = EXCLUDED.valor,
                  razao_social = EXCLUDED.razao_social,
                  cnpj_raiz = EXCLUDED.cnpj_raiz,
                  company_id = EXCLUDED.company_id,
                  meta = EXCLUDED.meta,
                  retrieved_at = EXCLUDED.retrieved_at
                """,
                (
                    te_id,
                    year,
                    row.get("tributo"),
                    "RENUNCIA_BENEFICIARIO",
                    row.get("regime"),
                    row.get("setor"),
                    row.get("cnae"),
                    row["valor"],
                    row.get("value_type") or "OBSERVED",
                    "Top beneficiários por valor no extrato RFB (CNPJ raiz). Renúncia ≠ pagamento.",
                    row.get("cnpj"),
                    row.get("cnpj_raiz"),
                    row.get("company_id"),
                    row.get("razao_social"),
                    utc_now(),
                    json.dumps(
                        {
                            "rank": rank,
                            "nota": "Beneficiário identificado por CNPJ raiz / razão social na fonte",
                            "semantic": "TAX_EXPENDITURE_BENEFICIARY",
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            ben_n += 1

    return {
        "read": read,
        "inserted": n + ben_n,
        "updated": 0,
        "skipped": 0,
        "quarantined": 0,
        "aggregate_years": n,
        "beneficiaries": ben_n,
        "top_per_year": top_n,
    }


def load_tax_burden(cur) -> dict[str, int]:
    path = FISCAL / "tax_burden_latest.jsonl"
    n = read = 0
    for r in iter_jsonl(path):
        read += 1
        year = r.get("year")
        if not year:
            continue
        tb_id = r.get("tax_burden_id") or f"tb_br_{year}"
        cur.execute(
            """
            INSERT INTO tax_burden_observation (
              tax_burden_id, year, tax_to_gdp_ratio, amount, amount_unit,
              pib_bilhoes, arrecadacao_bruta_bilhoes, methodology, methodology_notes,
              territory_id, territory_type, source_id, dataset_id, source_file,
              retrieved_at, meta
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb
            )
            ON CONFLICT (tax_burden_id) DO UPDATE SET
              tax_to_gdp_ratio = EXCLUDED.tax_to_gdp_ratio,
              amount = EXCLUDED.amount,
              methodology = EXCLUDED.methodology,
              methodology_notes = EXCLUDED.methodology_notes,
              retrieved_at = EXCLUDED.retrieved_at
            """,
            (
                tb_id,
                int(year),
                r.get("tax_to_gdp_ratio"),
                r.get("amount"),
                r.get("amount_unit") or "BRL",
                r.get("pib_bilhoes"),
                r.get("arrecadacao_bruta_bilhoes"),
                r.get("methodology"),
                json.dumps(r.get("methodology_notes") or {}, ensure_ascii=False),
                r.get("territory_id") or "terr_br",
                r.get("territory_type") or "BRASIL",
                r.get("source") or r.get("source_id") or "receita_carga_tributaria",
                r.get("dataset_id") or "rfb.carga_tributaria",
                r.get("source_file"),
                r.get("retrieved_at") or utc_now(),
                json.dumps({"nota": r.get("nota")}, ensure_ascii=False),
            ),
        )
        n += 1
    return {"read": read, "inserted": n, "updated": 0, "skipped": 0, "quarantined": 0}


def load_cno(cur) -> dict[str, int]:
    path = FISCAL / "cno_works_latest.jsonl"
    n = read = skipped = 0
    sql = """
    INSERT INTO cno_works (
      cno_work_id, cno_id, cnpj, company_id, municipality, uf,
      source_id, dataset_id, source_file, retrieved_at, raw, meta
    ) VALUES (
      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb
    )
    ON CONFLICT (cno_work_id) DO UPDATE SET
      cnpj = EXCLUDED.cnpj,
      company_id = EXCLUDED.company_id,
      municipality = EXCLUDED.municipality,
      uf = EXCLUDED.uf,
      retrieved_at = EXCLUDED.retrieved_at,
      raw = EXCLUDED.raw,
      meta = EXCLUDED.meta
    """
    for r in iter_jsonl(path):
        read += 1
        cno_id = r.get("cno_id")
        if not cno_id:
            skipped += 1
            continue
        work_id = f"cno_{cno_id}_{r.get('cnpj') or 'na'}"
        try:
            cur.execute(
                sql,
                (
                    work_id,
                    str(cno_id),
                    r.get("cnpj"),
                    r.get("company_id"),
                    r.get("municipality"),
                    (str(r.get("uf"))[:2] if r.get("uf") else None),
                    r.get("fonte") or "receita_cno",
                    r.get("dataset_id") or "rfb.cno",
                    r.get("source_file"),
                    r.get("retrieved_at") or utc_now(),
                    json.dumps(r.get("raw") or {}, ensure_ascii=False),
                    json.dumps(
                        {
                            "semantic": r.get("semantic"),
                            "nome_empresarial": r.get("nome_empresarial"),
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            n += 1
        except Exception:
            skipped += 1
            continue
    return {"read": read, "inserted": n, "updated": 0, "skipped": skipped, "quarantined": 0}


def load_companies(cur) -> dict[str, int]:
    path = COMPANIES / "companies_latest.jsonl"
    if not path.exists():
        return {"read": 0, "inserted": 0, "updated": 0, "skipped": 0, "quarantined": 0}
    n = read = skipped = 0
    for r in iter_jsonl(path):
        read += 1
        cid = r.get("company_id") or r.get("id")
        cnpj = r.get("cnpj")
        if not cid or not cnpj:
            skipped += 1
            continue
        try:
            cur.execute(
                """
                INSERT INTO companies (
                  company_id, cnpj, cnpj_basico, razao_social, nome_fantasia,
                  cnae_fiscal, municipio, uf, source, retrieved_at, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT (company_id) DO UPDATE SET
                  razao_social = EXCLUDED.razao_social,
                  nome_fantasia = EXCLUDED.nome_fantasia,
                  cnae_fiscal = COALESCE(EXCLUDED.cnae_fiscal, companies.cnae_fiscal),
                  municipio = COALESCE(EXCLUDED.municipio, companies.municipio),
                  uf = COALESCE(EXCLUDED.uf, companies.uf),
                  retrieved_at = EXCLUDED.retrieved_at,
                  updated_at = NOW()
                """,
                (
                    cid,
                    str(cnpj)[:14],
                    (r.get("cnpj_basico") or str(cnpj)[:8]),
                    r.get("razao_social") or r.get("legal_name"),
                    r.get("nome_fantasia") or r.get("trade_name"),
                    r.get("cnae_fiscal") or r.get("cnae"),
                    r.get("municipio") or r.get("municipality"),
                    r.get("uf"),
                    r.get("source") or "rfb_cnpj",
                    r.get("retrieved_at") or utc_now(),
                ),
            )
            n += 1
        except Exception:
            skipped += 1
            continue
    return {"read": read, "inserted": n, "updated": 0, "skipped": skipped, "quarantined": 0}


def load_jsonl_batched(path: Path, upsert_fn, cur, label: str) -> dict[str, int]:
    batch: list[dict] = []
    read = inserted = 0
    for r in iter_jsonl(path):
        read += 1
        batch.append(r)
        if len(batch) >= BATCH:
            inserted += upsert_fn(cur, batch)
            batch.clear()
            if read % 10000 == 0:
                print(f"  {label}: {read} lidos...", flush=True)
    if batch:
        inserted += upsert_fn(cur, batch)
    return {"read": read, "inserted": inserted, "updated": 0, "skipped": 0, "quarantined": 0}


def adapt_cno_schema(cur) -> None:
    """Garante colunas esperadas em cno_works se migration antiga diferir."""
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'cno_works'
        """
    )
    cols = {r[0] for r in cur.fetchall()}
    if "cno_work_id" not in cols and "cno_id" in cols:
        # migration usa outro layout — adicionar cno_work_id se possível
        try:
            cur.execute("ALTER TABLE cno_works ADD COLUMN IF NOT EXISTS cno_work_id TEXT")
            cur.execute(
                "UPDATE cno_works SET cno_work_id = COALESCE(cno_work_id, cno_id) WHERE cno_work_id IS NULL"
            )
        except Exception:
            pass
    for col, typ in [
        ("uf", "TEXT"),
        ("nome_empresarial", "TEXT"),
        ("raw", "JSONB"),
        ("meta", "JSONB"),
        ("municipality", "TEXT"),
        ("source_file", "TEXT"),
        ("dataset_id", "TEXT"),
        ("source_id", "TEXT"),
        ("retrieved_at", "TIMESTAMPTZ"),
        ("company_id", "TEXT"),
        ("cnpj", "TEXT"),
    ]:
        if col not in cols:
            try:
                cur.execute(f"ALTER TABLE cno_works ADD COLUMN IF NOT EXISTS {col} {typ}")
            except Exception:
                pass
    # PK for upsert
    try:
        cur.execute(
            """
            DO $$ BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'cno_works_pkey_work'
              ) AND EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='cno_works' AND column_name='cno_work_id'
              ) THEN
                BEGIN
                  ALTER TABLE cno_works ADD CONSTRAINT cno_works_pkey_work PRIMARY KEY (cno_work_id);
                EXCEPTION WHEN others THEN NULL;
                END;
              END IF;
            END $$;
            """
        )
    except Exception:
        pass


def main() -> int:
    t0 = time.time()
    try:
        conn = connect()
    except Exception as e:
        print(f"Postgres indisponível: {e}", file=sys.stderr)
        return 1

    results: dict[str, Any] = {}
    with conn:
        with conn.cursor() as cur:
            ensure_serving_runs(cur)
            adapt_cno_schema(cur)

            jobs = [
                (
                    "tesouro",
                    "budget_revenue",
                    FISCAL / "public_budget_execution_revenue.jsonl",
                    lambda c, rows: upsert_budget(c, rows)[0],
                ),
                (
                    "tesouro",
                    "budget_expenditure",
                    FISCAL / "public_budget_execution_expenditure.jsonl",
                    lambda c, rows: upsert_budget(c, rows)[0],
                ),
                (
                    "siconfi",
                    "budget_execution",
                    FISCAL / "public_budget_execution_siconfi.jsonl",
                    lambda c, rows: upsert_budget(c, rows)[0],
                ),
                (
                    "tesouro",
                    "fiscal_result",
                    FISCAL / "fiscal_result_observation.jsonl",
                    upsert_fiscal_result,
                ),
                (
                    "tesouro",
                    "public_debt",
                    FISCAL / "public_debt_observation.jsonl",
                    upsert_debt,
                ),
                (
                    "tesouro",
                    "debt_cost",
                    FISCAL / "public_debt_cost.jsonl",
                    upsert_debt,
                ),
                (
                    "siconfi",
                    "personnel",
                    FISCAL / "personnel_expenditure_siconfi.jsonl",
                    upsert_personnel,
                ),
            ]

            for source, dataset, path, fn in jobs:
                run_id = start_run(cur, source, dataset)
                try:
                    if not path.exists():
                        finish_run(cur, run_id, {"read": 0}, status="SKIPPED", error=f"missing {path}")
                        results[dataset] = {"status": "SKIPPED", "path": str(path)}
                        continue
                    stats = load_jsonl_batched(path, fn, cur, dataset)
                    finish_run(cur, run_id, stats, status="OK")
                    results[dataset] = {"status": "OK", **stats}
                    print(f"OK {dataset}: {stats}", flush=True)
                except Exception as e:
                    finish_run(cur, run_id, {"read": 0}, status="ERROR", error=str(e))
                    results[dataset] = {"status": "ERROR", "error": str(e)}
                    print(f"ERROR {dataset}: {e}", file=sys.stderr)
                    conn.rollback()
                    ensure_serving_runs(cur)

            # renúncias
            run_id = start_run(cur, "receita_renuncias", "tax_expenditure")
            try:
                if RENUNCIA_MODE == "full":
                    # full mode not implemented as primary — aggregate is product serving
                    stats = load_renuncias_aggregate(cur)
                else:
                    stats = load_renuncias_aggregate(cur)
                finish_run(cur, run_id, stats, status="OK")
                results["tax_expenditure"] = {"status": "OK", "mode": RENUNCIA_MODE, **stats}
                print(f"OK tax_expenditure aggregate: {stats}", flush=True)
            except Exception as e:
                finish_run(cur, run_id, {}, status="ERROR", error=str(e))
                results["tax_expenditure"] = {"status": "ERROR", "error": str(e)}
                print(f"ERROR tax_expenditure: {e}", file=sys.stderr)

            run_id = start_run(cur, "receita_carga_tributaria", "tax_burden")
            try:
                stats = load_tax_burden(cur)
                finish_run(cur, run_id, stats, status="OK")
                results["tax_burden"] = {"status": "OK", **stats}
                print(f"OK tax_burden: {stats}", flush=True)
            except Exception as e:
                finish_run(cur, run_id, {}, status="ERROR", error=str(e))
                results["tax_burden"] = {"status": "ERROR", "error": str(e)}

            run_id = start_run(cur, "receita_cno", "cno_works")
            try:
                stats = load_cno(cur)
                finish_run(cur, run_id, stats, status="OK")
                results["cno_works"] = {"status": "OK", **stats}
                print(f"OK cno_works: {stats}", flush=True)
            except Exception as e:
                finish_run(cur, run_id, {}, status="ERROR", error=str(e))
                results["cno_works"] = {"status": "ERROR", "error": str(e)}
                print(f"ERROR cno: {e}", file=sys.stderr)

            run_id = start_run(cur, "rfb_cnpj", "companies")
            try:
                stats = load_companies(cur)
                finish_run(cur, run_id, stats, status="OK")
                results["companies"] = {"status": "OK", **stats}
                print(f"OK companies: {stats}", flush=True)
            except Exception as e:
                finish_run(cur, run_id, {}, status="ERROR", error=str(e))
                results["companies"] = {"status": "ERROR", "error": str(e)}

            run_id = start_run(cur, "receita_contencioso", "admin_tax_contencioso")
            try:
                stats = load_contencioso(cur)
                finish_run(cur, run_id, stats, status="OK" if stats.get("read") else "SKIPPED")
                results["admin_tax_contencioso"] = {"status": "OK", **stats}
                print(f"OK admin_tax_contencioso: {stats}", flush=True)
            except Exception as e:
                finish_run(cur, run_id, {}, status="ERROR", error=str(e))
                results["admin_tax_contencioso"] = {"status": "ERROR", "error": str(e)}
                print(f"ERROR contencioso: {e}", file=sys.stderr)

    out = {
        "finished_at": utc_now(),
        "duration_s": round(time.time() - t0, 2),
        "results": results,
        "disclaimer": "O Atlas não acusa. O Atlas documenta. Renúncia ≠ pagamento. Resultado fiscal canônico ≠ arrecadação RFB − despesa.",
    }
    report = ROOT / "pipelines" / "reports" / "serving_contas_load.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except UnicodeEncodeError:
        print(json.dumps(out, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
