#!/usr/bin/env python3
"""
Gold indicadores — enriquece nós uf_* na KB + grava atlas-brasil-indicators.json.

Observações NÃO vão para o grafo (spec §59). Arquivo separado para UI mapa/tabela.
"""

from __future__ import annotations

import gc
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"
OUT_IND = ROOT / "data" / "atlas-brasil-indicators.json"


def _load_json(path: Path):
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write_json_compact(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    sil = LAKE / "silver" / "indicadores"
    territories = _load_json(sil / "territories_latest.json") or []
    indicators = _load_json(sil / "indicators_latest.json") or []
    obs_path = sil / "observations_latest.jsonl"
    if not territories:
        print("silver indicadores vazio", file=sys.stderr)
        return 1
    if not obs_path.exists():
        print("observations_latest.jsonl ausente", file=sys.stderr)
        return 1

    state_ids = {
        t["territory_id"]
        for t in territories
        if t.get("territory_type") == "STATE" and t.get("territory_id")
    }
    cobertura_pop: dict[str, set[int]] = defaultdict(set)
    cobertura_pib: dict[str, set[int]] = defaultdict(set)

    # Passo 1: contar + cobertura UF (sem acumular observations)
    n_obs = 0
    with obs_path.open(encoding="utf-8") as inp:
        for line in inp:
            if not line.strip():
                continue
            o = json.loads(line)
            n_obs += 1
            tid = o.get("territory_id")
            if tid not in state_ids:
                continue
            iid = o.get("indicator_id")
            yr = o.get("reference_year")
            if yr is None:
                continue
            if iid == "ind_pop_estimada":
                cobertura_pop[tid].add(int(yr))
            elif iid == "ind_pib_corrente":
                cobertura_pib[tid].add(int(yr))

    # Passo 2: stream → indicators.json compacto
    OUT_IND.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "em": utc_now(),
        "principio": "INDICADOR É OBSERVAÇÃO, NÃO PROPRIEDADE FIXA",
        "disclaimer": (
            "Variação durante um governo não significa variação causada pelo governo."
        ),
        "territories": len(territories),
        "indicators": len(indicators),
        "observations": n_obs,
    }
    with OUT_IND.open("w", encoding="utf-8") as out:
        out.write('{"meta":')
        json.dump(meta, out, ensure_ascii=False, separators=(",", ":"))
        out.write(',"territories":')
        json.dump(territories, out, ensure_ascii=False, separators=(",", ":"))
        out.write(',"indicators":')
        json.dump(indicators, out, ensure_ascii=False, separators=(",", ":"))
        out.write(',"observations":[')
        first = True
        with obs_path.open(encoding="utf-8") as inp:
            for line in inp:
                line = line.strip()
                if not line:
                    continue
                if not first:
                    out.write(",")
                first = False
                out.write(line)
        out.write("]}")
    gc.collect()
    print(f"OK indicators.json: obs={n_obs} → {OUT_IND.name}")

    if not GOLD.exists():
        print("gold KB ausente — só indicators.json gravado", file=sys.stderr)
        return 0

    with GOLD.open(encoding="utf-8") as f:
        kb = json.load(f)
    ents = {e["id"]: e for e in kb.get("entidades") or []}

    for t in territories:
        if t.get("territory_type") != "STATE":
            continue
        tid = t["territory_id"]
        if tid not in ents:
            ents[tid] = {
                "id": tid,
                "tipo": "estado",
                "nome": t.get("name"),
                "uf": t.get("state_code"),
                "tags": ["coletado", "uf", "ibge", "indicadores"],
                "source_ids": [f"ibge_uf:{t.get('ibge_code')}"],
            }
        e = ents[tid]
        e["ibge_code"] = t.get("ibge_code")
        e["region_code"] = t.get("region_code")
        e["region_name"] = t.get("region_name")
        tags = list(e.get("tags") or [])
        for x in ("ibge", "indicadores"):
            if x not in tags:
                tags.append(x)
        e["tags"] = tags
        anos_pop = sorted(cobertura_pop.get(tid) or [])
        anos_pib = sorted(cobertura_pib.get(tid) or [])
        e["indicadores_cobertura"] = {
            "ind_pop_estimada": {
                "anos": anos_pop,
                "fonte": "ibge.sidra_6579",
            }
            if anos_pop
            else None,
            "ind_pib_corrente": {
                "anos": anos_pib,
                "fonte": "ibge.sidra_5938",
                "nivel": "STATE",
            }
            if anos_pib
            else None,
        }

    for t in territories:
        if t.get("territory_type") != "REGION":
            continue
        tid = t["territory_id"]
        if tid not in ents:
            ents[tid] = {
                "id": tid,
                "tipo": "regiao",
                "nome": t.get("name"),
                "region_code": t.get("region_code"),
                "ibge_code": t.get("ibge_code"),
                "tags": ["coletado", "ibge", "indicadores"],
                "source_ids": [f"ibge_reg:{t.get('ibge_code')}"],
            }

    if "terr_br" not in ents:
        ents["terr_br"] = {
            "id": "terr_br",
            "tipo": "pais",
            "nome": "Brasil",
            "tags": ["coletado", "ibge", "indicadores"],
            "source_ids": ["ibge:brasil"],
        }

    kb["entidades"] = list(ents.values())
    kb.setdefault("meta", {})["indicadores"] = {
        "em": utc_now(),
        "arquivo": str(OUT_IND.name),
        "observations": n_obs,
        "indicators": [i["indicator_id"] for i in indicators],
    }
    _write_json_compact(GOLD, kb)
    lake_gold = LAKE / "gold" / "kb.json"
    lake_gold.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(GOLD, lake_gold)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        shutil.copyfile(GOLD, ACTIVE)
        shutil.copyfile(GOLD, V2)
    print("OK gold indicadores: UFs enriquecidas + meta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
