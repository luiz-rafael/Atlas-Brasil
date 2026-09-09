#!/usr/bin/env python3
"""
Tesouro — Resultado Fiscal (RTN) via API Séries Temporais.

Dataset oficial:
  https://www.tesourotransparente.gov.br/ckan/dataset/resultado-do-tesouro-nacional
  API: https://apiapex.tesouro.gov.br/aria/v1/series-temporais/docs

Gera FISCAL_RESULT_OBSERVATION (acima da linha + abaixo da linha + nominal).
Valores em R$ milhões (amount_scale=millions). Território: terr_br.
"""

from __future__ import annotations

import os
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
from pipelines.fiscal.ids import fiscal_result_id  # noqa: E402
from pipelines.fiscal.models import FiscalResultObservation  # noqa: E402
from pipelines.fiscal.quarantine import quarantine_fiscal  # noqa: E402
from pipelines.fiscal.rtn_client import fetch_wanted_series, pivot_wanted_series  # noqa: E402
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402

SOURCE_ID = "tesouro"
DATASET_ID = "tesouro.rtn_fiscal_result"
CONNECTOR_VERSION = "5.2.0"


def build_observations(
    by_period: dict[str, dict[str, float]],
    *,
    raw_record_id: str,
    retrieved_at: str,
) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    quarantined: list[dict] = []
    for period, vals in sorted(by_period.items()):
        if len(period) != 7 or period[4] != "-":
            quarantined.append(
                quarantine_fiscal(
                    "INVALID_PERIOD",
                    source_id=SOURCE_ID,
                    raw_record_id=raw_record_id,
                    payload={"period": period, "vals": vals},
                    retrieved_at=retrieved_at,
                )
            )
            continue

        # Acima da linha (preferido para decomposição receita/despesa)
        above = FiscalResultObservation(
            id=fiscal_result_id(
                territory_id="terr_br",
                reference_period=period,
                methodology="RTN_ABOVE_THE_LINE",
                dataset_id=DATASET_ID,
            ),
            source_id=SOURCE_ID,
            dataset_id=DATASET_ID,
            territory_id="terr_br",
            reference_period=period,
            primary_revenue=vals.get("primary_revenue"),
            primary_expense=vals.get("primary_expense"),
            primary_result=vals.get("primary_result_above"),
            nominal_result=vals.get("nominal_result"),
            interest=vals.get("interest"),
            methodology="RTN_ABOVE_THE_LINE",
            amount_scale="millions",
            retrieved_at=retrieved_at,
            raw_record_id=raw_record_id,
            notes=(
                "RTN Governo Central. Receita/Despesa Total ≠ arrecadação RFB "
                "nem execução orçamentária (empenho/liquidação/pagamento)."
            ),
            extra={"series_map": {k: v["codigo_serie"] for k, v in SERIES_RTN.items()}},
        )
        if above.primary_result is None and above.primary_revenue is None:
            quarantined.append(
                quarantine_fiscal(
                    "MISSING_REQUIRED_FIELD",
                    source_id=SOURCE_ID,
                    raw_record_id=raw_record_id,
                    payload={"period": period, "methodology": "RTN_ABOVE_THE_LINE"},
                    notes="Sem resultado primário nem receita no período",
                    retrieved_at=retrieved_at,
                )
            )
        else:
            rows.append(above.to_dict())

        # Abaixo da linha (série oficial distinta — não misturar)
        if "primary_result_below" in vals:
            below = FiscalResultObservation(
                id=fiscal_result_id(
                    territory_id="terr_br",
                    reference_period=period,
                    methodology="RTN_BELOW_THE_LINE",
                    dataset_id=DATASET_ID,
                ),
                source_id=SOURCE_ID,
                dataset_id=DATASET_ID,
                territory_id="terr_br",
                reference_period=period,
                primary_result=vals.get("primary_result_below"),
                methodology="RTN_BELOW_THE_LINE",
                amount_scale="millions",
                retrieved_at=retrieved_at,
                raw_record_id=raw_record_id,
                notes="Resultado primário abaixo da linha (RTN 10.07.1). ≠ acima da linha.",
            )
            rows.append(below.to_dict())
    return rows, quarantined


def main() -> int:
    run = start_run(SOURCE_ID, DATASET_ID)
    retrieved_at = utc_now()
    data_inicio = os.getenv("ATLAS_RTN_DATA_INICIO", "01/2015").strip()
    data_fim = os.getenv("ATLAS_RTN_DATA_FIM", "").strip() or None

    registros = fetch_wanted_series(data_inicio=data_inicio, data_fim=data_fim)
    raw_meta = write_raw_record(
        source_id=SOURCE_ID,
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=CONNECTOR_VERSION,
        payload={"tema": "10", "count": len(registros), "registros": registros},
        filename="rtn_resultado_fiscal.json",
        source_url=DATASET_URLS["rtn_api"],
        dataset_id=DATASET_ID,
        content_type="application/json",
    )

    by_period = pivot_wanted_series(registros)
    rows, quarantined = build_observations(
        by_period, raw_record_id=raw_meta["raw_record_id"], retrieved_at=retrieved_at
    )

    outdir = run_bronze_dir(SOURCE_ID, run["ingestion_run_id"])
    day_out = LAKE / "bronze" / SOURCE_ID / retrieved_at[:10]
    day_out.mkdir(parents=True, exist_ok=True)

    write_jsonl(outdir / "fiscal_result_observation.jsonl", rows)
    write_jsonl(day_out / "fiscal_result_observation.jsonl", rows)
    if quarantined:
        write_jsonl(outdir / "quarantine.jsonl", quarantined)
        write_jsonl(day_out / "quarantine_fiscal_result.jsonl", quarantined)

    meta = {
        "source_id": SOURCE_ID,
        "dataset_id": DATASET_ID,
        "dataset_url": DATASET_URLS["rtn_ckan"],
        "api_url": DATASET_URLS["rtn_api"],
        "ingestion_run_id": run["ingestion_run_id"],
        "retrieved_at": retrieved_at,
        "n_registros_api": len(registros),
        "n_periods": len(by_period),
        "n_observations": len(rows),
        "n_quarantine": len(quarantined),
        "amount_scale": "millions",
        "raw_record_id": raw_meta["raw_record_id"],
        "series": SERIES_RTN,
    }
    write_json(outdir / "tesouro_fiscal_result_meta.json", meta)
    write_json(day_out / "tesouro_fiscal_result_meta.json", meta)
    append_event(
        "tesouro_fiscal_result",
        {"ok": True, "n": len(rows), "run": run["ingestion_run_id"]},
    )
    mark_ingested(
        SOURCE_ID,
        run_id=run["ingestion_run_id"],
        counts={"observations": len(rows), "quarantine": len(quarantined)},
        ok=len(rows) > 0,
        dataset_id=dataset_id_from_env("tesouro_fiscal_result"),
    )
    print(f"OK tesouro_fiscal_result: periods={len(by_period)} obs={len(rows)} q={len(quarantined)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
