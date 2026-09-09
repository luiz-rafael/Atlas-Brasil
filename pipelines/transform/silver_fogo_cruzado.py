#!/usr/bin/env python3
"""
Silver Fogo Cruzado — ind_fogocruzado_tiros, ind_fogocruzado_vitimas.

Fonte complementar colaborativa (não Sinesp; não SIM homicídios).
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
        "indicator_id": "ind_fogocruzado_tiros",
        "name": "fogocruzado_tiros",
        "display_name": "Tiros (Fogo Cruzado)",
        "description": "Contagem anual de ocorrências de tiros (Fogo Cruzado / crossfire).",
        "category": "seguranca",
        "unit": "count",
        "higher_is_better": False,
        "source_id": "fogocruzado",
        "dataset_id": "fogocruzado.tiros_vitimas",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "notes": (
            "POLICE_OCCURRENCE_DATA complementary collaborative. "
            "Coverage mainly RJ/PE metro. NOT national Sinesp; keep separate from SIM homicide."
        ),
    },
    {
        "indicator_id": "ind_fogocruzado_vitimas",
        "name": "fogocruzado_vitimas",
        "display_name": "Vítimas em tiros (Fogo Cruzado)",
        "description": "Contagem anual de vítimas em ocorrências Fogo Cruzado.",
        "category": "seguranca",
        "unit": "count",
        "higher_is_better": False,
        "source_id": "fogocruzado",
        "dataset_id": "fogocruzado.tiros_vitimas",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "notes": "Complementary collaborative; not SIM mortality.",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "fogo_cruzado"
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
    if not bronze or not (bronze / "fogo_cruzado_extract.jsonl").exists():
        print("SKIPPED silver_fogo_cruzado: bronze ausente", flush=True)
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
    for row in read_jsonl(bronze / "fogo_cruzado_extract.jsonl"):
        tid = row.get("territory_id")
        year = int(row.get("ano") or 0)
        if not tid or not year:
            continue
        for field, ind_id, short in (
            ("tiros", "ind_fogocruzado_tiros", "fc_tiros"),
            ("vitimas", "ind_fogocruzado_vitimas", "fc_vit"),
        ):
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
                    "unit": "count",
                    "source_id": "fogocruzado",
                    "dataset_id": "fogocruzado.tiros_vitimas",
                    "coverage_status": "partial",
                    "confidence": "collaborative",
                    "retrieved_at": now,
                    "geographic_level": "MUNICIPALITY",
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
    write_json(sil / "meta_fogo_cruzado.json", {"em": now, "observations": len(new_obs)})
    print(f"OK silver Fogo Cruzado: +{len(new_obs)} obs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
