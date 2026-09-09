#!/usr/bin/env python3
"""
Tesouro — Estoque da Dívida Pública Federal (DPF).

Dataset:
  https://www.tesourotransparente.gov.br/ckan/dataset/estoque-da-divida-publica-federal
  CSV: estoquedpf.csv

Agrega por mês × Tipo de Divida → PUBLIC_DEBT_OBSERVATION (debt_indicator=DPF_STOCK).
≠ DBGG / DLSP (BCB).
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
from pipelines.fiscal.concepts import DATASET_URLS  # noqa: E402
from pipelines.fiscal.ids import public_debt_id  # noqa: E402
from pipelines.fiscal.models import PublicDebtObservation  # noqa: E402
from pipelines.fiscal.quarantine import quarantine_fiscal  # noqa: E402
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402

SOURCE_ID = "tesouro"
DATASET_ID = "tesouro.dpf_estoque"
CONNECTOR_VERSION = "5.2.0"
CKAN_PACKAGE = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show"
PACKAGE_ID = "estoque-da-divida-publica-federal"


def resolve_csv_url() -> str:
    r = http_get(f"{CKAN_PACKAGE}?id={PACKAGE_ID}", timeout=60.0)
    r.raise_for_status()
    resources = (r.json().get("result") or {}).get("resources") or []
    for res in resources:
        if str(res.get("format") or "").upper() == "CSV" and res.get("url"):
            return str(res["url"])
    raise RuntimeError("CSV de estoque DPF não encontrado no CKAN")


def parse_br_float(s: str) -> float | None:
    t = (s or "").strip().replace(".", "").replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_mes_estoque(s: str) -> str | None:
    # MM/YYYY
    parts = (s or "").strip().split("/")
    if len(parts) != 2:
        return None
    try:
        m, y = int(parts[0]), int(parts[1])
        if not (1 <= m <= 12):
            return None
        return f"{y:04d}-{m:02d}"
    except ValueError:
        return None


def aggregate_csv(text: str) -> tuple[list[dict], list[dict]]:
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    # normaliza chaves
    if not reader.fieldnames:
        return [], [
            quarantine_fiscal(
                "SCHEMA_CHANGED",
                source_id=SOURCE_ID,
                payload={"hint": "sem header"},
            )
        ]

    sums: dict[tuple[str, str], float] = defaultdict(float)
    n_rows = 0
    quarantined: list[dict] = []
    for row in reader:
        # aceita variações de encoding no header
        period = None
        debt_type = None
        valor = None
        for k, v in row.items():
            kn = (k or "").lower()
            if "mes do estoque" in kn or kn == "mes do estoque":
                period = parse_mes_estoque(v or "")
            elif "tipo de divida" in kn or "tipo de dívida" in kn:
                debt_type = (v or "").strip() or "UNKNOWN"
            elif "valor do estoque" in kn:
                valor = parse_br_float(v or "")
        if period is None:
            quarantined.append(
                quarantine_fiscal(
                    "INVALID_PERIOD",
                    source_id=SOURCE_ID,
                    payload=row,
                )
            )
            continue
        if valor is None:
            continue  # ausente ≠ zero
        sums[(period, debt_type or "UNKNOWN")] += valor
        n_rows += 1

    retrieved_at = utc_now()
    rows: list[dict] = []
    for (period, debt_type), stock in sorted(sums.items()):
        obs = PublicDebtObservation(
            id=public_debt_id(
                reference_period=period,
                debt_indicator="DPF_STOCK",
                debt_type=debt_type,
                dataset_id=DATASET_ID,
            ),
            source_id=SOURCE_ID,
            dataset_id=DATASET_ID,
            reference_period=period,
            debt_indicator="DPF_STOCK",
            debt_type=debt_type,
            stock=stock,
            amount_scale="units",
            methodology="DPF_ESTOQUE_CKAN",
            retrieved_at=retrieved_at,
            notes="Estoque DPF agregado por mês e tipo. ≠ DBGG/DLSP.",
            extra={"source_rows_contrib": n_rows},
        )
        rows.append(obs.to_dict())

    # total DPF por mês
    by_period: dict[str, float] = defaultdict(float)
    for (period, _), stock in sums.items():
        by_period[period] += stock
    for period, stock in sorted(by_period.items()):
        obs = PublicDebtObservation(
            id=public_debt_id(
                reference_period=period,
                debt_indicator="DPF_STOCK_TOTAL",
                debt_type="TOTAL",
                dataset_id=DATASET_ID,
            ),
            source_id=SOURCE_ID,
            dataset_id=DATASET_ID,
            reference_period=period,
            debt_indicator="DPF_STOCK_TOTAL",
            debt_type="TOTAL",
            stock=stock,
            amount_scale="units",
            methodology="DPF_ESTOQUE_CKAN",
            retrieved_at=retrieved_at,
            notes="Soma dos tipos de dívida no mês (DPF).",
        )
        rows.append(obs.to_dict())
    return rows, quarantined[:500]  # cap quarantine noise


def main() -> int:
    run = start_run(SOURCE_ID, DATASET_ID)
    csv_url = resolve_csv_url()
    r = http_get(csv_url, timeout=180.0)
    r.raise_for_status()
    raw_bytes = r.content
    # latin-1 comum em exports STN
    text = raw_bytes.decode("latin-1")

    raw_meta = write_raw_record(
        source_id=SOURCE_ID,
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=CONNECTOR_VERSION,
        payload=raw_bytes,
        filename="estoquedpf.csv",
        source_url=csv_url,
        dataset_id=DATASET_ID,
        content_type="text/csv",
    )

    rows, quarantined = aggregate_csv(text)
    for q in quarantined:
        q["raw_record_id"] = raw_meta["raw_record_id"]

    outdir = run_bronze_dir(SOURCE_ID, run["ingestion_run_id"])
    day_out = LAKE / "bronze" / SOURCE_ID / utc_now()[:10]
    day_out.mkdir(parents=True, exist_ok=True)
    write_jsonl(outdir / "public_debt_observation.jsonl", rows)
    write_jsonl(day_out / "public_debt_observation.jsonl", rows)
    if quarantined:
        write_jsonl(outdir / "quarantine_debt.jsonl", quarantined)

    meta = {
        "source_id": SOURCE_ID,
        "dataset_id": DATASET_ID,
        "dataset_url": DATASET_URLS["dpf_estoque"],
        "csv_url": csv_url,
        "ingestion_run_id": run["ingestion_run_id"],
        "n_observations": len(rows),
        "n_quarantine": len(quarantined),
        "raw_record_id": raw_meta["raw_record_id"],
    }
    write_json(outdir / "tesouro_public_debt_meta.json", meta)
    write_json(day_out / "tesouro_public_debt_meta.json", meta)
    append_event("tesouro_public_debt", {"ok": True, "n": len(rows)})
    mark_ingested(
        SOURCE_ID,
        run_id=run["ingestion_run_id"],
        counts={"observations": len(rows)},
        ok=len(rows) > 0,
        dataset_id=dataset_id_from_env("tesouro_public_debt"),
    )
    print(f"OK tesouro_public_debt: obs={len(rows)} q={len(quarantined)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
