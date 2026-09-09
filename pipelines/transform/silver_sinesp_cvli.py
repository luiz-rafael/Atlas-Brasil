#!/usr/bin/env python3
"""
Silver CVLI / Sinesp-IPEA — ind_cvli_per_100k.

SECURITY_DATA_COVERAGE: complementary police/IPEA rates; not Fogo Cruzado; not SIM.
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
        "indicator_id": "ind_cvli_per_100k",
        "name": "cvli_per_100k",
        "display_name": "CVLI / homicídios por 100 mil",
        "description": (
            "Taxa de crimes violentos letais intencionais ou homicídios por 100 mil "
            "(Sinesp quando disponível; fallback IPEA Atlas / arquivo manual)."
        ),
        "category": "seguranca",
        "unit": "per_100000",
        "higher_is_better": False,
        "source_id": "sinesp_cvli",
        "dataset_id": "sinesp.cvli_per_100k",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
        "notes": (
            "SECURITY_DATA_COVERAGE: complementary consolidated rates. "
            "Keep separate from Fogo Cruzado and SIM CID homicide mortality."
        ),
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "sinesp_cvli"
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
    if not bronze or not (bronze / "sinesp_cvli_extract.jsonl").exists():
        print("SKIPPED silver_sinesp_cvli: bronze ausente", flush=True)
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
    for row in read_jsonl(bronze / "sinesp_cvli_extract.jsonl"):
        tid = row.get("territory_id")
        year = int(row.get("ano") or 0)
        val = row.get("cvli_per_100k")
        if not tid or not year or val is None:
            continue
        suf = tid.replace("uf_", "").replace("mun_", "")
        new_obs.append(
            {
                "observation_id": f"obs_cvli100k_{suf}_{year}",
                "indicator_id": "ind_cvli_per_100k",
                "territory_id": tid,
                "reference_year": year,
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "value": float(val),
                "unit": "per_100000",
                "source_id": "sinesp_cvli",
                "dataset_id": "sinesp.cvli_per_100k",
                "coverage_status": "partial",
                "confidence": "official_derived",
                "retrieved_at": now,
                "geographic_level": row.get("nivel") or "STATE",
                "fonte_serie": row.get("serie") or row.get("fonte"),
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
    write_json(sil / "meta_sinesp_cvli.json", {"em": now, "observations": len(new_obs)})
    print(f"OK silver CVLI: +{len(new_obs)} obs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
