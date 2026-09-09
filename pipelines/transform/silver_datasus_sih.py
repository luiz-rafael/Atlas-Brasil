#!/usr/bin/env python3
"""Silver DATASUS SIH — ind_internacoes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402

INDICATOR_DEFS = [
    {
        "indicator_id": "ind_internacoes",
        "name": "internacoes_sih",
        "display_name": "Internações (SIH)",
        "description": "Contagem anual de AIH (SIH RD) por UF; município se ATLAS_SIH_MUN=1.",
        "category": "saude",
        "unit": "count",
        "source_id": "datasus_sih",
        "dataset_id": "datasus.sih_rd",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
        "methodology_url": "https://datasus.saude.gov.br/",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "datasus_sih"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    return days[0] if days else None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def rebuild_annual_from_monthly(bronze: Path) -> Path | None:
    """Se annual sumiu / incompleto, reconstrói a partir de sih_extract.jsonl."""
    monthly = bronze / "sih_extract.jsonl"
    annual = bronze / "sih_annual_extract.jsonl"
    if not monthly.exists():
        return annual if annual.exists() else None
    from collections import defaultdict

    acc: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"internacoes": 0, "mun_metrics": defaultdict(int)}
    )
    for line in monthly.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("missing"):
            continue
        uf, year = row.get("uf"), row.get("exercicio")
        if not uf or not year:
            continue
        acc[(uf, int(year))]["internacoes"] += int(row.get("internacoes") or 0)
        for tid, c in (row.get("mun_metrics") or {}).items():
            acc[(uf, int(year))]["mun_metrics"][tid] += int(c)
    if not acc:
        return annual if annual.exists() else None
    with annual.open("w", encoding="utf-8") as f:
        for (uf, year), m in sorted(acc.items()):
            f.write(
                json.dumps(
                    {
                        "uf": uf,
                        "exercicio": year,
                        "internacoes": m["internacoes"],
                        "mun_metrics": dict(m["mun_metrics"]),
                        "fonte": "datasus_sih_rd",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return annual


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("SKIPPED silver_datasus_sih: bronze ausente", flush=True)
        return 0
    annual = rebuild_annual_from_monthly(bronze)
    if not annual or not annual.exists():
        print("SKIPPED silver_datasus_sih: annual ausente", flush=True)
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
    for row in read_jsonl(annual):
        uf = row.get("uf")
        year = int(row.get("exercicio") or 0)
        val = row.get("internacoes")
        if not uf or not year or val is None:
            continue
        new_obs.append(
            {
                "observation_id": f"obs_intern_{uf}_{year}",
                "indicator_id": "ind_internacoes",
                "territory_id": f"uf_{uf}",
                "reference_year": year,
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "value": float(val),
                "unit": "count",
                "source_id": "datasus_sih",
                "dataset_id": "datasus.sih_rd",
                "coverage_status": "ok",
                "confidence": "official",
                "retrieved_at": now,
                "geographic_level": "STATE",
            }
        )
        for tid, n in (row.get("mun_metrics") or {}).items():
            code = tid.replace("mun_", "")
            new_obs.append(
                {
                    "observation_id": f"obs_intern_mun_{code}_{year}",
                    "indicator_id": "ind_internacoes",
                    "territory_id": tid,
                    "reference_year": year,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "value": float(n),
                    "unit": "count",
                    "source_id": "datasus_sih",
                    "dataset_id": "datasus.sih_rd",
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
    write_json(sil / "meta_datasus_sih.json", {"em": now, "observations": len(new_obs)})
    print(f"OK silver SIH: +{len(new_obs)} obs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
