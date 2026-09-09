#!/usr/bin/env python3
"""
Silver DATASUS — nascimentos, óbitos, mortalidade infantil (derivada).

Lê bronze sim_sinasc_extract.jsonl e anexa observações.
Taxa mortalidade infantil = óbitos_infantis / nascidos_vivos * 1000
Taxa mortalidade geral (bruta) = óbitos / pop * 100000 (quando pop disponível)
Taxa natalidade = nascidos / pop * 1000 (quando pop disponível)
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
        "indicator_id": "ind_nascidos_vivos",
        "name": "nascidos_vivos",
        "display_name": "Nascidos vivos",
        "description": "Contagem de nascidos vivos (SINASC), residência da mãe.",
        "category": "saude",
        "unit": "count",
        "source_id": "datasus",
        "dataset_id": "datasus.sinasc",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "methodology_url": "https://datasus.saude.gov.br/informacoes-de-saude-tabnet/",
        "notes": "Fonte FTP DATASUS SINASC. Observação temporal.",
    },
    {
        "indicator_id": "ind_obitos",
        "name": "obitos",
        "display_name": "Óbitos",
        "description": "Contagem de óbitos (SIM), residência.",
        "category": "saude",
        "unit": "count",
        "source_id": "datasus",
        "dataset_id": "datasus.sim",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "methodology_url": "https://datasus.saude.gov.br/informacoes-de-saude-tabnet/",
    },
    {
        "indicator_id": "ind_obitos_infantis",
        "name": "obitos_infantis",
        "display_name": "Óbitos infantis (<1 ano)",
        "description": "Óbitos com IDADE < 400 no SIM (menores de 1 ano).",
        "category": "saude",
        "unit": "count",
        "source_id": "datasus",
        "dataset_id": "datasus.sim",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_mortalidade_infantil",
        "name": "taxa_mortalidade_infantil",
        "display_name": "Mortalidade infantil",
        "description": "Óbitos infantis / nascidos vivos × 1000. Derivado SIM÷SINASC.",
        "category": "saude",
        "unit": "per_1000_live_births",
        "higher_is_better": False,
        "source_id": "datasus",
        "dataset_id": "datasus.sim_sinasc_derived",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "notes": "Guarda numerador e denominador na observação.",
    },
    {
        "indicator_id": "ind_mortalidade_geral",
        "name": "taxa_mortalidade_geral",
        "display_name": "Mortalidade geral (bruta)",
        "description": "Óbitos / população × 100000. Derivado SIM÷IBGE.",
        "category": "saude",
        "unit": "per_100000",
        "higher_is_better": False,
        "source_id": "datasus",
        "dataset_id": "datasus.sim_derived",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_natalidade",
        "name": "taxa_natalidade",
        "display_name": "Natalidade",
        "description": "Nascidos vivos / população × 1000. Derivado SINASC÷IBGE.",
        "category": "saude",
        "unit": "per_1000",
        "source_id": "datasus",
        "dataset_id": "datasus.sinasc_derived",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
    },
]

DATASUS_IDS = {d["indicator_id"] for d in INDICATOR_DEFS}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "datasus"
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
        print("bronze datasus ausente", file=sys.stderr)
        return 1
    extract = bronze / "sim_sinasc_extract.jsonl"
    extract_mun = bronze / "sim_sinasc_mun_extract.jsonl"
    if not extract.exists() and not extract_mun.exists():
        print("extract ausente", file=sys.stderr)
        return 1

    sil = LAKE / "silver" / "indicadores"
    ind_path = sil / "indicators_latest.json"
    obs_path = sil / "observations_latest.jsonl"
    if not obs_path.exists():
        print("silver base ausente", file=sys.stderr)
        return 1

    indicators = json.loads(ind_path.read_text(encoding="utf-8")) if ind_path.exists() else []
    observations = read_jsonl(obs_path)
    observations = [o for o in observations if o.get("indicator_id") not in DATASUS_IDS]
    indicators = [i for i in indicators if i.get("indicator_id") not in DATASUS_IDS]
    indicators.extend(INDICATOR_DEFS)

    pop: dict[tuple[str, int], float] = {}
    for o in observations:
        if o.get("indicator_id") != "ind_pop_estimada":
            continue
        tid, y = o.get("territory_id"), o.get("reference_year")
        if tid and y:
            pop[(tid, int(y))] = float(o["value"])

    now = utc_now()
    # index nascimentos e óbitos por território/ano
    nasc: dict[tuple[str, int], float] = {}
    obitos: dict[tuple[str, int], float] = {}
    ob_inf: dict[tuple[str, int], float] = {}
    new_obs: list[dict] = []

    def add_count(ind_id: str, tid: str, year: int, val: float, dataset: str, nivel: str):
        short = ind_id.replace("ind_", "")[:16]
        new_obs.append(
            {
                "observation_id": f"obs_datasus_{short}_{tid}_{year}",
                "indicator_id": ind_id,
                "territory_id": tid,
                "reference_year": year,
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "value": float(val),
                "unit": "count",
                "source_id": "datasus",
                "dataset_id": dataset,
                "coverage_status": "ok",
                "confidence": "official",
                "retrieved_at": now,
                "fonte_url": "ftp://ftp.datasus.gov.br/dissemin/publicos/",
                "geographic_level": nivel,
            }
        )

    for row in read_jsonl(extract) + read_jsonl(extract_mun):
        if row.get("missing"):
            continue
        uf = (row.get("uf") or "").upper()
        year = int(row.get("exercicio") or 0)
        if not uf or not year:
            continue
        tid_uf = f"uf_{uf}"
        fonte = row.get("fonte")
        um = row.get("uf_metrics") or {}
        mm = row.get("mun_metrics") or {}
        # extract principal: UF; extract mun: prioriza mun_metrics (evita dobrar UF se ambos)
        has_mun = bool(mm)
        apply_uf = bool(um) and not has_mun

        if fonte == "sinasc":
            nv = float(um.get("nascidos_vivos") or 0)
            if apply_uf and nv:
                nasc[(tid_uf, year)] = nasc.get((tid_uf, year), 0) + nv
                add_count("ind_nascidos_vivos", tid_uf, year, nv, "datasus.sinasc", "STATE")
            for tid, cnt in mm.items():
                if cnt:
                    nasc[(tid, year)] = nasc.get((tid, year), 0) + float(cnt)
                    add_count(
                        "ind_nascidos_vivos", tid, year, float(cnt), "datasus.sinasc", "MUNICIPALITY"
                    )
        elif fonte == "sim":
            ob = float(um.get("obitos") or 0)
            oi = float(um.get("obitos_infantis") or 0)
            if apply_uf and ob:
                obitos[(tid_uf, year)] = obitos.get((tid_uf, year), 0) + ob
                add_count("ind_obitos", tid_uf, year, ob, "datasus.sim", "STATE")
            if apply_uf and oi:
                ob_inf[(tid_uf, year)] = ob_inf.get((tid_uf, year), 0) + oi
                add_count("ind_obitos_infantis", tid_uf, year, oi, "datasus.sim", "STATE")
            for tid, m in mm.items():
                obm = float(m.get("obitos") or 0)
                oim = float(m.get("obitos_infantis") or 0)
                if obm:
                    obitos[(tid, year)] = obitos.get((tid, year), 0) + obm
                    add_count("ind_obitos", tid, year, obm, "datasus.sim", "MUNICIPALITY")
                if oim:
                    ob_inf[(tid, year)] = ob_inf.get((tid, year), 0) + oim
                    add_count(
                        "ind_obitos_infantis", tid, year, oim, "datasus.sim", "MUNICIPALITY"
                    )

    # derivados
    keys = set(nasc) | set(ob_inf) | set(obitos)
    for tid, year in keys:
        nv = nasc.get((tid, year))
        oi = ob_inf.get((tid, year))
        ob = obitos.get((tid, year))
        nivel = "STATE" if tid.startswith("uf_") else "MUNICIPALITY"
        if nv and nv > 0 and oi is not None:
            tmi = (oi / nv) * 1000.0
            new_obs.append(
                {
                    "observation_id": f"obs_datasus_tmi_{tid}_{year}",
                    "indicator_id": "ind_mortalidade_infantil",
                    "territory_id": tid,
                    "reference_year": year,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "value": tmi,
                    "value_original_numerador": oi,
                    "value_original_denominador": nv,
                    "unit": "per_1000_live_births",
                    "source_id": "datasus",
                    "dataset_id": "datasus.sim_sinasc_derived",
                    "coverage_status": "ok",
                    "confidence": "derived",
                    "retrieved_at": now,
                    "geographic_level": nivel,
                }
            )
        pop_v = pop.get((tid, year))
        if pop_v and pop_v > 0:
            if ob is not None:
                new_obs.append(
                    {
                        "observation_id": f"obs_datasus_tmorb_{tid}_{year}",
                        "indicator_id": "ind_mortalidade_geral",
                        "territory_id": tid,
                        "reference_year": year,
                        "period_start": f"{year}-01-01",
                        "period_end": f"{year}-12-31",
                        "value": (ob / pop_v) * 100000.0,
                        "value_original": ob,
                        "populacao_utilizada": pop_v,
                        "unit": "per_100000",
                        "source_id": "datasus",
                        "dataset_id": "datasus.sim_derived",
                        "confidence": "derived",
                        "retrieved_at": now,
                        "geographic_level": nivel,
                    }
                )
            if nv is not None:
                new_obs.append(
                    {
                        "observation_id": f"obs_datasus_tnatal_{tid}_{year}",
                        "indicator_id": "ind_natalidade",
                        "territory_id": tid,
                        "reference_year": year,
                        "period_start": f"{year}-01-01",
                        "period_end": f"{year}-12-31",
                        "value": (nv / pop_v) * 1000.0,
                        "value_original": nv,
                        "populacao_utilizada": pop_v,
                        "unit": "per_1000",
                        "source_id": "datasus",
                        "dataset_id": "datasus.sinasc_derived",
                        "confidence": "derived",
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
        sil / "meta_datasus.json",
        {
            "em": now,
            "datasus_observations": len(new_obs),
            "total_observations": len(observations),
            "indicators": [d["indicator_id"] for d in INDICATOR_DEFS],
            "bronze": str(bronze),
        },
    )
    print(f"OK silver DATASUS: +{len(new_obs)} obs · total={len(observations)}")
    return 0 if new_obs else 1


if __name__ == "__main__":
    raise SystemExit(main())
