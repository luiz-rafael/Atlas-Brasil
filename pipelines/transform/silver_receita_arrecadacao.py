#!/usr/bin/env python3
"""
Silver arrecadação RF — ind_arrecadacao_federal (ano/mês; UF se disponível).

Nota: arrecadação RF ≠ toda receita pública brasileira.
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
        "indicator_id": "ind_arrecadacao_federal",
        "name": "arrecadacao_federal",
        "display_name": "Arrecadação federal (RF)",
        "description": (
            "Arrecadação das receitas federais (série histórica RFB). "
            "Não representa toda a receita pública brasileira (estados/municípios/outras)."
        ),
        "category": "fiscal",
        "unit": "BRL",
        "higher_is_better": None,
        "source_id": "receita_arrecadacao",
        "dataset_id": "rfb.arrecadacao",
        "minimum_geographic_level": "BRASIL",
        "frequency": "monthly",
        "notes": "Valores convertidos de R$ milhões (fonte) para R$. Contas do Brasil — início.",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "receita_arrecadacao"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    for d in days:
        if (d / "arrecadacao_extract.jsonl").exists():
            return d
    return None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("SKIPPED silver_receita_arrecadacao: bronze ausente", flush=True)
        return 0

    sil = LAKE / "silver" / "indicadores"
    ind_path = sil / "indicators_latest.json"
    obs_path = sil / "observations_latest.jsonl"
    if not obs_path.exists():
        print("silver base indicadores ausente — rode silver_indicadores.py antes", file=sys.stderr)
        return 1

    indicators = json.loads(ind_path.read_text(encoding="utf-8")) if ind_path.exists() else []
    observations = read_jsonl(obs_path)
    observations = [o for o in observations if o.get("indicator_id") not in IDS]
    indicators = [i for i in indicators if i.get("indicator_id") not in IDS]
    indicators.extend(INDICATOR_DEFS)

    now = utc_now()
    new_obs: list[dict] = []
    for row in read_jsonl(bronze / "arrecadacao_extract.jsonl"):
        year = int(row.get("ano") or 0)
        month = int(row.get("mes") or 0)
        val = row.get("valor")
        tid = row.get("territory_id") or "terr_br"
        if not year or not month or val is None:
            continue
        uf = (row.get("uf") or "").upper() or None
        suf = uf or "br"
        new_obs.append(
            {
                "observation_id": f"obs_arr_fed_{suf}_{year}_{month:02d}",
                "indicator_id": "ind_arrecadacao_federal",
                "territory_id": tid if not uf else f"uf_{uf}",
                "territory_type": row.get("territory_type") or ("STATE" if uf else "BRASIL"),
                "year": year,
                "month": month,
                "period_start": f"{year}-{month:02d}-01",
                "value": float(val),
                "unit": "BRL",
                "source_id": "receita_arrecadacao",
                "dataset_id": "rfb.arrecadacao",
                "retrieved_at": now,
                "meta": {
                    "valor_milhoes": row.get("valor_milhoes"),
                    "rubrica": row.get("rubrica"),
                    "nota": row.get("nota"),
                },
            }
        )

    observations.extend(new_obs)
    sil.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    write_json(ind_path, indicators)
    write_jsonl(obs_path, observations)
    write_jsonl(sil / f"observations_{stamp}.jsonl", observations)
    write_json(sil / f"indicators_{stamp}.json", indicators)

    print(
        f"OK silver_receita_arrecadacao obs={len(new_obs)} indicators+=1 -> {sil}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
