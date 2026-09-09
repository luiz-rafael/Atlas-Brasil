#!/usr/bin/env python3
"""
Ingest Fogo Cruzado via pacote `crossfire` (API colaborativa).

SECURITY_DATA_COVERAGE / POLICE_OCCURRENCE_DATA:
  Fonte COMPLEMENTAR colaborativa (tiros em RM RJ/PE e expansões BA/PA).
  NÃO é Sinesp nacional; NÃO substitui mortalidade por homicídio do SIM.
  Manter indicadores separados de ind_homicidios_* / CVLI policial.

Requer: FOGOCRUZADO_EMAIL + FOGOCRUZADO_PASSWORD (ou CROSSFIRE_*).
Sem credenciais → SKIPPED exit 0 (fail-soft).

Bronze: fogo_cruzado_extract.jsonl (contagens anuais por município IBGE).
"""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

# Cobertura histórica principal do projeto (API também pode trazer BA/PA).
FOCUS_UF = {"RJ", "PE"}


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFKD", s or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(t.lower().split())


def load_city_ibge_map() -> dict[tuple[str, str], str]:
    """(uf_sigla, nome_norm) → cod IBGE 7 dígitos."""
    sil = ROOT / "data" / "lake" / "silver" / "indicadores" / "territories_latest.json"
    if not sil.exists():
        # fallback bronze IBGE
        base = ROOT / "data" / "lake" / "bronze" / "ibge"
        if not base.exists():
            return {}
        days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
        mun_path = None
        est_path = None
        for d in days:
            if (d / "municipios.json").exists() and (d / "estados.json").exists():
                mun_path, est_path = d / "municipios.json", d / "estados.json"
                break
        if not mun_path:
            return {}
        estados = {str(e["id"]): e.get("sigla", "").upper() for e in json.loads(est_path.read_text(encoding="utf-8"))}
        m: dict[tuple[str, str], str] = {}
        for mun in json.loads(mun_path.read_text(encoding="utf-8")):
            mid = str(mun.get("id") or "")
            nome = _norm(mun.get("nome") or "")
            # UF via microrregiao
            micro = mun.get("microrregiao") or {}
            meso = micro.get("mesorregiao") or {}
            uf_obj = meso.get("UF") or {}
            uf = (uf_obj.get("sigla") or estados.get(str(uf_obj.get("id") or ""), "")).upper()
            if mid and nome and uf:
                m[(uf, nome)] = mid
        return m

    territories = json.loads(sil.read_text(encoding="utf-8"))
    m: dict[tuple[str, str], str] = {}
    for t in territories:
        if t.get("territory_type") != "MUNICIPALITY":
            continue
        code = str(t.get("ibge_code") or "").strip()
        name = _norm(t.get("name") or t.get("nome") or "")
        uf = str(t.get("state_code") or t.get("uf") or "").upper()[:2]
        if len(code) >= 6 and name and uf:
            m[(uf, name)] = code[:7] if len(code) >= 7 else code
    return m


def victim_count(occ: dict) -> int:
    v = occ.get("victims") or occ.get("Victims") or []
    if isinstance(v, list):
        return len(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def city_name_from_occ(occ: dict) -> str:
    for key in ("city", "city_name", "cidade", "City"):
        val = occ.get(key)
        if isinstance(val, dict):
            return str(val.get("name") or val.get("nome") or "")
        if val:
            return str(val)
    return ""


def uf_from_state(state_obj) -> str:
    if isinstance(state_obj, dict):
        return str(state_obj.get("name") or state_obj.get("nome") or state_obj.get("uf") or "").upper()[:2]
    return str(state_obj or "").upper()[:2]


def main() -> int:
    email = os.getenv("FOGOCRUZADO_EMAIL") or os.getenv("CROSSFIRE_EMAIL")
    password = os.getenv("FOGOCRUZADO_PASSWORD") or os.getenv("CROSSFIRE_PASSWORD")
    if not email or not password:
        msg = (
            "SKIPPED fogo_cruzado: defina FOGOCRUZADO_EMAIL e FOGOCRUZADO_PASSWORD "
            "(cadastro em https://api.fogocruzado.org.br/). "
            "Fonte complementar colaborativa — não é Sinesp."
        )
        print(msg, flush=True)
        return 0

    # crossfire lê credenciais do ambiente
    os.environ.setdefault("FOGOCRUZADO_EMAIL", email)
    os.environ.setdefault("FOGOCRUZADO_PASSWORD", password)

    try:
        from crossfire import occurrences, states
    except ImportError:
        print(
            "SKIPPED fogo_cruzado: pacote ausente — pip install crossfire",
            flush=True,
        )
        return 0

    run = start_run("fogocruzado", "fogocruzado.tiros_vitimas")
    out = bronze_dir("fogo_cruzado")
    city_map = load_city_ibge_map()
    print(f"  city_map={len(city_map)}", flush=True)

    try:
        st_list = states(format="dict")
    except Exception as e:
        print(f"SKIPPED fogo_cruzado: states() falhou: {e}", flush=True)
        mark_ingested(
            "fogocruzado",
            run_id=run["ingestion_run_id"],
            counts={"rows": 0},
            ok=False,
            error=str(e),
            dataset_id="fogocruzado.tiros_vitimas",
        )
        return 0

    # normaliza lista de estados
    if isinstance(st_list, dict):
        st_list = st_list.get("data") or st_list.get("states") or [st_list]
    if not isinstance(st_list, list):
        st_list = list(st_list) if st_list is not None else []

    # agrega (cod_ibge|uf, year) → tiros, vitimas
    agg: dict[tuple[str, str, int], dict] = defaultdict(
        lambda: {"tiros": 0, "vitimas": 0}
    )
    messages: list[str] = []
    now = utc_now()

    for st in st_list:
        if not isinstance(st, dict):
            continue
        sid = st.get("id") or st.get("state_id")
        sname = str(st.get("name") or st.get("nome") or "")
        # mapeia nome longo → sigla
        uf = sname.upper()[:2] if len(sname) == 2 else ""
        name_l = _norm(sname)
        if "rio de janeiro" in name_l or name_l == "rj":
            uf = "RJ"
        elif "pernambuco" in name_l or name_l == "pe":
            uf = "PE"
        elif "bahia" in name_l or name_l == "ba":
            uf = "BA"
        elif "para" == name_l or "pará" in _norm(sname) or name_l == "pa":
            uf = "PA"
        if not sid:
            continue
        # padrão: só RJ/PE; ATLAS_FOGO_ALL_STATES=1 inclui BA/PA e demais
        if os.getenv("ATLAS_FOGO_ALL_STATES", "").strip().lower() not in ("1", "true", "yes"):
            if uf and uf not in FOCUS_UF:
                continue
        print(f"  ocorrências {uf or sname} …", flush=True)
        try:
            data = occurrences(id_state=sid, format="dict", type_occurrence="all")
        except TypeError:
            try:
                data = occurrences(sid, format="dict")
            except Exception as e:
                messages.append(f"{uf}: {e}")
                print(f"  fail {uf}: {e}", file=sys.stderr)
                continue
        except Exception as e:
            messages.append(f"{uf}: {e}")
            print(f"  fail {uf}: {e}", file=sys.stderr)
            continue

        if isinstance(data, dict):
            rows = data.get("data") or data.get("occurrences") or []
        else:
            rows = list(data) if data is not None else []

        for occ in rows:
            if not isinstance(occ, dict):
                continue
            # data
            date_s = str(
                occ.get("date")
                or occ.get("occurrenceDate")
                or occ.get("dateOccurrence")
                or occ.get("created_at")
                or ""
            )
            year = int(date_s[:4]) if date_s[:4].isdigit() else 0
            if not year:
                continue
            cname = city_name_from_occ(occ)
            uf_occ = uf or uf_from_state(occ.get("state") or occ.get("State"))
            uf_key = (uf_occ or "").upper()[:2]
            code = city_map.get((uf_key, _norm(cname))) if uf_key and cname else None
            tid_key = code or f"nome:{uf_key}:{_norm(cname)}"
            key = (tid_key, uf_key, year)
            agg[key]["tiros"] += 1
            agg[key]["vitimas"] += victim_count(occ)

    extract: list[dict] = []
    for (cod, uf, year), m in agg.items():
        is_ibge = cod.isdigit() or (len(cod) >= 6 and cod[:6].isdigit())
        extract.append(
            {
                "cod_ibge": cod if is_ibge else None,
                "city_key": None if is_ibge else cod,
                "uf": uf,
                "ano": year,
                "tiros": m["tiros"],
                "vitimas": m["vitimas"],
                "territory_id": f"mun_{cod}" if is_ibge else None,
                "retrieved_at": now,
                "fonte": "fogocruzado_crossfire",
                "coverage_note": "POLICE_OCCURRENCE_DATA complementary collaborative; not national Sinesp",
            }
        )

    write_jsonl(out / "fogo_cruzado_extract.jsonl", extract)
    write_json(
        out / "fogo_cruzado_meta.json",
        {
            "em": now,
            "fonte": "fogocruzado",
            "rows": len(extract),
            "messages": messages,
            "focus_uf": sorted(FOCUS_UF),
            "city_map_size": len(city_map),
            "ingestion_run_id": run["ingestion_run_id"],
            "day": day_stamp(),
            "SECURITY_DATA_COVERAGE": (
                "Complementary collaborative gunfire occurrences (Fogo Cruzado). "
                "Not police CVLI/Sinesp; keep separate from SIM homicide mortality."
            ),
        },
    )
    mark_ingested(
        "fogocruzado",
        run_id=run["ingestion_run_id"],
        counts={"rows": len(extract)},
        ok=len(extract) > 0,
        dataset_id="fogocruzado.tiros_vitimas",
    )
    print(f"OK Fogo Cruzado: rows={len(extract)} -> {out}")
    return 0 if extract else 0  # fail-soft: API vazia não quebra lote


if __name__ == "__main__":
    raise SystemExit(main())
