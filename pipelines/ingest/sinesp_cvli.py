#!/usr/bin/env python3
"""
Ingest criminalidade policial / CVLI — Sinesp (se público) OU IPEA Atlas da Violência.

SECURITY_DATA_COVERAGE:
  Sinesp API frequentemente fechada/instável. Preferimos séries Ipeadata / arquivo
  manual (ATLAS_CVLI_FILE / ATLAS_SINESP_FILE) com taxa CVLI ou homicídios por 100 mil.
  NÃO misturar com Fogo Cruzado (colaborativo) nem com mortalidade SIM (CID).

Ordem:
  1) ATLAS_CVLI_FILE / ATLAS_SINESP_FILE
  2) Ipeadata OData — séries com 'homicídio' / 'CVLI' em nível UF/mun se existirem
  3) SKIPPED exit 0 com mensagem clara

Bronze: sinesp_cvli_extract.jsonl
Indicador: ind_cvli_per_100k
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, throttle, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

UA = os.getenv("ATLAS_USER_AGENT", "ATLAS-BRASIL-Ingestor/5.1 (+pesquisa CVLI/IPEA)")
IPEA = "http://www.ipeadata.gov.br/api/odata4"

UF_CODE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}

# códigos conhecidos (Atlas da Violência / Ipeadata)
CANDIDATE_SERIES = [
    "AVIOL12_THOMIC",  # Taxa de homicídios (100.000 hab.) — níveis Brasil/UF/mun
]


def _norm(s: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", s or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", t.lower())


def parse_local(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    delim = ";" if text[:4096].count(";") >= text[:4096].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    if not reader.fieldnames:
        return []
    fields = list(reader.fieldnames)
    norms = {_norm(f): f for f in fields}

    def pick(*aliases):
        for a in aliases:
            na = _norm(a)
            if na in norms:
                return norms[na]
            for nk, orig in norms.items():
                if na and len(na) >= 4 and na in nk:
                    return orig
        return None

    col_ibge = pick("cod_ibge", "ibge", "codigo")
    col_uf = pick("uf", "sg_uf", "sigla")
    col_ano = pick("ano", "year", "nu_ano")
    col_taxa = pick("cvli_per_100k", "taxa_cvli", "taxa", "homicidios_100k", "tx_homicidio", "valor")
    now = utc_now()
    out = []
    for row in reader:
        if not col_taxa:
            break
        try:
            val = float(str(row.get(col_taxa) or "").replace(",", "."))
        except ValueError:
            continue
        year = 0
        if col_ano and row.get(col_ano):
            ys = re.sub(r"\D", "", str(row[col_ano]))[:4]
            if ys.isdigit():
                year = int(ys)
        if not year:
            continue
        code = re.sub(r"\D", "", str(row.get(col_ibge) or "")) if col_ibge else ""
        uf = str(row.get(col_uf) or "").upper()[:2] if col_uf else ""
        if len(code) >= 6:
            code = code[:7] if len(code) >= 7 else code[:6]
            nivel, tid = "MUNICIPALITY", f"mun_{code}"
        elif uf:
            nivel, tid, code = "STATE", f"uf_{uf}", uf
        else:
            continue
        out.append(
            {
                "nivel": nivel,
                "territory_id": tid,
                "cod_ibge": code,
                "uf": uf,
                "ano": year,
                "cvli_per_100k": val,
                "retrieved_at": now,
                "fonte": "ATLAS_CVLI_FILE",
            }
        )
    return out


def discover_ipea_series() -> list[str]:
    env = os.getenv("ATLAS_IPEA_CVLI_SERIES", "")
    if env.strip():
        return [s.strip() for s in env.split(",") if s.strip()]
    # discovery completa é pesada — só se ATLAS_IPEA_DISCOVER=1; senão usa candidatos
    if os.getenv("ATLAS_IPEA_DISCOVER", "").strip().lower() not in ("1", "true", "yes"):
        return list(CANDIDATE_SERIES)
    throttle()
    try:
        r = httpx.get(
            f"{IPEA}/Metadados",
            headers={"User-Agent": UA},
            timeout=120.0,
            follow_redirects=True,
        )
        r.raise_for_status()
        vals = r.json().get("value") or []
    except Exception as e:
        print(f"  ipea metadados falhou: {e}", file=sys.stderr)
        return list(CANDIDATE_SERIES)
    codes = []
    for v in vals:
        nome = _norm(v.get("SERNOME") or "")
        if "homicidio" not in nome and "cvli" not in nome:
            continue
        if "taxa" not in nome and "100" not in nome and "mil" not in nome:
            if "homicidio" not in nome:
                continue
        code = v.get("SERCODIGO")
        if code:
            codes.append(code)
        if len(codes) >= 8:
            break
    return codes or list(CANDIDATE_SERIES)


def fetch_serie(code: str) -> list[dict]:
    throttle()
    url = f"{IPEA}/ValoresSerie(SERCODIGO='{code}')"
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=180.0, follow_redirects=True)
    r.raise_for_status()
    return r.json().get("value") or []


def ipea_to_rows(series: list[str]) -> list[dict]:
    now = utc_now()
    out = []
    for code in series:
        print(f"  Ipeadata {code} …", flush=True)
        try:
            vals = fetch_serie(code)
        except Exception as e:
            print(f"  fail {code}: {e}", file=sys.stderr)
            continue
        for v in vals:
            year = int(str(v.get("VALDATA") or "")[:4] or 0)
            if year < 1990 or year > 2035:
                continue
            ter = str(v.get("TERCODIGO") or "").strip()
            niv = (v.get("NIVNOME") or "").lower()
            val = v.get("VALVALOR")
            if val is None:
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if "munic" in niv or (len(ter) >= 6 and "estado" not in niv):
                if os.getenv("ATLAS_CVLI_STATE_ONLY", "1").strip().lower() in ("1", "true", "yes"):
                    continue  # P3: só UF por padrão
                nivel = "MUNICIPALITY"
                cod = ter[:7] if len(ter) >= 7 else ter
                tid = f"mun_{cod}"
                uf = UF_CODE.get(cod[:2], "")
            elif "estado" in niv or len(ter) == 2:
                uf = UF_CODE.get(ter.zfill(2), "")
                if not uf:
                    continue
                nivel, tid, cod = "STATE", f"uf_{uf}", uf
            else:
                continue
            out.append(
                {
                    "nivel": nivel,
                    "territory_id": tid,
                    "cod_ibge": cod,
                    "uf": uf,
                    "ano": year,
                    "cvli_per_100k": num,
                    "retrieved_at": now,
                    "fonte": f"ipeadata:{code}",
                    "serie": code,
                }
            )
    return out


def main() -> int:
    run = start_run("sinesp_cvli", "sinesp.cvli_per_100k")
    out = bronze_dir("sinesp_cvli")
    rows: list[dict] = []
    messages: list[str] = [
        "SECURITY_DATA_COVERAGE: complementary police/IPEA rates; not Fogo Cruzado; not SIM CID mortality."
    ]

    local = os.getenv("ATLAS_CVLI_FILE") or os.getenv("ATLAS_SINESP_FILE")
    if local:
        p = Path(local)
        if p.is_file():
            rows = parse_local(p)
            messages.append(f"local rows={len(rows)}")
        else:
            messages.append(f"arquivo ausente: {local}")

    if not rows:
        # Sinesp API pública tipicamente indisponível
        messages.append("Sinesp API pública não utilizada (acesso fechado/instável).")
        try:
            series = discover_ipea_series()
            messages.append(f"ipea series={series}")
            if series:
                rows = ipea_to_rows(series)
                messages.append(f"ipea rows={len(rows)}")
            else:
                messages.append("nenhuma série IPEA candidata")
        except Exception as e:
            messages.append(f"ipea falhou: {e}")

    if rows:
        write_jsonl(out / "sinesp_cvli_extract.jsonl", rows)
    else:
        messages.append(
            "SKIPPED sinesp_cvli: sem Sinesp público nem série IPEA/arquivo. "
            "Defina ATLAS_CVLI_FILE=caminho.csv (uf/ibge, ano, taxa por 100k)."
        )
        print(messages[-1], flush=True)

    write_json(
        out / "sinesp_cvli_meta.json",
        {
            "em": utc_now(),
            "fonte": "sinesp_cvli",
            "rows": len(rows),
            "messages": messages,
            "ingestion_run_id": run["ingestion_run_id"],
            "day": day_stamp(),
            "SECURITY_DATA_COVERAGE": messages[0],
            "portal_ipea": "https://www.ipea.gov.br/atlasviolencia/",
        },
    )
    mark_ingested(
        "sinesp_cvli",
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        ok=len(rows) > 0,
        error=None if rows else messages[-1],
        dataset_id="sinesp.cvli_per_100k",
    )
    print(f"OK CVLI/Sinesp-IPEA: rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
