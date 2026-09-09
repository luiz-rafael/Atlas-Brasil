#!/usr/bin/env python3
"""
Silver Novo CAGED — observações anuais de fluxo formal por UF e município.

Agrega competências mensais → ano:
  ind_caged_admissoes, ind_caged_desligamentos, ind_caged_saldo

Lê caged_mov_uf_extract.jsonl e, se existir, caged_mov_mun_extract.jsonl.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402

INDICATOR_DEFS = [
    {
        "indicator_id": "ind_caged_admissoes",
        "name": "caged_admissoes",
        "display_name": "CAGED — admissões",
        "description": "Soma anual de admissões (fluxo Novo CAGED / CAGEDMOV).",
        "category": "emprego",
        "unit": "count",
        "source_id": "caged",
        "dataset_id": "caged.novo_mov",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "methodology_url": "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/estatisticas-trabalho/o-pdet/o-que-e-o-novo-caged",
        "notes": "Fluxo de emprego formal (UF + município quando collect mun). Não é taxa de desemprego.",
    },
    {
        "indicator_id": "ind_caged_desligamentos",
        "name": "caged_desligamentos",
        "display_name": "CAGED — desligamentos",
        "description": "Soma anual de desligamentos (Novo CAGED).",
        "category": "emprego",
        "unit": "count",
        "source_id": "caged",
        "dataset_id": "caged.novo_mov",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_caged_saldo",
        "name": "caged_saldo",
        "display_name": "CAGED — saldo",
        "description": "Saldo anual = admissões − desligamentos (fluxo formal).",
        "category": "emprego",
        "unit": "count",
        "source_id": "caged",
        "dataset_id": "caged.novo_mov",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "notes": "Não interpretar como taxa de desemprego. Nível mínimo MUNICIPALITY quando extract mun disponível.",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "caged"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    return days[0] if days else None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_mun6_map() -> dict[str, str]:
    sil = LAKE / "silver" / "indicadores" / "territories_latest.json"
    if not sil.exists():
        return {}
    territories = json.loads(sil.read_text(encoding="utf-8"))
    m: dict[str, str] = {}
    for t in territories:
        if t.get("territory_type") != "MUNICIPALITY":
            continue
        code = str(t.get("ibge_code") or "")
        if len(code) >= 6:
            m[code[:6]] = f"mun_{code}"
    return m


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("bronze caged ausente", file=sys.stderr)
        return 1
    extract_uf = bronze / "caged_mov_uf_extract.jsonl"
    extract_mun = bronze / "caged_mov_mun_extract.jsonl"
    # também procura extracts em dias anteriores se o latest não tiver
    if not extract_uf.exists() or not extract_mun.exists():
        base = LAKE / "bronze" / "caged"
        for day in sorted([p for p in base.iterdir() if p.is_dir()], reverse=True):
            if not extract_uf.exists() and (day / "caged_mov_uf_extract.jsonl").exists():
                extract_uf = day / "caged_mov_uf_extract.jsonl"
            if not extract_mun.exists() and (day / "caged_mov_mun_extract.jsonl").exists():
                extract_mun = day / "caged_mov_mun_extract.jsonl"
    if not extract_uf.exists() and not extract_mun.exists():
        print("extract caged ausente", file=sys.stderr)
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

    annual_uf: dict[int, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"admissoes": 0, "desligamentos": 0, "saldo": 0})
    )
    annual_mun: dict[int, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"admissoes": 0, "desligamentos": 0, "saldo": 0})
    )
    mun6 = load_mun6_map()

    for row in read_jsonl(extract_uf):
        year = int(row.get("ano") or 0)
        if not year:
            continue
        for uf, m in (row.get("uf_metrics") or {}).items():
            b = annual_uf[year][uf]
            b["admissoes"] += int(m.get("admissoes") or 0)
            b["desligamentos"] += int(m.get("desligamentos") or 0)
            b["saldo"] += int(m.get("saldo") or 0)
        for code6, m in (row.get("mun_metrics") or {}).items():
            tid = mun6.get(str(code6)[:6]) or f"mun_{code6}"
            b = annual_mun[year][tid]
            b["admissoes"] += int(m.get("admissoes") or 0)
            b["desligamentos"] += int(m.get("desligamentos") or 0)
            b["saldo"] += int(m.get("saldo") or 0)

    for row in read_jsonl(extract_mun):
        year = int(row.get("ano") or 0)
        if not year:
            continue
        for code6, m in (row.get("mun_metrics") or {}).items():
            tid = mun6.get(str(code6)[:6]) or f"mun_{code6}"
            b = annual_mun[year][tid]
            b["admissoes"] += int(m.get("admissoes") or 0)
            b["desligamentos"] += int(m.get("desligamentos") or 0)
            b["saldo"] += int(m.get("saldo") or 0)

    now = utc_now()
    new_obs: list[dict] = []
    mapping = [
        ("admissoes", "ind_caged_admissoes", "adm"),
        ("desligamentos", "ind_caged_desligamentos", "des"),
        ("saldo", "ind_caged_saldo", "sal"),
    ]
    for year, by_uf in annual_uf.items():
        for uf, m in by_uf.items():
            tid = f"uf_{uf}"
            for key, ind_id, short in mapping:
                val = float(m.get(key) or 0)
                new_obs.append(
                    {
                        "observation_id": f"obs_caged_{short}_{uf}_{year}",
                        "indicator_id": ind_id,
                        "territory_id": tid,
                        "reference_year": year,
                        "period_start": f"{year}-01-01",
                        "period_end": f"{year}-12-31",
                        "value": val,
                        "unit": "count",
                        "source_id": "caged",
                        "dataset_id": "caged.novo_mov",
                        "coverage_status": "ok",
                        "confidence": "official",
                        "retrieved_at": now,
                        "fonte_url": f"ftp://ftp.mtps.gov.br/pdet/microdados/NOVO CAGED/{year}/",
                        "geographic_level": "STATE",
                        "notes": "Fluxo formal anual (soma das competências mensais).",
                    }
                )

    for year, by_mun in annual_mun.items():
        for tid, m in by_mun.items():
            code = tid.replace("mun_", "")
            for key, ind_id, short in mapping:
                val = float(m.get(key) or 0)
                new_obs.append(
                    {
                        "observation_id": f"obs_caged_{short}_mun_{code}_{year}",
                        "indicator_id": ind_id,
                        "territory_id": tid,
                        "reference_year": year,
                        "period_start": f"{year}-01-01",
                        "period_end": f"{year}-12-31",
                        "value": val,
                        "unit": "count",
                        "source_id": "caged",
                        "dataset_id": "caged.novo_mov_mun",
                        "coverage_status": "ok",
                        "confidence": "official",
                        "retrieved_at": now,
                        "fonte_url": f"ftp://ftp.mtps.gov.br/pdet/microdados/NOVO CAGED/{year}/",
                        "geographic_level": "MUNICIPALITY",
                        "notes": "Fluxo formal anual municipal.",
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
        sil / "meta_caged.json",
        {
            "em": now,
            "caged_observations": len(new_obs),
            "total_observations": len(observations),
            "years_uf": sorted(annual_uf.keys()),
            "years_mun": sorted(annual_mun.keys()),
            "has_mun_extract": extract_mun.exists(),
        },
    )
    print(
        f"OK silver CAGED: +{len(new_obs)} obs · uf_years={sorted(annual_uf.keys())} "
        f"mun_years={sorted(annual_mun.keys())} · total={len(observations)}"
    )
    return 0 if new_obs else 1


if __name__ == "__main__":
    raise SystemExit(main())
