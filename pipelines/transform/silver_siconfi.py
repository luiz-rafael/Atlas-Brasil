#!/usr/bin/env python3
"""
Silver SICONFI — observações financeiras anuais (nominal R$).

Lê extratos bronze dca_extract.jsonl + rgf_rcl_extract.jsonl
e anexa a observations_latest.jsonl / indicators_latest.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402

METRIC_TO_IND = {
    "receita_bruta": "ind_receita_bruta",
    "despesa_total": "ind_despesa_total",
    "despesa_pessoal": "ind_despesa_pessoal",
    "despesa_investimentos": "ind_despesa_investimentos",
    "despesa_saude": "ind_despesa_saude",
    "despesa_educacao": "ind_despesa_educacao",
    "transferencias_correntes": "ind_transferencias_correntes",
    "rcl": "ind_rcl",
}

PER_CAPITA = {
    "despesa_saude": "ind_despesa_saude_per_capita",
    "despesa_educacao": "ind_despesa_educacao_per_capita",
    "despesa_pessoal": "ind_despesa_pessoal_per_capita",
    "despesa_investimentos": "ind_investimento_per_capita",
}

INDICATOR_DEFS = [
    {
        "indicator_id": "ind_receita_bruta",
        "name": "receita_bruta_realizada",
        "display_name": "Receita bruta realizada",
        "description": "Receitas (exceto intra-orçamentárias), Receitas Brutas Realizadas — DCA Anexo I-C.",
        "category": "financas",
        "unit": "BRL",
        "higher_is_better": None,
        "neutral_direction": True,
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "methodology_url": "https://www.tesourotransparente.gov.br/consultas/consultas-siconfi/siconfi-api-de-dados-abertos",
        "notes": "Valores nominais (correntes). Observação temporal — não atribui causalidade política.",
    },
    {
        "indicator_id": "ind_despesa_total",
        "name": "despesa_total_empenhada",
        "display_name": "Despesa total empenhada",
        "description": "Total Geral da Despesa — Despesas Empenhadas (DCA Anexo I-D).",
        "category": "financas",
        "unit": "BRL",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
        "methodology_url": "https://www.tesourotransparente.gov.br/consultas/consultas-siconfi/siconfi-api-de-dados-abertos",
    },
    {
        "indicator_id": "ind_despesa_pessoal",
        "name": "despesa_pessoal_empenhada",
        "display_name": "Despesa com pessoal",
        "description": "Pessoal e Encargos Sociais — Despesas Empenhadas (DCA).",
        "category": "financas",
        "unit": "BRL",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_despesa_investimentos",
        "name": "despesa_investimentos_empenhada",
        "display_name": "Investimentos (despesa)",
        "description": "Grupo Investimentos — Despesas Empenhadas (DCA).",
        "category": "financas",
        "unit": "BRL",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_despesa_saude",
        "name": "despesa_funcao_saude",
        "display_name": "Despesa função saúde",
        "description": "Função 10 — Saúde, Despesas Empenhadas (DCA Anexo I-E).",
        "category": "financas",
        "subcategory": "saude",
        "unit": "BRL",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_despesa_educacao",
        "name": "despesa_funcao_educacao",
        "display_name": "Despesa função educação",
        "description": "Função 12 — Educação, Despesas Empenhadas (DCA Anexo I-E).",
        "category": "financas",
        "subcategory": "educacao",
        "unit": "BRL",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_transferencias_correntes",
        "name": "transferencias_correntes",
        "display_name": "Transferências correntes",
        "description": "Receita de transferências correntes — DCA Anexo I-C.",
        "category": "financas",
        "unit": "BRL",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_rcl",
        "name": "receita_corrente_liquida",
        "display_name": "Receita corrente líquida (RCL)",
        "description": "RCL do RGF (3º quadrimestre), poder Executivo.",
        "category": "financas",
        "unit": "BRL",
        "source_id": "siconfi",
        "dataset_id": "siconfi.rgf",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
        "notes": "Referência anual = valor do 3º quadrimestre do exercício.",
    },
    {
        "indicator_id": "ind_despesa_saude_per_capita",
        "name": "despesa_saude_per_capita",
        "display_name": "Gasto saúde per capita",
        "description": "Despesa função saúde ÷ população estimada (mesmo ano). Derivado.",
        "category": "financas",
        "unit": "BRL_per_capita",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca_derived",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
        "notes": "Guarda valor_original e população_utilizada na observação.",
    },
    {
        "indicator_id": "ind_despesa_educacao_per_capita",
        "name": "despesa_educacao_per_capita",
        "display_name": "Gasto educação per capita",
        "description": "Despesa função educação ÷ população estimada. Derivado.",
        "category": "financas",
        "unit": "BRL_per_capita",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca_derived",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_despesa_pessoal_per_capita",
        "name": "despesa_pessoal_per_capita",
        "display_name": "Despesa pessoal per capita",
        "description": "Despesa com pessoal ÷ população estimada. Derivado.",
        "category": "financas",
        "unit": "BRL_per_capita",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca_derived",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_investimento_per_capita",
        "name": "investimento_per_capita",
        "display_name": "Investimento per capita",
        "description": "Investimentos ÷ população estimada. Derivado.",
        "category": "financas",
        "unit": "BRL_per_capita",
        "source_id": "siconfi",
        "dataset_id": "siconfi.dca_derived",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
    },
]


def latest_bronze_dir() -> Path | None:
    base = LAKE / "bronze" / "siconfi"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    return days[0] if days else None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # linhas truncadas por escrita concorrente no bronze
            print(f"  aviso: JSON inválido {path.name}:{i} (ignorado)", flush=True)
            continue
    return out


def territory_id(nivel: str, cod: int, uf: str | None) -> str | None:
    if nivel == "STATE" and uf:
        return f"uf_{uf.upper()}"
    if nivel == "MUNICIPALITY":
        return f"mun_{cod}"
    return None


def main() -> int:
    bronze = latest_bronze_dir()
    if not bronze:
        print("bronze siconfi ausente", file=sys.stderr)
        return 1

    sil = LAKE / "silver" / "indicadores"
    ind_path = sil / "indicators_latest.json"
    obs_path = sil / "observations_latest.jsonl"
    if not obs_path.exists():
        print("silver base ausente", file=sys.stderr)
        return 1

    indicators = json.loads(ind_path.read_text(encoding="utf-8")) if ind_path.exists() else []
    observations = read_jsonl(obs_path)

    # remove siconfi anterior
    siconfi_ids = {d["indicator_id"] for d in INDICATOR_DEFS}
    observations = [o for o in observations if o.get("indicator_id") not in siconfi_ids]
    indicators = [i for i in indicators if i.get("indicator_id") not in siconfi_ids]
    indicators.extend(INDICATOR_DEFS)

    # pop index for per capita (STATE)
    pop: dict[tuple[str, int], float] = {}
    for o in observations:
        if o.get("indicator_id") != "ind_pop_estimada":
            continue
        tid = o.get("territory_id")
        y = o.get("reference_year")
        if tid and y:
            pop[(tid, int(y))] = float(o["value"])

    now = utc_now()
    new_obs: list[dict] = []
    rows = read_jsonl(bronze / "dca_extract.jsonl") + read_jsonl(bronze / "rgf_rcl_extract.jsonl")

    for row in rows:
        nivel = row.get("nivel") or ""
        cod = int(row.get("cod_ibge") or 0)
        uf = row.get("uf")
        year = int(row.get("exercicio") or 0)
        tid = territory_id(nivel, cod, uf)
        if not tid or not year:
            continue
        metrics = row.get("metrics") or {}
        for metric, val in metrics.items():
            if val is None or metric not in METRIC_TO_IND:
                continue
            ind_id = METRIC_TO_IND[metric]
            short = {
                "receita_bruta": "rec_bruta",
                "despesa_total": "desp_tot",
                "despesa_pessoal": "desp_pess",
                "despesa_investimentos": "desp_inv",
                "despesa_saude": "desp_sau",
                "despesa_educacao": "desp_edu",
                "transferencias_correntes": "transf_cor",
                "rcl": "rcl",
            }.get(metric, metric[:12])
            obs = {
                "observation_id": f"obs_siconfi_{short}_{tid}_{year}",
                "indicator_id": ind_id,
                "territory_id": tid,
                "reference_year": year,
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "value": float(val),
                "value_reais": float(val),
                "unit": "BRL",
                "source_id": "siconfi",
                "dataset_id": "siconfi.rgf" if metric == "rcl" else "siconfi.dca",
                "coverage_status": "ok",
                "confidence": "official",
                "retrieved_at": row.get("retrieved_at") or now,
                "fonte_url": "http://apidatalake.tesouro.gov.br/docs/siconfi/",
                "geographic_level": nivel,
                "metric_key": metric,
            }
            new_obs.append(obs)

            # per capita (quando houver pop no mesmo ano)
            if metric in PER_CAPITA and (tid, year) in pop and pop[(tid, year)] > 0:
                pop_v = pop[(tid, year)]
                pc = float(val) / pop_v
                new_obs.append(
                    {
                        "observation_id": f"obs_siconfi_pc_{short}_{tid}_{year}",
                        "indicator_id": PER_CAPITA[metric],
                        "territory_id": tid,
                        "reference_year": year,
                        "period_start": f"{year}-01-01",
                        "period_end": f"{year}-12-31",
                        "value": pc,
                        "value_original": float(val),
                        "populacao_utilizada": pop_v,
                        "unit": "BRL_per_capita",
                        "source_id": "siconfi",
                        "dataset_id": "siconfi.dca_derived",
                        "coverage_status": "ok",
                        "confidence": "derived",
                        "retrieved_at": now,
                        "geographic_level": nivel,
                    }
                )

    # dedupe by observation_id (último ganha)
    by_id: dict[str, dict] = {o["observation_id"]: o for o in new_obs}
    new_obs = list(by_id.values())
    observations.extend(new_obs)

    stamp = day_stamp()
    write_json(sil / f"indicators_{stamp}.json", indicators)
    write_json(sil / "indicators_latest.json", indicators)
    write_jsonl(sil / f"observations_{stamp}.jsonl", observations)
    write_jsonl(sil / "observations_latest.jsonl", observations)
    write_json(
        sil / "meta_siconfi.json",
        {
            "em": now,
            "siconfi_observations": len(new_obs),
            "total_observations": len(observations),
            "indicators": [d["indicator_id"] for d in INDICATOR_DEFS],
            "bronze": str(bronze),
        },
    )
    print(f"OK silver SICONFI: +{len(new_obs)} obs · total={len(observations)}")
    return 0 if new_obs else 1


if __name__ == "__main__":
    raise SystemExit(main())
