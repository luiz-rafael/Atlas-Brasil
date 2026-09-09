#!/usr/bin/env python3
"""
Tesouro — despesas do Governo Central (RTN série Despesa total).

≠ despesa autorizada / empenhada / liquidada / paga (estágios orçamentários).
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
DATASET_ID = "tesouro.expenditure"
CONNECTOR_VERSION = "5.2.0"
CODE = SERIES_RTN["despesa_total"]["codigo_serie"]


def main() -> int:
    run = start_run(SOURCE_ID, DATASET_ID)
    retrieved_at = utc_now()
    regs = fetch_resultado_fiscal(tema="10", data_inicio="01/2015", codigo_da_serie=CODE)
    raw = write_raw_record(
        source_id=SOURCE_ID,
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=CONNECTOR_VERSION,
        payload=regs,
        filename="rtn_despesa_total.json",
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
            expense_committed=None,
            expense_paid=None,
            # campo genérico: despesa primária RTN — guardamos em extra + authorized nulo
            amount_scale="millions",
            methodology="RTN_DESPESA_TOTAL",
            retrieved_at=retrieved_at,
            raw_record_id=raw["raw_record_id"],
            notes=(
                "Despesa Total RTN (R$ mi). Não é empenho/liquidação/pagamento. "
                "Valor em extra.rtn_despesa_total."
            ),
            extra={"rtn_despesa_total": val},
        )
        d = obs.to_dict()
        # espelha no campo mais próximo sem fingir estágio orçamentário
        d["expense_liquidated"] = None
        d["primary_expense_rtn"] = val
        rows.append(d)

    outdir = run_bronze_dir(SOURCE_ID, run["ingestion_run_id"])
    day_out = LAKE / "bronze" / SOURCE_ID / retrieved_at[:10]
    day_out.mkdir(parents=True, exist_ok=True)
    write_jsonl(outdir / "public_budget_execution_expenditure.jsonl", rows)
    write_jsonl(day_out / "public_budget_execution_expenditure.jsonl", rows)
    meta = {
        "dataset_id": DATASET_ID,
        "serie": CODE,
        "n": len(rows),
        "concept_warning": "despesa_rtn != despesa_empenhada",
    }
    write_json(outdir / "tesouro_expenditure_meta.json", meta)
    write_json(day_out / "tesouro_expenditure_meta.json", meta)
    append_event("tesouro_expenditure", {"ok": True, "n": len(rows)})
    mark_ingested(
        SOURCE_ID,
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        ok=bool(rows),
        dataset_id=dataset_id_from_env("tesouro_expenditure"),
    )
    print(f"OK tesouro_expenditure: {len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
