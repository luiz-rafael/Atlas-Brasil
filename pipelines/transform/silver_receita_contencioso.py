#!/usr/bin/env python3
"""
Silver contencioso administrativo → admin_tax_contencioso_latest.jsonl
+ opcional ind_contencioso_admin_acervo.

Nunca mesclar com DataJud LEGAL_CASE.
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
        "indicator_id": "ind_contencioso_admin_acervo",
        "name": "contencioso_admin_acervo",
        "display_name": "Acervo do contencioso administrativo tributário",
        "description": (
            "Indicador de estoque (quantidade/valor) do contencioso administrativo na RFB. "
            "Entidade ADMINISTRATIVE_TAX_CASE — separado do Judiciário/DataJud."
        ),
        "category": "fiscal",
        "unit": "count",
        "higher_is_better": None,
        "source_id": "receita_contencioso",
        "dataset_id": "rfb.contencioso_admin",
        "minimum_geographic_level": "BRASIL",
        "frequency": "annual",
        "notes": "Não confundir com LEGAL_CASE judicial.",
    },
]
IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "receita_contencioso"
    if not base.exists():
        return None
    for d in sorted([p for p in base.iterdir() if p.is_dir()], reverse=True):
        if (d / "meta.json").exists():
            return d
    return None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("SKIPPED silver_receita_contencioso: bronze ausente", flush=True)
        return 0

    meta = {}
    mp = bronze / "meta.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    cases = read_jsonl(bronze / "admin_tax_contencioso_extract.jsonl")
    inds = read_jsonl(bronze / "admin_tax_contencioso_indicators.jsonl")

    if meta.get("status") == "SKIPPED" and not cases and not inds:
        print(
            f"SKIPPED silver_receita_contencioso: {meta.get('reason') or 'sem dados'}",
            flush=True,
        )
        return 0

    now = utc_now()
    silver_cases = [
        {**r, "retrieved_at": now, "semantic": "ADMINISTRATIVE_TAX_CASE"} for r in cases
    ]
    silver_inds = [{**r, "retrieved_at": now} for r in inds]

    sil = LAKE / "silver" / "fiscal"
    sil.mkdir(parents=True, exist_ok=True)
    write_jsonl(sil / "admin_tax_contencioso_latest.jsonl", silver_cases)
    write_jsonl(sil / f"admin_tax_contencioso_{day_stamp()}.jsonl", silver_cases)
    write_jsonl(sil / "admin_tax_contencioso_indicators_latest.jsonl", silver_inds)
    write_json(
        sil / "admin_tax_contencioso_meta.json",
        {
            "cases": len(silver_cases),
            "indicators": len(silver_inds),
            "updated_at": now,
            "nota": "ADMINISTRATIVE_TAX_CASE ≠ LEGAL_CASE",
        },
    )

    # optional indicator series
    if silver_inds:
        sil_ind = LAKE / "silver" / "indicadores"
        ind_path = sil_ind / "indicators_latest.json"
        obs_path = sil_ind / "observations_latest.jsonl"
        if obs_path.exists():
            indicators = json.loads(ind_path.read_text(encoding="utf-8")) if ind_path.exists() else []
            observations = read_jsonl(obs_path)
            observations = [o for o in observations if o.get("indicator_id") not in IDS]
            indicators = [i for i in indicators if i.get("indicator_id") not in IDS]
            indicators.extend(INDICATOR_DEFS)
            new_obs = []
            for r in silver_inds:
                year = int(r.get("year") or 0)
                qtd = r.get("quantidade")
                if not year or qtd is None:
                    continue
                new_obs.append(
                    {
                        "observation_id": f"obs_contencioso_admin_br_{year}",
                        "indicator_id": "ind_contencioso_admin_acervo",
                        "territory_id": "terr_br",
                        "territory_type": "BRASIL",
                        "year": year,
                        "period_start": f"{year}-01-01",
                        "value": float(qtd),
                        "unit": "count",
                        "source_id": "receita_contencioso",
                        "dataset_id": "rfb.contencioso_admin",
                        "retrieved_at": now,
                        "meta": {
                            "valor": r.get("valor"),
                            "tempo_medio": r.get("tempo_medio"),
                            "nota": "Acervo administrativo — não judicial",
                        },
                    }
                )
            observations.extend(new_obs)
            stamp = day_stamp()
            write_json(ind_path, indicators)
            write_jsonl(obs_path, observations)
            write_jsonl(sil_ind / f"observations_{stamp}.jsonl", observations)
            write_json(sil_ind / f"indicators_{stamp}.json", indicators)
            print(
                f"OK silver_receita_contencioso cases={len(silver_cases)} "
                f"ind_obs={len(new_obs)} -> {sil}",
                flush=True,
            )
            return 0

    print(
        f"OK silver_receita_contencioso cases={len(silver_cases)} indicators={len(silver_inds)} -> {sil}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
