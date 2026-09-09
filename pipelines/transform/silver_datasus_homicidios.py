#!/usr/bin/env python3
"""
Silver DATASUS — homicídios e causas externas.

ind_homicidios, ind_homicidios_per_100k (÷ ind_pop_estimada), ind_mortes_causas_externas
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
        "indicator_id": "ind_homicidios",
        "name": "homicidios",
        "display_name": "Homicídios (agressões)",
        "description": "Óbitos por agressão (SIM CAUSABAS CID-10 X85–Y09), residência.",
        "category": "seguranca",
        "unit": "count",
        "higher_is_better": False,
        "source_id": "datasus",
        "dataset_id": "datasus.sim_homicidios",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "methodology_url": "https://datasus.saude.gov.br/informacoes-de-saude-tabnet/",
        "notes": "Contagem SIM. Não é taxa.",
    },
    {
        "indicator_id": "ind_homicidios_per_100k",
        "name": "homicidios_per_100k",
        "display_name": "Homicídios por 100 mil hab.",
        "description": "Homicídios / população estimada × 100000.",
        "category": "seguranca",
        "unit": "per_100000",
        "higher_is_better": False,
        "source_id": "datasus",
        "dataset_id": "datasus.sim_homicidios_derived",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "notes": "Derivado SIM ÷ IBGE população.",
    },
    {
        "indicator_id": "ind_mortes_causas_externas",
        "name": "mortes_causas_externas",
        "display_name": "Mortes por causas externas",
        "description": "Óbitos por causas externas (SIM CAUSABAS V01–Y98).",
        "category": "saude",
        "unit": "count",
        "higher_is_better": False,
        "source_id": "datasus",
        "dataset_id": "datasus.sim_homicidios",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "datasus"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    for d in days:
        if (d / "sim_homicidios_extract.jsonl").exists():
            return d
    return days[0] if days else None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("bronze datasus ausente", file=sys.stderr)
        return 1
    extract = bronze / "sim_homicidios_extract.jsonl"
    if not extract.exists():
        print("extract homicídios ausente", file=sys.stderr)
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

    pop: dict[tuple[str, int], float] = {}
    for o in observations:
        if o.get("indicator_id") != "ind_pop_estimada":
            continue
        tid, y = o.get("territory_id"), o.get("reference_year")
        if tid and y:
            pop[(tid, int(y))] = float(o["value"])

    now = utc_now()
    new_obs: list[dict] = []
    for row in read_jsonl(extract):
        if row.get("missing"):
            continue
        year = int(row.get("ano") or 0)
        if not year:
            continue
        nivel = row.get("nivel") or "STATE"
        tid = row.get("territory_id")
        if not tid:
            uf = (row.get("uf") or "").upper()
            if nivel == "STATE" and uf:
                tid = f"uf_{uf}"
            else:
                cod = row.get("cod_ibge")
                if cod:
                    tid = f"mun_{cod}"
        if not tid:
            continue
        hom = float(row.get("homicidios") or 0)
        ext = float(row.get("causas_externas") or 0)
        if hom:
            new_obs.append(
                {
                    "observation_id": f"obs_hom_{tid}_{year}",
                    "indicator_id": "ind_homicidios",
                    "territory_id": tid,
                    "reference_year": year,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "value": hom,
                    "unit": "count",
                    "source_id": "datasus",
                    "dataset_id": "datasus.sim_homicidios",
                    "coverage_status": "ok",
                    "confidence": "official",
                    "retrieved_at": now,
                    "geographic_level": nivel,
                }
            )
            pop_v = pop.get((tid, year))
            if pop_v and pop_v > 0:
                new_obs.append(
                    {
                        "observation_id": f"obs_hom100k_{tid}_{year}",
                        "indicator_id": "ind_homicidios_per_100k",
                        "territory_id": tid,
                        "reference_year": year,
                        "period_start": f"{year}-01-01",
                        "period_end": f"{year}-12-31",
                        "value": (hom / pop_v) * 100000.0,
                        "value_original": hom,
                        "populacao_utilizada": pop_v,
                        "unit": "per_100000",
                        "source_id": "datasus",
                        "dataset_id": "datasus.sim_homicidios_derived",
                        "confidence": "derived",
                        "retrieved_at": now,
                        "geographic_level": nivel,
                    }
                )
        if ext:
            new_obs.append(
                {
                    "observation_id": f"obs_ext_{tid}_{year}",
                    "indicator_id": "ind_mortes_causas_externas",
                    "territory_id": tid,
                    "reference_year": year,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "value": ext,
                    "unit": "count",
                    "source_id": "datasus",
                    "dataset_id": "datasus.sim_homicidios",
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
        sil / "meta_datasus_homicidios.json",
        {
            "em": now,
            "observations": len(new_obs),
            "total_observations": len(observations),
            "indicators": sorted(IDS),
            "bronze": str(bronze),
        },
    )
    print(f"OK silver DATASUS homicídios: +{len(new_obs)} obs · total={len(observations)}")
    return 0 if new_obs else 1


if __name__ == "__main__":
    raise SystemExit(main())
