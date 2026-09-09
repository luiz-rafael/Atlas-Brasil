#!/usr/bin/env python3
"""
Silver IDHM — índice e dimensões (educação, longevidade, renda).

ind_idhm, ind_idhm_educacao, ind_idhm_longevidade, ind_idhm_renda
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
        "indicator_id": "ind_idhm",
        "name": "idhm",
        "display_name": "IDHM",
        "description": "Índice de Desenvolvimento Humano Municipal (Atlas Brasil / Ipeadata ADH).",
        "category": "desenvolvimento",
        "unit": "index_0_1",
        "higher_is_better": True,
        "source_id": "idhm_atlas",
        "dataset_id": "idhm.atlas",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "census",
        "methodology_url": "https://www.atlasbrasil.org.br/",
        "notes": "Anos censo 1991/2000/2010 (e radar se disponível).",
    },
    {
        "indicator_id": "ind_idhm_educacao",
        "name": "idhm_educacao",
        "display_name": "IDHM Educação",
        "description": "Dimensão educação do IDHM.",
        "category": "desenvolvimento",
        "unit": "index_0_1",
        "higher_is_better": True,
        "source_id": "idhm_atlas",
        "dataset_id": "idhm.atlas",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "census",
    },
    {
        "indicator_id": "ind_idhm_longevidade",
        "name": "idhm_longevidade",
        "display_name": "IDHM Longevidade",
        "description": "Dimensão longevidade do IDHM.",
        "category": "desenvolvimento",
        "unit": "index_0_1",
        "higher_is_better": True,
        "source_id": "idhm_atlas",
        "dataset_id": "idhm.atlas",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "census",
    },
    {
        "indicator_id": "ind_idhm_renda",
        "name": "idhm_renda",
        "display_name": "IDHM Renda",
        "description": "Dimensão renda do IDHM.",
        "category": "desenvolvimento",
        "unit": "index_0_1",
        "higher_is_better": True,
        "source_id": "idhm_atlas",
        "dataset_id": "idhm.atlas",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "census",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}
FIELD_TO_IND = {
    "idhm": ("ind_idhm", "idhm"),
    "idhm_educacao": ("ind_idhm_educacao", "idhm_e"),
    "idhm_longevidade": ("ind_idhm_longevidade", "idhm_l"),
    "idhm_renda": ("ind_idhm_renda", "idhm_r"),
}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "idhm_atlas"
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
    if not bronze:
        print("bronze idhm ausente", file=sys.stderr)
        return 1
    extract = bronze / "idhm_extract.jsonl"
    if not extract.exists():
        print("extract idhm ausente", file=sys.stderr)
        return 1

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
    for row in read_jsonl(extract):
        year = int(row.get("ano") or 0)
        tid = row.get("territory_id")
        nivel = row.get("nivel") or (
            "STATE" if tid and str(tid).startswith("uf_") else "MUNICIPALITY"
        )
        if not tid or not year:
            continue
        for field, (ind_id, short) in FIELD_TO_IND.items():
            val = row.get(field)
            if val is None:
                continue
            new_obs.append(
                {
                    "observation_id": f"obs_{short}_{tid}_{year}",
                    "indicator_id": ind_id,
                    "territory_id": tid,
                    "reference_year": year,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "value": float(val),
                    "unit": "index_0_1",
                    "source_id": "idhm_atlas",
                    "dataset_id": "idhm.atlas",
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
    write_json(
        sil / "meta_idhm.json",
        {"em": now, "observations": len(new_obs), "total_observations": len(observations)},
    )
    print(f"OK silver IDHM: +{len(new_obs)} obs · total={len(observations)}")
    return 0 if new_obs else 1


if __name__ == "__main__":
    raise SystemExit(main())
