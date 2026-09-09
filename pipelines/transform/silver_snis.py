#!/usr/bin/env python3
"""
Silver SNIS — cobertura de água/esgoto (%).

ind_agua_atendimento, ind_esgoto_atendimento, ind_esgoto_tratamento

P3 estadual: além do MUNICIPALITY, agrega STATE (média ponderada por
ind_pop_estimada do mesmo ano; se pop ausente, média simples).
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
        "indicator_id": "ind_agua_atendimento",
        "name": "agua_atendimento_pct",
        "display_name": "Atendimento de água (%)",
        "description": "Índice de atendimento de água (SNIS IN055 ou equivalente). UF = média ponderada por pop.",
        "category": "saneamento",
        "unit": "percent",
        "higher_is_better": True,
        "source_id": "snis",
        "dataset_id": "snis.ae",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
        "methodology_url": "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/snis",
    },
    {
        "indicator_id": "ind_esgoto_atendimento",
        "name": "esgoto_atendimento_pct",
        "display_name": "Atendimento/coleta de esgoto (%)",
        "description": "Índice de coleta/atendimento de esgoto (SNIS IN015/IN056). UF = média ponderada por pop.",
        "category": "saneamento",
        "unit": "percent",
        "higher_is_better": True,
        "source_id": "snis",
        "dataset_id": "snis.ae",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
    },
    {
        "indicator_id": "ind_esgoto_tratamento",
        "name": "esgoto_tratamento_pct",
        "display_name": "Tratamento de esgoto (%)",
        "description": "Índice de tratamento de esgoto (SNIS IN016/IN046). UF = média ponderada por pop.",
        "category": "saneamento",
        "unit": "percent",
        "higher_is_better": True,
        "source_id": "snis",
        "dataset_id": "snis.ae",
        "minimum_geographic_level": "STATE",
        "frequency": "annual",
    },
]

IDS = {d["indicator_id"] for d in INDICATOR_DEFS}
METRIC_TO_IND = {
    "agua_atendimento_pct": ("ind_agua_atendimento", "agua"),
    "esgoto_atendimento_pct": ("ind_esgoto_atendimento", "esg_at"),
    "esgoto_tratamento_pct": ("ind_esgoto_tratamento", "esg_tr"),
}


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "snis"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    return days[0] if days else None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_mun_uf_map(sil: Path) -> dict[str, str]:
    """mun_XXXXXXX → UF sigla."""
    path = sil / "territories_latest.json"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for t in json.loads(path.read_text(encoding="utf-8")):
        if t.get("territory_type") != "MUNICIPALITY":
            continue
        code = str(t.get("ibge_code") or "").strip()
        uf = str(t.get("state_code") or t.get("uf") or "").upper()[:2]
        if len(code) >= 6 and uf:
            out[f"mun_{code}"] = uf
            out[code] = uf
            out[code[:6]] = uf
    return out


def load_pop_by_mun_year(observations: list[dict]) -> dict[tuple[str, int], float]:
    pop: dict[tuple[str, int], float] = {}
    for o in observations:
        if o.get("indicator_id") != "ind_pop_estimada":
            continue
        tid = o.get("territory_id") or ""
        if not str(tid).startswith("mun_"):
            continue
        try:
            year = int(o.get("reference_year") or 0)
            val = float(o.get("value"))
        except (TypeError, ValueError):
            continue
        if year and val > 0:
            pop[(tid, year)] = val
    return pop


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("bronze snis ausente", file=sys.stderr)
        return 1
    extract = bronze / "snis_ae_extract.jsonl"
    if not extract.exists():
        print("extract snis ausente", file=sys.stderr)
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

    mun_uf = load_mun_uf_map(sil)
    pop = load_pop_by_mun_year(observations)

    now = utc_now()
    new_obs: list[dict] = []
    # (uf, year, ind_id) → [weighted_sum, weight_sum, simple_sum, n]
    uf_acc: dict[tuple[str, int, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])

    for row in read_jsonl(extract):
        code = str(row.get("cod_ibge") or "")
        year = int(row.get("ano") or 0)
        if not code or not year:
            continue
        tid = f"mun_{code}" if not code.startswith("mun_") else code
        code_clean = tid.replace("mun_", "")
        uf = mun_uf.get(tid) or mun_uf.get(code_clean) or mun_uf.get(code_clean[:6]) or ""
        for metric, (ind_id, short) in METRIC_TO_IND.items():
            val = row.get(metric)
            if val is None:
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue
            new_obs.append(
                {
                    "observation_id": f"obs_snis_{short}_{code_clean}_{year}",
                    "indicator_id": ind_id,
                    "territory_id": tid if tid.startswith("mun_") else f"mun_{code_clean}",
                    "reference_year": year,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "value": fval,
                    "unit": "percent",
                    "source_id": "snis",
                    "dataset_id": "snis.ae",
                    "coverage_status": "ok",
                    "confidence": "official",
                    "retrieved_at": now,
                    "geographic_level": "MUNICIPALITY",
                }
            )
            if uf:
                w = pop.get((tid if tid.startswith("mun_") else f"mun_{code_clean}", year), 0.0)
                acc = uf_acc[(uf, year, ind_id)]
                if w > 0:
                    acc[0] += fval * w
                    acc[1] += w
                acc[2] += fval
                acc[3] += 1

    short_by_ind = {ind: short for _m, (ind, short) in METRIC_TO_IND.items()}
    n_uf = 0
    for (uf, year, ind_id), (wsum, wtot, ssum, n) in uf_acc.items():
        if n <= 0:
            continue
        value = (wsum / wtot) if wtot > 0 else (ssum / n)
        short = short_by_ind.get(ind_id, "x")
        new_obs.append(
            {
                "observation_id": f"obs_snis_{short}_uf_{uf}_{year}",
                "indicator_id": ind_id,
                "territory_id": f"uf_{uf}",
                "reference_year": year,
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "value": round(float(value), 4),
                "unit": "percent",
                "source_id": "snis",
                "dataset_id": "snis.ae_uf_agg",
                "coverage_status": "ok",
                "confidence": "derived",
                "retrieved_at": now,
                "geographic_level": "STATE",
                "notes": "pop-weighted mean of municipal SNIS when pop available",
            }
        )
        n_uf += 1

    by_id = {o["observation_id"]: o for o in new_obs}
    new_obs = list(by_id.values())
    observations.extend(new_obs)

    stamp = day_stamp()
    write_json(sil / f"indicators_{stamp}.json", indicators)
    write_json(sil / "indicators_latest.json", indicators)
    write_jsonl(sil / f"observations_{stamp}.jsonl", observations)
    write_jsonl(sil / "observations_latest.jsonl", observations)
    write_json(
        sil / "meta_snis.json",
        {
            "em": now,
            "observations": len(new_obs),
            "state_observations": n_uf,
            "total_observations": len(observations),
        },
    )
    print(f"OK silver SNIS: +{len(new_obs)} obs (UF={n_uf}) · total={len(observations)}")
    return 0 if new_obs else 1


if __name__ == "__main__":
    raise SystemExit(main())
