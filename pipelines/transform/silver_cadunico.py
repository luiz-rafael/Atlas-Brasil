#!/usr/bin/env python3
"""Silver CadÚnico — ind_cadunico_familias, ind_cadunico_baixa_renda."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402

INDICATOR_DEFS = [
    {
        "indicator_id": "ind_cadunico_familias",
        "name": "cadunico_familias",
        "display_name": "Famílias CadÚnico",
        "description": "Famílias cadastradas no Cadastro Único (MDS).",
        "category": "social",
        "unit": "count",
        "source_id": "cadunico",
        "dataset_id": "cadunico.familias",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_cadunico_baixa_renda",
        "name": "cadunico_baixa_renda",
        "display_name": "Famílias baixa renda (CadÚnico)",
        "description": "Famílias em faixa de baixa renda / pobreza no CadÚnico (quando disponível).",
        "category": "social",
        "unit": "count",
        "source_id": "cadunico",
        "dataset_id": "cadunico.familias",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}
FIELD_TO_IND = {
    "familias": ("ind_cadunico_familias", "cad_fam"),
    "baixa_renda": ("ind_cadunico_baixa_renda", "cad_br"),
}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "cadunico"
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
    if not bronze or not (bronze / "cadunico_extract.jsonl").exists():
        print("SKIPPED silver_cadunico: bronze ausente", flush=True)
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
    for row in read_jsonl(bronze / "cadunico_extract.jsonl"):
        tid = row.get("territory_id")
        year = int(row.get("ano") or 0)
        if not tid or not year:
            continue
        suf = tid.replace("mun_", "")
        for field, (ind_id, short) in FIELD_TO_IND.items():
            val = row.get(field)
            if val is None:
                continue
            new_obs.append(
                {
                    "observation_id": f"obs_{short}_{suf}_{year}",
                    "indicator_id": ind_id,
                    "territory_id": tid,
                    "reference_year": year,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "value": float(val),
                    "unit": "count",
                    "source_id": "cadunico",
                    "dataset_id": "cadunico.familias",
                    "coverage_status": "ok",
                    "confidence": "official",
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
    write_json(sil / "meta_cadunico.json", {"em": now, "observations": len(new_obs)})
    print(f"OK silver CadÚnico: +{len(new_obs)} obs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
