#!/usr/bin/env python3
"""
Silver indicadores — TERRITORY + INDICATOR + INDICATOR_OBSERVATION.

Níveis: BRASIL / REGION / STATE / MUNICIPALITY
Indicadores: população (UF), PIB correntes (UF + município)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402


def latest_bronze_file(*names: str) -> Path | None:
    base = LAKE / "bronze" / "ibge"
    if not base.exists():
        return None
    for day in sorted(base.iterdir(), reverse=True):
        if not day.is_dir():
            continue
        for n in names:
            p = day / n
            if p.exists():
                return p
    return None


def parse_sidra_value(raw) -> float | None:
    if raw in (None, "", "...", "-", "X"):
        return None
    try:
        return float(str(raw).replace(",", "."))
    except ValueError:
        return None


def parse_year(row: dict) -> int | None:
    ano = str(row.get("D3C") or row.get("D3N") or "")[:4]
    return int(ano) if ano.isdigit() else None


def mun_uf_from_localidade(m: dict) -> tuple[str, str]:
    """Extrai sigla UF e nome do estado do JSON de municípios IBGE."""
    micro = m.get("microrregiao") or {}
    meso = micro.get("mesorregiao") or {}
    uf_obj = meso.get("UF") or {}
    if not uf_obj:
        ri = m.get("regiao-imediata") or {}
        rint = ri.get("regiao-intermediaria") or {}
        uf_obj = rint.get("UF") or {}
    return (uf_obj.get("sigla") or "").upper(), (uf_obj.get("nome") or "")


def main() -> int:
    est_path = latest_bronze_file("estados.json")
    reg_path = latest_bronze_file("regioes.json")
    mun_path = latest_bronze_file("municipios.json")
    pop_path = latest_bronze_file("sidra_6579_populacao_uf.json")
    pop_mun_path = latest_bronze_file("sidra_6579_populacao_mun.json")
    pib_uf_path = latest_bronze_file("sidra_5938_pib_uf.json")
    pib_mun_path = latest_bronze_file("sidra_5938_pib_mun.json")

    if not est_path:
        print("bronze estados ausente — rode ibge_territorios.py", file=sys.stderr)
        return 1

    estados = json.loads(est_path.read_text(encoding="utf-8"))
    regioes = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path else []
    municipios = json.loads(mun_path.read_text(encoding="utf-8")) if mun_path else []

    territories: list[dict] = [
        {
            "territory_id": "terr_br",
            "ibge_code": "1",
            "name": "Brasil",
            "territory_type": "BRASIL",
            "fonte": "ibge_localidades",
        }
    ]
    for r in regioes:
        territories.append(
            {
                "territory_id": f"terr_reg_{r['id']}",
                "ibge_code": str(r["id"]),
                "name": r["nome"],
                "territory_type": "REGION",
                "region_code": r.get("sigla"),
                "region_name": r.get("nome"),
                "fonte": "ibge_localidades",
            }
        )

    ibge_to_uf: dict[str, str] = {}
    for e in estados:
        uf = (e.get("sigla") or "").upper()
        code = str(e.get("id") or "")
        ibge_to_uf[code] = uf
        reg = e.get("regiao") or {}
        territories.append(
            {
                "territory_id": f"uf_{uf}",
                "ibge_code": code,
                "name": e.get("nome"),
                "territory_type": "STATE",
                "state_code": uf,
                "state_name": e.get("nome"),
                "region_code": reg.get("sigla"),
                "region_name": reg.get("nome"),
                "fonte": "ibge_localidades",
            }
        )

    for m in municipios:
        code = str(m.get("id") or "")
        if not code:
            continue
        uf, uf_nome = mun_uf_from_localidade(m)
        territories.append(
            {
                "territory_id": f"mun_{code}",
                "ibge_code": code,
                "name": m.get("nome"),
                "territory_type": "MUNICIPALITY",
                "state_code": uf or None,
                "state_name": uf_nome or None,
                "fonte": "ibge_localidades",
            }
        )

    indicators = [
        {
            "indicator_id": "ind_pop_estimada",
            "name": "populacao_residente_estimada",
            "display_name": "População residente estimada",
            "description": "Estimativa anual de população residente (IBGE SIDRA t/6579 v/9324).",
            "category": "demografia",
            "subcategory": "populacao",
            "unit": "pessoas",
            "neutral_direction": True,
            "aggregation_method": "sum",
            "source_id": "ibge",
            "dataset_id": "ibge.sidra_6579",
            "minimum_geographic_level": "MUNICIPALITY",
            "frequency": "annual",
            "methodology_url": "https://sidra.ibge.gov.br/tabela/6579",
            "notes": "Observação temporal — não é propriedade fixa. Lacunas em anos censitários.",
        },
        {
            "indicator_id": "ind_pib_corrente",
            "name": "pib_precos_correntes",
            "display_name": "PIB a preços correntes",
            "description": (
                "Produto Interno Bruto a preços correntes (IBGE SIDRA t/5938 v/37). "
                "Disponível em UF e município. Valores nominais em mil reais."
            ),
            "category": "economia",
            "subcategory": "pib",
            "unit": "mil_reais",
            "neutral_direction": True,
            "aggregation_method": "sum",
            "source_id": "ibge",
            "dataset_id": "ibge.sidra_5938",
            "minimum_geographic_level": "MUNICIPALITY",
            "frequency": "annual",
            "methodology_url": "https://sidra.ibge.gov.br/tabela/5938",
            "notes": (
                "Preços correntes (nominal). Não comparar anos distintos sem "
                "considerar inflação quando a análise exigir valores reais."
            ),
        },
        {
            "indicator_id": "ind_pib_per_capita",
            "name": "pib_per_capita_corrente",
            "display_name": "PIB per capita (correntes)",
            "description": (
                "Derivado: (PIB mil R$ × 1000) ÷ população estimada, no mesmo "
                "território e ano. Nominal — não deflacionado."
            ),
            "category": "economia",
            "subcategory": "pib",
            "unit": "reais_por_habitante",
            "neutral_direction": True,
            "aggregation_method": "weighted_avg",
            "source_id": "ibge",
            "dataset_id": "ibge.derived_pib_per_capita",
            "minimum_geographic_level": "MUNICIPALITY",
            "frequency": "annual",
            "methodology_url": "https://sidra.ibge.gov.br/tabela/5938",
            "notes": (
                "Indicador derivado Atlas (não publicado assim na SIDRA). "
                "Só existe quando PIB e população coincidem no ano."
            ),
        },
    ]

    observations: list[dict] = []
    now = utc_now()
    n_pop_uf = 0
    n_pop_mun = 0

    if pop_path:
        rows = json.loads(pop_path.read_text(encoding="utf-8"))
        for row in rows[1:]:
            code = str(row.get("D1C") or "")
            uf = ibge_to_uf.get(code)
            ano = parse_year(row)
            val = parse_sidra_value(row.get("V"))
            if not uf or ano is None or val is None:
                continue
            observations.append(
                {
                    "observation_id": f"obs_pop_{uf}_{ano}",
                    "indicator_id": "ind_pop_estimada",
                    "territory_id": f"uf_{uf}",
                    "reference_year": ano,
                    "period_start": f"{ano}-01-01",
                    "period_end": f"{ano}-12-31",
                    "value": val,
                    "unit": "pessoas",
                    "source_id": "ibge",
                    "dataset_id": "ibge.sidra_6579",
                    "coverage_status": "ok",
                    "confidence": "official",
                    "retrieved_at": now,
                    "fonte_url": "https://apisidra.ibge.gov.br/",
                    "geographic_level": "STATE",
                }
            )
            n_pop_uf += 1

    if pop_mun_path:
        rows = json.loads(pop_mun_path.read_text(encoding="utf-8"))
        for row in rows[1:]:
            code = str(row.get("D1C") or "")
            ano = parse_year(row)
            val = parse_sidra_value(row.get("V"))
            if not code or ano is None or val is None:
                continue
            observations.append(
                {
                    "observation_id": f"obs_pop_mun_{code}_{ano}",
                    "indicator_id": "ind_pop_estimada",
                    "territory_id": f"mun_{code}",
                    "reference_year": ano,
                    "period_start": f"{ano}-01-01",
                    "period_end": f"{ano}-12-31",
                    "value": val,
                    "unit": "pessoas",
                    "source_id": "ibge",
                    "dataset_id": "ibge.sidra_6579",
                    "coverage_status": "ok",
                    "confidence": "official",
                    "retrieved_at": now,
                    "fonte_url": "https://sidra.ibge.gov.br/tabela/6579",
                    "geographic_level": "MUNICIPALITY",
                }
            )
            n_pop_mun += 1

    def add_pib_rows(rows: list, level: str) -> int:
        n = 0
        for row in rows[1:]:
            code = str(row.get("D1C") or "")
            ano = parse_year(row)
            val = parse_sidra_value(row.get("V"))
            if not code or ano is None or val is None:
                continue
            if level == "STATE":
                uf = ibge_to_uf.get(code)
                if not uf:
                    continue
                tid = f"uf_{uf}"
                oid = f"obs_pib_{uf}_{ano}"
            else:
                tid = f"mun_{code}"
                oid = f"obs_pib_mun_{code}_{ano}"
            observations.append(
                {
                    "observation_id": oid,
                    "indicator_id": "ind_pib_corrente",
                    "territory_id": tid,
                    "reference_year": ano,
                    "period_start": f"{ano}-01-01",
                    "period_end": f"{ano}-12-31",
                    "value": val,
                    "value_reais": val * 1000.0,
                    "unit": "mil_reais",
                    "source_id": "ibge",
                    "dataset_id": "ibge.sidra_5938",
                    "coverage_status": "ok",
                    "confidence": "official",
                    "retrieved_at": now,
                    "fonte_url": "https://sidra.ibge.gov.br/tabela/5938",
                    "geographic_level": level,
                }
            )
            n += 1
        return n

    n_uf = add_pib_rows(json.loads(pib_uf_path.read_text(encoding="utf-8")), "STATE") if pib_uf_path else 0
    n_mun = (
        add_pib_rows(json.loads(pib_mun_path.read_text(encoding="utf-8")), "MUNICIPALITY")
        if pib_mun_path
        else 0
    )

    # PIB per capita derivado (só onde pop e PIB coincidem)
    pop_idx: dict[tuple[str, int], float] = {}
    pib_idx: dict[tuple[str, int], tuple[float, str]] = {}
    for o in observations:
        key = (o["territory_id"], int(o["reference_year"]))
        if o["indicator_id"] == "ind_pop_estimada":
            pop_idx[key] = float(o["value"])
        elif o["indicator_id"] == "ind_pib_corrente":
            pib_idx[key] = (float(o["value"]), o.get("geographic_level") or "")

    n_pc = 0
    for key, (pib_mil, level) in pib_idx.items():
        pop = pop_idx.get(key)
        if not pop or pop <= 0:
            continue
        tid, ano = key
        reais = pib_mil * 1000.0
        pc = reais / pop
        suf = tid.replace("uf_", "").replace("mun_", "")
        observations.append(
            {
                "observation_id": f"obs_pibpc_{suf}_{ano}",
                "indicator_id": "ind_pib_per_capita",
                "territory_id": tid,
                "reference_year": ano,
                "period_start": f"{ano}-01-01",
                "period_end": f"{ano}-12-31",
                "value": round(pc, 2),
                "unit": "reais_por_habitante",
                "numerator": reais,
                "denominator": pop,
                "source_id": "ibge",
                "dataset_id": "ibge.derived_pib_per_capita",
                "coverage_status": "derived",
                "confidence": "derived_official_inputs",
                "retrieved_at": now,
                "fonte_url": "https://sidra.ibge.gov.br/tabela/5938",
                "geographic_level": level or ("STATE" if tid.startswith("uf_") else "MUNICIPALITY"),
                "derived_from": ["ind_pib_corrente", "ind_pop_estimada"],
            }
        )
        n_pc += 1

    out = LAKE / "silver" / "indicadores"
    out.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    write_json(out / f"territories_{stamp}.json", territories)
    write_json(out / "territories_latest.json", territories)
    write_json(out / f"indicators_{stamp}.json", indicators)
    write_json(out / "indicators_latest.json", indicators)
    write_jsonl(out / f"observations_{stamp}.jsonl", observations)
    write_jsonl(out / "observations_latest.jsonl", observations)
    write_json(
        out / "meta.json",
        {
            "em": utc_now(),
            "territories": len(territories),
            "indicators": len(indicators),
            "observations": len(observations),
            "pop_uf": n_pop_uf,
            "pop_mun": n_pop_mun,
            "pib_uf": n_uf,
            "pib_mun": n_mun,
            "pib_per_capita": n_pc,
            "anos": sorted({o["reference_year"] for o in observations}),
        },
    )
    print(
        f"OK silver indicadores: terr={len(territories)} ind={len(indicators)} "
        f"obs={len(observations)} (pop_uf={n_pop_uf} pop_mun={n_pop_mun} "
        f"pib_uf={n_uf} pib_mun={n_mun} pib_pc={n_pc})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
