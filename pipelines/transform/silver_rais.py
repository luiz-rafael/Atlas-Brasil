#!/usr/bin/env python3
"""
Silver RAIS — estoque de vínculos formais por UF.

ind_rais_vinculos
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
        "indicator_id": "ind_rais_vinculos",
        "name": "rais_vinculos",
        "display_name": "RAIS — vínculos/empregos formais",
        "description": "Estoque de empregos formais (RAIS) por UF.",
        "category": "emprego",
        "unit": "count",
        "source_id": "rais",
        "dataset_id": "rais.estoque_uf",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
        "methodology_url": "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/estatisticas-trabalho/rais",
        "notes": "Estoque em 31/12 (agregados PDET). Não confundir com fluxo CAGED.",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "rais"
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
        print("bronze rais ausente", file=sys.stderr)
        return 1
    extract = bronze / "rais_estoque_extract.jsonl"
    if not extract.exists():
        print("extract rais ausente", file=sys.stderr)
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
        uf = (row.get("uf") or "").upper()
        year = int(row.get("ano") or 0)
        val = row.get("vinculos")
        if val is None:
            val = row.get("empregos")
        if not uf or not year or val is None:
            continue
        tid = f"uf_{uf}"
        new_obs.append(
            {
                "observation_id": f"obs_rais_vinc_{uf}_{year}",
                "indicator_id": "ind_rais_vinculos",
                "territory_id": tid,
                "reference_year": year,
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "value": float(val),
                "unit": "count",
                "source_id": "rais",
                "dataset_id": "rais.estoque_uf",
                "coverage_status": "ok",
                "confidence": "official",
                "retrieved_at": now,
                "geographic_level": "STATE",
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
        sil / "meta_rais.json",
        {"em": now, "observations": len(new_obs), "total_observations": len(observations)},
    )
    print(f"OK silver RAIS: +{len(new_obs)} obs · total={len(observations)}")
    return 0 if new_obs else 1


if __name__ == "__main__":
    raise SystemExit(main())
