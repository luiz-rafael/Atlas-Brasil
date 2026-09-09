#!/usr/bin/env python3
"""
Tesouro — custo / juros da dívida.

Fontes oficiais usadas:
  1) RTN série 10.08.1 Juros Nominais → PUBLIC_DEBT_OBSERVATION.interest
     (componente do resultado nominal; ≠ custo médio % a.a. do RMD)
  2) Execução orçamentária DPF por ND (CSV CKAN) — agrega «Juros e Encargos»
     → interest sob debt_indicator=DPF_INTEREST_PAID

Dataset ND:
  https://www.tesourotransparente.gov.br/ckan/dataset/
  execucao-orcamentaria-e-financeira-da-divida-publica-federal-por-nd

Custo médio / prazo médio da DPF (RMD) não estão neste CSV; documentados como cobertura parcial.
"""

from __future__ import annotations

import csv
import io
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    LAKE,
    append_event,
    http_get,
    run_bronze_dir,
    utc_now,
    write_json,
    write_jsonl,
    write_raw_record,
)
from pipelines.fiscal.concepts import DATASET_URLS, SERIES_RTN  # noqa: E402
from pipelines.fiscal.ids import public_debt_id  # noqa: E402
from pipelines.fiscal.models import PublicDebtObservation  # noqa: E402
from pipelines.fiscal.rtn_client import fetch_resultado_fiscal, parse_period  # noqa: E402
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402

SOURCE_ID = "tesouro"
DATASET_ID = "tesouro.debt_cost"
CONNECTOR_VERSION = "5.2.0"
CKAN_PACKAGE = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show"
PACKAGE_ID = "execucao-orcamentaria-e-financeira-da-divida-publica-federal-por-nd"
MONTHS = [
    "janeiro",
    "fevereiro",
    "março",
    "marco",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]
MONTH_IDX = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def resolve_nd_csv_url() -> str:
    r = http_get(f"{CKAN_PACKAGE}?id={PACKAGE_ID}", timeout=60.0)
    r.raise_for_status()
    for res in (r.json().get("result") or {}).get("resources") or []:
        if str(res.get("format") or "").upper() == "CSV" and res.get("url"):
            return str(res["url"])
    raise RuntimeError("CSV execução DPF por ND não encontrado")


def parse_br_float(s: str) -> float | None:
    t = (s or "").strip().replace(".", "").replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def interest_from_rtn(retrieved_at: str, raw_id: str) -> list[dict]:
    code = SERIES_RTN["juros_nominais"]["codigo_serie"]
    regs = fetch_resultado_fiscal(tema="10", data_inicio="01/2015", codigo_da_serie=code)
    rows: list[dict] = []
    for reg in regs:
        if str(reg.get("codigoSerie")) != code:
            continue
        _, _, period = parse_period(str(reg["data"]))
        try:
            val = float(reg["valor"])
        except (TypeError, ValueError, KeyError):
            continue
        obs = PublicDebtObservation(
            id=public_debt_id(
                reference_period=period,
                debt_indicator="RTN_JUROS_NOMINAIS",
                debt_type="GOVERNO_CENTRAL",
                dataset_id=DATASET_ID,
            ),
            source_id=SOURCE_ID,
            dataset_id=DATASET_ID,
            reference_period=period,
            debt_indicator="RTN_JUROS_NOMINAIS",
            debt_type="GOVERNO_CENTRAL",
            interest=val,
            amount_scale="millions",
            methodology="RTN_JUROS_NOMINAIS",
            retrieved_at=retrieved_at,
            raw_record_id=raw_id,
            notes=(
                "Juros nominais RTN (R$ mi). Não é custo médio % a.a. da DPF (RMD)."
            ),
        )
        rows.append(obs.to_dict())
    return rows


def interest_from_nd_csv(text: str, retrieved_at: str, raw_id: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    sums: dict[str, float] = defaultdict(float)
    for row in reader:
        mov = ""
        year = None
        for k, v in row.items():
            kn = (k or "").lower()
            if "moviment" in kn:
                mov = (v or "").strip().lower()
            elif kn.startswith("exerc"):
                try:
                    year = int(str(v).strip()[:4])
                except ValueError:
                    year = None
        if "juros" not in mov:
            continue
        if year is None:
            continue
        for col, v in row.items():
            cn = (col or "").strip().lower()
            if cn not in MONTH_IDX:
                continue
            val = parse_br_float(v or "")
            if val is None:
                continue
            period = f"{year:04d}-{MONTH_IDX[cn]:02d}"
            sums[period] += val

    rows: list[dict] = []
    for period, interest in sorted(sums.items()):
        obs = PublicDebtObservation(
            id=public_debt_id(
                reference_period=period,
                debt_indicator="DPF_INTEREST_PAID",
                debt_type="DPF",
                dataset_id=DATASET_ID,
            ),
            source_id=SOURCE_ID,
            dataset_id=DATASET_ID,
            reference_period=period,
            debt_indicator="DPF_INTEREST_PAID",
            debt_type="DPF",
            interest=interest,
            amount_scale="units",
            methodology="DPF_EXECUCAO_ND_JUROS",
            retrieved_at=retrieved_at,
            raw_record_id=raw_id,
            notes="Soma mensal de movimentação «Juros e Encargos» na execução DPF por ND.",
        )
        rows.append(obs.to_dict())
    return rows


def main() -> int:
    run = start_run(SOURCE_ID, DATASET_ID)
    retrieved_at = utc_now()
    outdir = run_bronze_dir(SOURCE_ID, run["ingestion_run_id"])
    day_out = LAKE / "bronze" / SOURCE_ID / retrieved_at[:10]
    day_out.mkdir(parents=True, exist_ok=True)

    # 1) RTN juros
    rtn_regs = fetch_resultado_fiscal(
        tema="10",
        data_inicio="01/2015",
        codigo_da_serie=SERIES_RTN["juros_nominais"]["codigo_serie"],
    )
    rtn_raw = write_raw_record(
        source_id=SOURCE_ID,
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=CONNECTOR_VERSION,
        payload=rtn_regs,
        filename="rtn_juros_nominais.json",
        source_url=DATASET_URLS["rtn_api"],
        dataset_id=DATASET_ID,
    )
    rows = interest_from_rtn(retrieved_at, rtn_raw["raw_record_id"])

    # 2) Execução ND
    csv_url = resolve_nd_csv_url()
    resp = http_get(csv_url, timeout=120.0)
    resp.raise_for_status()
    nd_raw = write_raw_record(
        source_id=SOURCE_ID,
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=CONNECTOR_VERSION,
        payload=resp.content,
        filename="dpf_execucao_nd.csv",
        source_url=csv_url,
        dataset_id=DATASET_ID,
        content_type="text/csv",
    )
    text = resp.content.decode("latin-1")
    rows.extend(interest_from_nd_csv(text, retrieved_at, nd_raw["raw_record_id"]))

    write_jsonl(outdir / "public_debt_cost.jsonl", rows)
    write_jsonl(day_out / "public_debt_cost.jsonl", rows)
    meta = {
        "source_id": SOURCE_ID,
        "dataset_id": DATASET_ID,
        "coverage": {
            "rtn_juros_nominais": True,
            "dpf_interest_paid_nd": True,
            "dpf_average_cost_rmd": False,
            "dpf_average_maturity_rmd": False,
        },
        "dataset_urls": {
            "rtn": DATASET_URLS["rtn_ckan"],
            "execucao_nd": DATASET_URLS["dpf_execucao_nd"],
        },
        "n_observations": len(rows),
        "ingestion_run_id": run["ingestion_run_id"],
        "note": "Custo médio % a.a. e prazo médio ficam no RMD — cobertura parcial.",
    }
    write_json(outdir / "tesouro_debt_cost_meta.json", meta)
    write_json(day_out / "tesouro_debt_cost_meta.json", meta)
    append_event("tesouro_debt_cost", {"ok": True, "n": len(rows)})
    mark_ingested(
        SOURCE_ID,
        run_id=run["ingestion_run_id"],
        counts={"observations": len(rows)},
        ok=len(rows) > 0,
        dataset_id=dataset_id_from_env("tesouro_debt_cost"),
    )
    print(f"OK tesouro_debt_cost: obs={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
