#!/usr/bin/env python3
"""
Silver IDEB — observa IDEB rede pública (UF + município) a partir dos ZIPs INEP.

Etapas: anos_iniciais | anos_finais | ensino_medio
Não mistura redes (usa Pública / Pública (4)).
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402

IDEB_YEARS = [2005, 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2021, 2023, 2025]

# (arquivo, etapa, sheet contains, nivel)
SPECS = [
    (
        "divulgacao_regioes_ufs_ideb_2025.zip",
        "anos_iniciais",
        "AI",
        "STATE",
    ),
    (
        "divulgacao_regioes_ufs_ideb_2025.zip",
        "anos_finais",
        "AF",
        "STATE",
    ),
    (
        "divulgacao_regioes_ufs_ideb_2025.zip",
        "ensino_medio",
        "EM",
        "STATE",
    ),
    (
        "divulgacao_anos_iniciais_municipios_2025.zip",
        "anos_iniciais",
        "AI",
        "MUNICIPALITY",
    ),
    (
        "divulgacao_anos_finais_municipios_2025.zip",
        "anos_finais",
        "AF",
        "MUNICIPALITY",
    ),
    (
        "divulgacao_ensino_medio_municipios_2025.zip",
        "ensino_medio",
        "EM",
        "MUNICIPALITY",
    ),
]

INDICATOR_DEFS = [
    {
        "indicator_id": "ind_ideb_anos_iniciais",
        "name": "ideb_anos_iniciais_rede_publica",
        "display_name": "IDEB — anos iniciais (rede pública)",
        "description": "IDEB anos iniciais do EF, rede pública. Escala 0–10 (INEP).",
        "category": "educacao",
        "subcategory": "ideb_anos_iniciais",
        "unit": "indice_0_10",
        "higher_is_better": True,
        "neutral_direction": False,
        "aggregation_method": "avg",
        "source_id": "inep",
        "dataset_id": "inep.ideb",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "biennial",
        "methodology_url": "https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb",
        "notes": "Rede pública apenas. Observação temporal — não é propriedade fixa.",
    },
    {
        "indicator_id": "ind_ideb_anos_finais",
        "name": "ideb_anos_finais_rede_publica",
        "display_name": "IDEB — anos finais (rede pública)",
        "description": "IDEB anos finais do EF, rede pública. Escala 0–10 (INEP).",
        "category": "educacao",
        "subcategory": "ideb_anos_finais",
        "unit": "indice_0_10",
        "higher_is_better": True,
        "source_id": "inep",
        "dataset_id": "inep.ideb",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "biennial",
        "methodology_url": "https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb",
    },
    {
        "indicator_id": "ind_ideb_ensino_medio",
        "name": "ideb_ensino_medio_rede_publica",
        "display_name": "IDEB — ensino médio (rede pública)",
        "description": "IDEB ensino médio, rede pública. Escala 0–10 (INEP).",
        "category": "educacao",
        "subcategory": "ideb_ensino_medio",
        "unit": "indice_0_10",
        "higher_is_better": True,
        "source_id": "inep",
        "dataset_id": "inep.ideb",
        "minimum_geographic_level": "MUNICIPALITY",
        "frequency": "biennial",
        "methodology_url": "https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb",
    },
]

ETAPA_TO_IND = {
    "anos_iniciais": "ind_ideb_anos_iniciais",
    "anos_finais": "ind_ideb_anos_finais",
    "ensino_medio": "ind_ideb_ensino_medio",
}

ETAPA_SHORT = {
    "anos_iniciais": "ai",
    "anos_finais": "af",
    "ensino_medio": "em",
}


def latest_bronze_dir() -> Path | None:
    base = LAKE / "bronze" / "inep"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    return days[0] if days else None


def parse_ideb_val(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", ".")
    if s in ("", "-", "...", "ND", "na", "NA"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def find_ideb_cols(header_row: list) -> list[tuple[int, int]]:
    """Retorna [(col_idx, year), ...] a partir da linha de cabeçalho IDEB."""
    out: list[tuple[int, int]] = []
    for j, c in enumerate(header_row or []):
        if not c:
            continue
        t = str(c).upper().replace("\n", " ")
        if "IDEB" not in t:
            continue
        m = re.search(r"(20\d{2})", t)
        if not m:
            continue
        y = int(m.group(1))
        if y == 20215 or y == 20212:  # typos nas planilhas
            y = 2021
        if y in IDEB_YEARS:
            out.append((j, y))
    # fallback posicional se cabeçalho falhar
    if len(out) < 5:
        return []
    return out


def name_to_uf(nome: str, by_name: dict[str, str]) -> str | None:
    n = (nome or "").strip()
    if n in by_name:
        return by_name[n]
    # normalizar
    return by_name.get(n.replace("  ", " "))


def load_uf_name_map(territories: list[dict]) -> dict[str, str]:
    m: dict[str, str] = {}
    for t in territories:
        if t.get("territory_type") != "STATE":
            continue
        if t.get("name") and t.get("state_code"):
            m[str(t["name"])] = str(t["state_code"]).upper()
    return m


def pick_sheet(wb, needle: str, nivel: str):
    for name in wb.sheetnames:
        up = name.upper()
        if needle in up:
            return wb[name]
        if nivel == "MUNICIPALITY" and "MUNIC" in up:
            return wb[name]
    return wb[wb.sheetnames[0]]


def parse_zip(
    zip_path: Path,
    etapa: str,
    needle: str,
    nivel: str,
    by_uf_name: dict[str, str],
    now: str,
) -> list[dict]:
    ind_id = ETAPA_TO_IND[etapa]
    obs: list[dict] = []
    with zipfile.ZipFile(zip_path) as zf:
        xlsx = next(n for n in zf.namelist() if n.lower().endswith(".xlsx"))
        wb = openpyxl.load_workbook(zf.open(xlsx), read_only=True, data_only=True)
        ws = pick_sheet(wb, needle, nivel)
        header_row = None
        ideb_cols: list[tuple[int, int]] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            cells = list(row)
            if i < 15:
                cols = find_ideb_cols(cells)
                # EM tem ~5 anos (2017–2025); AI/AF têm ~11
                if len(cols) >= 5:
                    header_row = cells
                    ideb_cols = cols
                    continue
            if not ideb_cols or not cells:
                continue
            if nivel == "STATE":
                nome = cells[0]
                rede = str(cells[1] or "")
                if not nome or not isinstance(nome, str):
                    continue
                # AI/AF: INEP publica "Pública (4)". EM UF: só há "Estadual" (sem linha Pública).
                if etapa == "ensino_medio":
                    if rede.strip() != "Estadual":
                        continue
                    rede_tag = "estadual"
                else:
                    if "Pública (4)" not in rede and rede.strip() != "Pública":
                        continue
                    rede_tag = "publica"
                uf = name_to_uf(nome, by_uf_name)
                if not uf:
                    continue
                tid = f"uf_{uf}"
                short = ETAPA_SHORT[etapa]
                for col, year in ideb_cols:
                    val = parse_ideb_val(cells[col] if col < len(cells) else None)
                    if val is None:
                        continue
                    obs.append(
                        {
                            "observation_id": f"obs_ideb_{short}_{uf}_{year}",
                            "indicator_id": ind_id,
                            "territory_id": tid,
                            "reference_year": year,
                            "period_start": f"{year}-01-01",
                            "period_end": f"{year}-12-31",
                            "value": val,
                            "unit": "indice_0_10",
                            "rede": rede_tag,
                            "etapa": etapa,
                            "source_id": "inep",
                            "dataset_id": "inep.ideb",
                            "coverage_status": "ok",
                            "confidence": "official",
                            "retrieved_at": now,
                            "fonte_url": (
                                "https://www.gov.br/inep/pt-br/areas-de-atuacao/"
                                "pesquisas-estatisticas-e-indicadores/ideb/resultados/2005-2025"
                            ),
                            "geographic_level": "STATE",
                            "notes": (
                                "UF EM: rede Estadual (INEP não publica Pública nesta planilha)."
                                if etapa == "ensino_medio"
                                else None
                            ),
                        }
                    )
            else:
                uf = str(cells[0] or "").upper()[:2]
                code = str(cells[1] or "").replace(".0", "").strip()
                rede = str(cells[3] or "")
                if not code.isdigit() or len(code) < 6:
                    continue
                if rede.strip() != "Pública":
                    continue
                tid = f"mun_{code}"
                short = ETAPA_SHORT[etapa]
                for col, year in ideb_cols:
                    val = parse_ideb_val(cells[col] if col < len(cells) else None)
                    if val is None:
                        continue
                    obs.append(
                        {
                            "observation_id": f"obs_ideb_{short}_mun_{code}_{year}",
                            "indicator_id": ind_id,
                            "territory_id": tid,
                            "reference_year": year,
                            "period_start": f"{year}-01-01",
                            "period_end": f"{year}-12-31",
                            "value": val,
                            "unit": "indice_0_10",
                            "rede": "publica",
                            "etapa": etapa,
                            "uf": uf or None,
                            "source_id": "inep",
                            "dataset_id": "inep.ideb",
                            "coverage_status": "ok",
                            "confidence": "official",
                            "retrieved_at": now,
                            "fonte_url": (
                                "https://www.gov.br/inep/pt-br/areas-de-atuacao/"
                                "pesquisas-estatisticas-e-indicadores/ideb/resultados/2005-2025"
                            ),
                            "geographic_level": "MUNICIPALITY",
                        }
                    )
        wb.close()
    return obs


def main() -> int:
    bronze = latest_bronze_dir()
    if not bronze:
        print("bronze inep ausente — rode ingest/inep_ideb.py", file=sys.stderr)
        return 1

    sil = LAKE / "silver" / "indicadores"
    terr_path = sil / "territories_latest.json"
    ind_path = sil / "indicators_latest.json"
    obs_path = sil / "observations_latest.jsonl"
    if not terr_path.exists() or not obs_path.exists():
        print("silver indicadores base ausente — rode silver_indicadores.py", file=sys.stderr)
        return 1

    territories = json.loads(terr_path.read_text(encoding="utf-8"))
    indicators = json.loads(ind_path.read_text(encoding="utf-8")) if ind_path.exists() else []
    observations = [
        json.loads(l)
        for l in obs_path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]

    # remove IDEB anterior
    observations = [o for o in observations if not str(o.get("indicator_id", "")).startswith("ind_ideb_")]
    indicators = [i for i in indicators if not str(i.get("indicator_id", "")).startswith("ind_ideb_")]
    indicators.extend(INDICATOR_DEFS)

    by_uf = load_uf_name_map(territories)
    now = utc_now()
    new_obs: list[dict] = []
    for fname, etapa, needle, nivel in SPECS:
        zp = bronze / fname
        if not zp.exists():
            print(f"  skip ausente {fname}", flush=True)
            continue
        print(f"  parse {fname} · {etapa} · {nivel} …", flush=True)
        chunk = parse_zip(zp, etapa, needle, nivel, by_uf, now)
        print(f"    +{len(chunk)} obs", flush=True)
        new_obs.extend(chunk)

    observations.extend(new_obs)
    stamp = day_stamp()
    write_json(sil / f"indicators_{stamp}.json", indicators)
    write_json(sil / "indicators_latest.json", indicators)
    write_jsonl(sil / f"observations_{stamp}.jsonl", observations)
    write_jsonl(sil / "observations_latest.jsonl", observations)
    write_json(
        sil / "meta_ideb.json",
        {
            "em": now,
            "ideb_observations": len(new_obs),
            "total_observations": len(observations),
            "indicators_ideb": [i["indicator_id"] for i in INDICATOR_DEFS],
        },
    )
    print(f"OK silver IDEB: +{len(new_obs)} obs · total={len(observations)}")
    return 0 if new_obs else 1


if __name__ == "__main__":
    raise SystemExit(main())
