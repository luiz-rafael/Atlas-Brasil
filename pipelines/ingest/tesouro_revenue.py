#!/usr/bin/env python3
"""
Tesouro — receitas do Governo Central (RTN série Receita Total).

ATENÇÃO conceitual:
  receita_primaria_rtn ≠ arrecadação tributária RFB ≠ receita orçamentária SIAFI.

Emite observações slim + espelho em PUBLIC_BUDGET_EXECUTION só com revenue_realized
(nível União, sem estágio orçamentário completo).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    LAKE,
    append_event,
    run_bronze_dir,
    utc_now,
    write_json,
    write_jsonl,
    write_raw_record,
)
from pipelines.fiscal.concepts import DATASET_URLS, SERIES_RTN  # noqa: E402
from pipelines.fiscal.ids import budget_execution_id, period_ym  # noqa: E402
from pipelines.fiscal.models import PublicBudgetExecution  # noqa: E402
from pipelines.fiscal.rtn_client import fetch_resultado_fiscal, parse_period  # noqa: E402
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402

SOURCE_ID = "tesouro"
DATASET_ID = "tesouro.revenue"
CONNECTOR_VERSION = "5.2.0"
CODE = SERIES_RTN["receita_total"]["codigo_serie"]


def main() -> int:
    run = start_run(SOURCE_ID, DATASET_ID)
    retrieved_at = utc_now()
    regs = fetch_resultado_fiscal(tema="10", data_inicio="01/2015", codigo_da_serie=CODE)
    raw = write_raw_record(
        source_id=SOURCE_ID,
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=CONNECTOR_VERSION,
        payload=regs,
        filename="rtn_receita_total.json",
        source_url=DATASET_URLS["rtn_api"],
        dataset_id=DATASET_ID,
    )

    rows: list[dict] = []
    for reg in regs:
        if str(reg.get("codigoSerie")) != CODE:
            continue
        y, m, period = parse_period(str(reg["data"]))
        try:
            val = float(reg["valor"])
        except (TypeError, ValueError, KeyError):
            continue
        obs = PublicBudgetExecution(
            id=budget_execution_id(
                territory_id="terr_br",
                government_level="UNION",
                reference_period=period,
                dataset_id=DATASET_ID,
            ),
            source_id=SOURCE_ID,
            dataset_id=DATASET_ID,
            territory_id="terr_br",
            government_level="UNION",
            reference_year=y,
            reference_month=m,
            reference_period=period_ym(y, m),
            revenue_realized=val,
            amount_scale="millions",
            methodology="RTN_RECEITA_TOTAL",
            retrieved_at=retrieved_at,
            raw_record_id=raw["raw_record_id"],
            notes="Receita Total RTN (R$ mi). Não confundir com arrecadação RFB.",
        )
        rows.append(obs.to_dict())

    outdir = run_bronze_dir(SOURCE_ID, run["ingestion_run_id"])
    day_out = LAKE / "bronze" / SOURCE_ID / retrieved_at[:10]
    day_out.mkdir(parents=True, exist_ok=True)
    write_jsonl(outdir / "public_budget_execution_revenue.jsonl", rows)
    write_jsonl(day_out / "public_budget_execution_revenue.jsonl", rows)
    meta = {
        "dataset_id": DATASET_ID,
        "serie": CODE,
        "n": len(rows),
        "dataset_url": DATASET_URLS["rtn_ckan"],
        "concept_warning": "arrecadacao_rf != receita_rtn",
    }
    write_json(outdir / "tesouro_revenue_meta.json", meta)
    write_json(day_out / "tesouro_revenue_meta.json", meta)
    append_event("tesouro_revenue", {"ok": True, "n": len(rows)})
    mark_ingested(
        SOURCE_ID,
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        ok=bool(rows),
        dataset_id=dataset_id_from_env("tesouro_revenue"),
    )
    print(f"OK tesouro_revenue: {len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
