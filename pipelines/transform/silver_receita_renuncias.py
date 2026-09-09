#!/usr/bin/env python3
"""
Silver renúncias fiscais → tax_expenditure_latest.jsonl + ind_renuncia_fiscal.

Renúncia ≠ pagamento. Beneficiário/company_id só com CNPJ 14 dígitos.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402

INDICATOR_DEFS = [
    {
        "indicator_id": "ind_renuncia_fiscal",
        "name": "renuncia_fiscal",
        "display_name": "Renúncia fiscal federal (agregada)",
        "description": (
            "Soma anual de valores de benefícios/renúncias fiscais federais publicados pela RFB. "
            "Renúncia ≠ pagamento público. Agregado BRASIL."
        ),
        "category": "fiscal",
        "unit": "BRL",
        "higher_is_better": None,
        "source_id": "receita_renuncias",
        "dataset_id": "rfb.renuncias",
        "minimum_geographic_level": "BRASIL",
        "frequency": "annual",
        "notes": "Contas do Brasil — quanto o Estado deixou de arrecadar (estimativa/observado da fonte).",
    },
]
IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "receita_renuncias"
    if not base.exists():
        return None
    for d in sorted([p for p in base.iterdir() if p.is_dir()], reverse=True):
        if (d / "tax_expenditure_extract.jsonl").exists():
            return d
    return None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("SKIPPED silver_receita_renuncias: bronze ausente", flush=True)
        return 0

    rows = read_jsonl(bronze / "tax_expenditure_extract.jsonl")
    now = utc_now()

    silver_rows: list[dict] = []
    by_year: dict[int, float] = defaultdict(float)
    beneficiaries = 0
    for r in rows:
        year = int(r.get("year") or 0)
        val = r.get("valor")
        if not year or val is None:
            continue
        cnpj = r.get("cnpj")
        company_id = r.get("company_id") if cnpj else None
        if company_id:
            beneficiaries += 1
        silver_rows.append(
            {
                **r,
                "company_id": company_id,
                "cnpj": cnpj,
                "retrieved_at": now,
                "semantic": "TAX_EXPENDITURE",
                "nota": "Renúncia ≠ pagamento público",
            }
        )
        by_year[year] += float(val)

    # lake fiscal
    sil_fiscal = LAKE / "silver" / "fiscal"
    sil_fiscal.mkdir(parents=True, exist_ok=True)
    write_jsonl(sil_fiscal / "tax_expenditure_latest.jsonl", silver_rows)
    write_jsonl(sil_fiscal / f"tax_expenditure_{day_stamp()}.jsonl", silver_rows)
    write_json(
        sil_fiscal / "tax_expenditure_meta.json",
        {
            "rows": len(silver_rows),
            "beneficiaries_with_cnpj14": beneficiaries,
            "years": sorted(by_year),
            "nota": "Renúncia ≠ pagamento. Agregados setoriais sem CNPJ não geram COMPANY.",
            "updated_at": now,
        },
    )

    # indicators
    sil = LAKE / "silver" / "indicadores"
    ind_path = sil / "indicators_latest.json"
    obs_path = sil / "observations_latest.jsonl"
    if not obs_path.exists():
        print("silver base indicadores ausente — rode silver_indicadores.py antes", file=sys.stderr)
        return 1

    indicators = json.loads(ind_path.read_text(encoding="utf-8")) if ind_path.exists() else []
    observations = read_jsonl(obs_path)
    observations = [o for o in observations if o.get("indicator_id") not in IDS]
    indicators = [i for i in indicators if i.get("indicator_id") not in IDS]
    indicators.extend(INDICATOR_DEFS)

    new_obs: list[dict] = []
    for year, total in sorted(by_year.items()):
        new_obs.append(
            {
                "observation_id": f"obs_renuncia_br_{year}",
                "indicator_id": "ind_renuncia_fiscal",
                "territory_id": "terr_br",
                "territory_type": "BRASIL",
                "reference_year": year,
                "year": year,
                "period_start": f"{year}-01-01",
                "value": float(total),
                "unit": "BRL",
                "source_id": "receita_renuncias",
                "dataset_id": "rfb.renuncias",
                "retrieved_at": now,
                "meta": {
                    "nota": "Soma de linhas do extrato RFB; renúncia ≠ pagamento",
                    "value_type_default": "OBSERVED",
                },
            }
        )
    observations.extend(new_obs)
    sil.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    write_json(ind_path, indicators)
    write_jsonl(obs_path, observations)
    write_jsonl(sil / f"observations_{stamp}.jsonl", observations)
    write_json(sil / f"indicators_{stamp}.json", indicators)

    print(
        f"OK silver_receita_renuncias rows={len(silver_rows)} "
        f"beneficiaries_cnpj14={beneficiaries} obs={len(new_obs)} -> {sil_fiscal}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
