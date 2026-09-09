#!/usr/bin/env python3
"""Silver DATASUS SINAN — ind_sinan_agravos (dengue slice)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402

INDICATOR_DEFS = [
    {
        "indicator_id": "ind_sinan_agravos",
        "name": "sinan_agravos_dengue",
        "display_name": "Casos notificados SINAN (dengue)",
        "description": "Contagem de notificações dengue (SINAN DENGBR). Slice inicial de agravos.",
        "category": "saude",
        "unit": "count",
        "higher_is_better": False,
        "source_id": "datasus_sinan",
        "dataset_id": "datasus.sinan_dengue",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "datasus_sinan"
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
    if not bronze or not (bronze / "sinan_extract.jsonl").exists():
        print("SKIPPED silver_datasus_sinan: bronze ausente", flush=True)
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
    for row in read_jsonl(bronze / "sinan_extract.jsonl"):
        tid = row.get("territory_id")
        year = int(row.get("ano") or 0)
        val = row.get("agravos")
        if not tid or not year or val is None:
            continue
        suf = tid.replace("uf_", "").replace("mun_", "")
        new_obs.append(
            {
                "observation_id": f"obs_sinan_deng_{suf}_{year}",
                "indicator_id": "ind_sinan_agravos",
                "territory_id": tid,
                "reference_year": year,
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "value": float(val),
                "unit": "count",
                "source_id": "datasus_sinan",
                "dataset_id": "datasus.sinan_dengue",
                "coverage_status": "ok",
                "confidence": "official",
                "retrieved_at": now,
                "geographic_level": row.get("nivel") or "STATE",
                "notes": row.get("agravo") or "dengue",
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
    write_json(sil / "meta_datasus_sinan.json", {"em": now, "observations": len(new_obs)})
    print(f"OK silver SINAN: +{len(new_obs)} obs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
