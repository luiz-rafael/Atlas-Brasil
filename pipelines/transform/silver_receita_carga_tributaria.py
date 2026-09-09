#!/usr/bin/env python3
"""
Silver carga tributária → ind_carga_tributaria_pib (separado de ind_arrecadacao_federal).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402

INDICATOR_DEFS = [
    {
        "indicator_id": "ind_carga_tributaria_pib",
        "name": "carga_tributaria_pib",
        "display_name": "Carga tributária bruta (% PIB)",
        "description": (
            "Carga tributária bruta como proporção do PIB (estudo CTB / RFB). "
            "Separado de ind_arrecadacao_federal (arrecadação nominal RF)."
        ),
        "category": "fiscal",
        "unit": "ratio",
        "higher_is_better": None,
        "source_id": "receita_carga_tributaria",
        "dataset_id": "rfb.carga_tributaria",
        "minimum_geographic_level": "BRASIL",
        "frequency": "annual",
        "notes": (
            "Valor tipicamente 0–1 (ex.: 0.32 = 32% do PIB). "
            "Metodologia CTB 2024: verificar notas FGTS/Sistema S."
        ),
    },
]
IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "receita_carga_tributaria"
    if not base.exists():
        return None
    for d in sorted([p for p in base.iterdir() if p.is_dir()], reverse=True):
        if (d / "carga_tributaria_extract.jsonl").exists():
            return d
    return None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("SKIPPED silver_receita_carga_tributaria: bronze ausente", flush=True)
        return 0

    rows = read_jsonl(bronze / "carga_tributaria_extract.jsonl")
    now = utc_now()

    sil_fiscal = LAKE / "silver" / "fiscal"
    sil_fiscal.mkdir(parents=True, exist_ok=True)
    obs_fiscal = []
    for r in rows:
        obs_fiscal.append({**r, "retrieved_at": now, "semantic": "TAX_BURDEN_OBSERVATION"})
    write_jsonl(sil_fiscal / "tax_burden_latest.jsonl", obs_fiscal)
    write_jsonl(sil_fiscal / f"tax_burden_{day_stamp()}.jsonl", obs_fiscal)
    write_json(
        sil_fiscal / "tax_burden_meta.json",
        {
            "rows": len(obs_fiscal),
            "methodology": (rows[0].get("methodology") if rows else None),
            "methodology_notes": (rows[0].get("methodology_notes") if rows else None),
            "updated_at": now,
            "nota": "Separado de ind_arrecadacao_federal",
        },
    )

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
    for r in rows:
        year = int(r.get("year") or 0)
        ratio = r.get("tax_to_gdp_ratio")
        if not year or ratio is None:
            continue
        new_obs.append(
            {
                "observation_id": f"obs_carga_pib_br_{year}",
                "indicator_id": "ind_carga_tributaria_pib",
                "territory_id": "terr_br",
                "territory_type": "BRASIL",
                "year": year,
                "period_start": f"{year}-01-01",
                "value": float(ratio),
                "unit": "ratio",
                "source_id": "receita_carga_tributaria",
                "dataset_id": "rfb.carga_tributaria",
                "retrieved_at": now,
                "meta": {
                    "amount_brl": r.get("amount"),
                    "pib_bilhoes": r.get("pib_bilhoes"),
                    "arrecadacao_bruta_bilhoes": r.get("arrecadacao_bruta_bilhoes"),
                    "methodology": r.get("methodology"),
                    "methodology_notes": r.get("methodology_notes"),
                    "nota": r.get("nota"),
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
        f"OK silver_receita_carga_tributaria obs={len(new_obs)} -> {sil}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
