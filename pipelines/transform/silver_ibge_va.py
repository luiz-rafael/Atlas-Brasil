#!/usr/bin/env python3
"""
Silver IBGE VA setorial — ind_va_agro, ind_va_industria, ind_va_servicos (+ shares).
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
        "indicator_id": "ind_va_agro",
        "name": "va_agropecuaria",
        "display_name": "Valor adicionado — agropecuária",
        "description": "VA bruto a preços correntes da agropecuária (SIDRA 5938 v/513). Mil Reais.",
        "category": "economia",
        "unit": "mil_reais",
        "source_id": "ibge",
        "dataset_id": "ibge.sidra_va_5938",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "methodology_url": "https://sidra.ibge.gov.br/tabela/5938",
    },
    {
        "indicator_id": "ind_va_industria",
        "name": "va_industria",
        "display_name": "Valor adicionado — indústria",
        "description": "VA bruto a preços correntes da indústria (SIDRA 5938 v/517). Mil Reais.",
        "category": "economia",
        "unit": "mil_reais",
        "source_id": "ibge",
        "dataset_id": "ibge.sidra_va_5938",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_va_servicos",
        "name": "va_servicos",
        "display_name": "Valor adicionado — serviços",
        "description": (
            "VA bruto a preços correntes dos serviços exclusive admin/defesa/"
            "educação/saúde públicas (SIDRA 5938 v/6575). Mil Reais."
        ),
        "category": "economia",
        "unit": "mil_reais",
        "source_id": "ibge",
        "dataset_id": "ibge.sidra_va_5938",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_va_agro_share",
        "name": "va_agro_share",
        "display_name": "Participação VA agropecuária (%)",
        "description": "Participação do VA agropecuária no VA total (SIDRA 5938 v/516).",
        "category": "economia",
        "unit": "percent",
        "source_id": "ibge",
        "dataset_id": "ibge.sidra_va_5938",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_va_industria_share",
        "name": "va_industria_share",
        "display_name": "Participação VA indústria (%)",
        "description": "Participação do VA indústria no VA total (SIDRA 5938 v/520).",
        "category": "economia",
        "unit": "percent",
        "source_id": "ibge",
        "dataset_id": "ibge.sidra_va_5938",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_va_servicos_share",
        "name": "va_servicos_share",
        "display_name": "Participação VA serviços (%)",
        "description": "Participação do VA serviços no VA total (SIDRA 5938 v/6574).",
        "category": "economia",
        "unit": "percent",
        "source_id": "ibge",
        "dataset_id": "ibge.sidra_va_5938",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}
FIELD_TO_IND = {
    "va_agro": ("ind_va_agro", "va_agro", "mil_reais"),
    "va_industria": ("ind_va_industria", "va_ind", "mil_reais"),
    "va_servicos": ("ind_va_servicos", "va_srv", "mil_reais"),
    "va_agro_share": ("ind_va_agro_share", "va_agro_sh", "percent"),
    "va_industria_share": ("ind_va_industria_share", "va_ind_sh", "percent"),
    "va_servicos_share": ("ind_va_servicos_share", "va_srv_sh", "percent"),
}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "ibge_va"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    return days[0] if days else None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    bronze = latest_bronze()
    if not bronze or not (bronze / "ibge_va_extract.jsonl").exists():
        print("SKIPPED silver_ibge_va: bronze ausente", flush=True)
        return 0

    sil = LAKE / "silver" / "indicadores"
    ind_path = sil / "indicators_latest.json"
    obs_path = sil / "observations_latest.jsonl"
    if not obs_path.exists():
        print("silver base ausente", file=sys.stderr)
        return 1

    indicators = json.loads(ind_path.read_text(encoding="utf-8")) if ind_path.exists() else []
    observations = read_jsonl(obs_path)
    observations = [o for o in observations if o.get("indicator_id") not in IDS]
    indicators = [i for i in indicators if i.get("indicator_id") not in IDS]
    indicators.extend(INDICATOR_DEFS)

    now = utc_now()
    new_obs: list[dict] = []
    for row in read_jsonl(bronze / "ibge_va_extract.jsonl"):
        tid = row.get("territory_id")
        year = int(row.get("ano") or 0)
        nivel = row.get("nivel") or ("STATE" if str(tid).startswith("uf_") else "MUNICIPALITY")
        if not tid or not year:
            continue
        for field, (ind_id, short, unit) in FIELD_TO_IND.items():
            val = row.get(field)
            if val is None:
                continue
            suf = tid.replace("uf_", "").replace("mun_", "")
            new_obs.append(
                {
                    "observation_id": f"obs_{short}_{suf}_{year}",
                    "indicator_id": ind_id,
                    "territory_id": tid,
                    "reference_year": year,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "value": float(val),
                    "unit": unit,
                    "source_id": "ibge",
                    "dataset_id": "ibge.sidra_va_5938",
                    "coverage_status": "ok",
                    "confidence": "official",
                    "retrieved_at": now,
                    "geographic_level": nivel,
                }
            )

    by_id = {o["observation_id"]: o for o in new_obs}
    new_obs = list(by_id.values())
    observations.extend(new_obs)

    stamp = day_stamp()
    write_json(sil / f"indicators_{stamp}.json", indicators)
    write_json(sil / "indicators_latest.json", indicators)
    write_jsonl(sil / f"observations_{stamp}.jsonl", observations)
    write_jsonl(sil / "observations_latest.jsonl", observations)
    write_json(sil / "meta_ibge_va.json", {"em": now, "observations": len(new_obs)})
    print(f"OK silver IBGE VA: +{len(new_obs)} obs")
    return 0 if new_obs else 1


if __name__ == "__main__":
    raise SystemExit(main())
