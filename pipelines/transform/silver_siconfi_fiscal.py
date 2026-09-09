#!/usr/bin/env python3
"""
Silver fiscal — SICONFI DCA/RGF → modelos canônicos Contas do Brasil.

Lê bronze siconfi (dca_extract + rgf_rcl) e grava:
  data/lake/silver/fiscal/public_budget_execution.jsonl
  data/lake/silver/fiscal/personnel_expenditure.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.fiscal.ids import (  # noqa: E402
    budget_execution_id,
    period_year,
    personnel_id,
)
from pipelines.fiscal.models import PersonnelExpenditure, PublicBudgetExecution  # noqa: E402


def latest_bronze_siconfi() -> Path | None:
    base = LAKE / "bronze" / "siconfi"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    for d in days:
        if (d / "dca_extract.jsonl").exists():
            return d
    return None


def territory_id(nivel: str, cod_ibge: int, uf: str | None) -> str:
    if nivel == "STATE":
        return f"uf_{(uf or '').upper()}" if uf else f"uf_{cod_ibge}"
    return f"mun_{cod_ibge}"


def main() -> int:
    bronze = latest_bronze_siconfi()
    if not bronze:
        print("bronze SICONFI ausente", file=sys.stderr)
        return 1

    retrieved_at = utc_now()
    budget_rows: list[dict] = []
    personnel_rows: list[dict] = []

    dca_path = bronze / "dca_extract.jsonl"
    for line in dca_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        metrics = row.get("metrics") or {}
        if "exercicio" not in row or "cod_ibge" not in row:
            continue
        year = int(row["exercicio"])
        nivel = row.get("nivel") or "STATE"
        gov = "STATE" if nivel == "STATE" else "MUNICIPALITY"
        tid = territory_id(nivel, int(row["cod_ibge"]), row.get("uf"))
        period = period_year(year)
        dataset_id = "siconfi.dca"

        pbe = PublicBudgetExecution(
            id=budget_execution_id(
                territory_id=tid,
                government_level=gov,
                reference_period=period,
                dataset_id=dataset_id,
            ),
            source_id="siconfi",
            dataset_id=dataset_id,
            territory_id=tid,
            government_level=gov,
            reference_year=year,
            reference_month=None,
            reference_period=period,
            revenue_realized=metrics.get("receita_bruta"),
            expense_committed=metrics.get("despesa_total"),
            expense_liquidated=metrics.get("despesa_liquidada"),
            expense_paid=metrics.get("despesa_paga"),
            amount_scale="units",
            methodology="SICONFI_DCA",
            retrieved_at=row.get("retrieved_at") or retrieved_at,
            notes=(
                "DCA: receita=Receitas Brutas Realizadas; "
                "despesas=estágios Empenhadas/Liquidadas/Pagas quando disponíveis. "
                "≠ RTN Governo Central."
            ),
            extra={
                "transferencias_correntes": metrics.get("transferencias_correntes"),
                "despesa_investimentos": metrics.get("despesa_investimentos"),
                "despesa_saude": metrics.get("despesa_saude"),
                "despesa_educacao": metrics.get("despesa_educacao"),
                "cod_ibge": row.get("cod_ibge"),
                "uf": row.get("uf"),
            },
        )
        budget_rows.append(pbe.to_dict())

        if metrics.get("despesa_pessoal") is not None:
            pex = PersonnelExpenditure(
                id=personnel_id(
                    territory_id=tid,
                    government_level=gov,
                    reference_period=period,
                    agency_id=None,
                    dataset_id=dataset_id,
                ),
                territory_id=tid,
                government_level=gov,
                reference_period=period,
                source_id="siconfi",
                dataset_id=dataset_id,
                gross_amount=metrics["despesa_pessoal"],
                retrieved_at=row.get("retrieved_at") or retrieved_at,
                notes="Agregado DCA (Pessoal e Encargos). Não cria indivíduos.",
            )
            personnel_rows.append(pex.to_dict())

    out = LAKE / "silver" / "fiscal"
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "public_budget_execution_siconfi.jsonl", budget_rows)
    write_jsonl(out / "personnel_expenditure_siconfi.jsonl", personnel_rows)
    write_json(
        out / "meta_siconfi_fiscal.json",
        {
            "em": retrieved_at,
            "day": day_stamp(),
            "bronze": str(bronze),
            "n_budget": len(budget_rows),
            "n_personnel": len(personnel_rows),
        },
    )
    print(f"OK silver_siconfi_fiscal: budget={len(budget_rows)} personnel={len(personnel_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
