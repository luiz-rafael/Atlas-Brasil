#!/usr/bin/env python3
"""
Ingest IDHM (Atlas do Desenvolvimento Humano / Ipeadata ADH).

Ordem:
  1) ATLAS_IDHM_FILE (csv/xlsx local)
  2) Ipeadata OData: ADH_IDHM, ADH_IDHM_E, ADH_IDHM_L, ADH_IDHM_R
  3) Espelho github (dados2010.csv) se API falhar

Anos censo: 1991, 2000, 2010.
Bronze: idhm_extract.jsonl
"""

from __future__ import annotations

import csv
import io
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, throttle, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

IPEA = "http://www.ipeadata.gov.br/api/odata4"
SERIES = {
    "idhm": "ADH_IDHM",
    "idhm_educacao": "ADH_IDHM_E",
    "idhm_longevidade": "ADH_IDHM_L",
    "idhm_renda": "ADH_IDHM_R",
}

UF_CODE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}

GITHUB_MIRROR = (
    "https://raw.githubusercontent.com/miromachado/nasa-hackathon/master/dados2010.csv"
)

UA = os.getenv("ATLAS_USER_AGENT", "ATLAS-BRASIL-Ingestor/5.1 (+pesquisa IDHM)")


def fetch_serie(code: str) -> list[dict]:
    throttle()
    url = f"{IPEA}/ValoresSerie(SERCODIGO='{code}')"
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=180.0, follow_redirects=True)
    r.raise_for_status()
    return r.json().get("value") or []


def ipea_to_rows() -> list[dict]:
    # key: (nivel, territory, year) -> metrics
    bucket: dict[tuple, dict] = {}
    now = utc_now()
    for metric, code in SERIES.items():
        print(f"  Ipeadata {code} …", flush=True)
        vals = fetch_serie(code)
        for v in vals:
            year = int(str(v.get("VALDATA") or "")[:4] or 0)
            if year not in (1991, 2000, 2010):
                # radar/outros anos se API trouxer
                if year < 1990 or year > 2030:
                    continue
            ter = str(v.get("TERCODIGO") or "").strip()
            niv = (v.get("NIVNOME") or "").lower()
            val = v.get("VALVALOR")
            if val is None:
                continue
            if "munic" in niv or len(ter) >= 6:
                nivel = "MUNICIPALITY"
                cod = ter[:7] if len(ter) >= 7 else ter
                tid = f"mun_{cod}"
                uf = UF_CODE.get(cod[:2], "")
            elif "estado" in niv or len(ter) == 2:
                nivel = "STATE"
                uf = UF_CODE.get(ter.zfill(2), "")
                if not uf:
                    continue
                cod = uf
                tid = f"uf_{uf}"
            else:
                continue
            key = (nivel, tid, year)
            rec = bucket.setdefault(
                key,
                {
                    "nivel": nivel,
                    "territory_id": tid,
                    "cod_ibge": cod,
                    "uf": uf,
                    "ano": year,
                    "retrieved_at": now,
                    "fonte": "ipeadata_adh",
                },
            )
            rec[metric] = float(val)
    return list(bucket.values())


def parse_github_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    now = utc_now()
    rows = []
    for row in reader:
        keys = {k.lower(): k for k in row}
        code = str(row.get(keys.get("cod7") or keys.get("cod_ibge") or keys.get("codigo") or "") or "")
        code = "".join(ch for ch in code if ch.isdigit())
        if len(code) < 6:
            continue
        code = code[:7] if len(code) >= 7 else code
        uf = str(row.get(keys.get("uf") or "") or UF_CODE.get(code[:2], "")).upper()[:2]

        def g(*names):
            for n in names:
                k = keys.get(n)
                if k and row.get(k) not in (None, ""):
                    try:
                        return float(str(row[k]).replace(",", "."))
                    except ValueError:
                        return None
            return None

        rows.append(
            {
                "nivel": "MUNICIPALITY",
                "territory_id": f"mun_{code}",
                "cod_ibge": code,
                "uf": uf,
                "ano": 2010,
                "idhm": g("idhm"),
                "idhm_educacao": g("idhm_edu", "idhm_educacao", "idhm_e"),
                "idhm_longevidade": g("idhm_longev", "idhm_longevidade", "idhm_l"),
                "idhm_renda": g("idhm_renda", "idhm_r"),
                "retrieved_at": now,
                "fonte": "github_mirror_2010",
            }
        )
    return [r for r in rows if r.get("idhm") is not None]


def parse_local(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".csv":
        # tenta schema github ou genérico
        rows = parse_github_csv(text)
        if rows:
            for r in rows:
                r["fonte"] = "ATLAS_IDHM_FILE"
            return rows
        reader = csv.DictReader(io.StringIO(text))
        now = utc_now()
        out = []
        for row in reader:
            keys = {k.lower(): k for k in row}
            code = str(row.get(keys.get("cod_ibge") or keys.get("codigo") or "") or "")
            code = "".join(ch for ch in code if ch.isdigit())
            try:
                ano = int(float(row.get(keys.get("ano") or keys.get("year") or 2010)))
            except ValueError:
                continue
            if len(code) >= 6:
                nivel, tid = "MUNICIPALITY", f"mun_{code[:7]}"
                uf = UF_CODE.get(code[:2], "")
            else:
                uf = str(row.get(keys.get("uf") or "") or "").upper()[:2]
                if not uf:
                    continue
                nivel, tid, code = "STATE", f"uf_{uf}", uf
            def gf(n):
                k = keys.get(n)
                if not k:
                    return None
                try:
                    return float(str(row[k]).replace(",", "."))
                except ValueError:
                    return None
            out.append(
                {
                    "nivel": nivel,
                    "territory_id": tid,
                    "cod_ibge": code,
                    "uf": uf,
                    "ano": ano,
                    "idhm": gf("idhm"),
                    "idhm_educacao": gf("idhm_educacao") or gf("idhm_edu"),
                    "idhm_longevidade": gf("idhm_longevidade") or gf("idhm_longev"),
                    "idhm_renda": gf("idhm_renda"),
                    "retrieved_at": now,
                    "fonte": "ATLAS_IDHM_FILE",
                }
            )
        return out
    return []


def main() -> int:
    run = start_run("idhm_atlas", "idhm.atlas_censo")
    out = bronze_dir("idhm_atlas")
    messages: list[str] = []
    rows: list[dict] = []

    local = os.getenv("ATLAS_IDHM_FILE")
    if local:
        p = Path(local)
        if p.is_file():
            rows = parse_local(p)
            messages.append(f"local rows={len(rows)}")
        else:
            messages.append(f"ATLAS_IDHM_FILE ausente: {local}")

    if not rows:
        try:
            rows = ipea_to_rows()
            messages.append(f"ipeadata rows={len(rows)}")
        except Exception as e:
            messages.append(f"ipeadata falhou: {e}")
            print(f"  Ipeadata falhou: {e}", file=sys.stderr)
            try:
                throttle()
                r = httpx.get(GITHUB_MIRROR, headers={"User-Agent": UA}, timeout=120.0)
                r.raise_for_status()
                (out / "dados2010_mirror.csv").write_text(r.text, encoding="utf-8")
                rows = parse_github_csv(r.text)
                messages.append(f"github mirror rows={len(rows)}")
            except Exception as e2:
                messages.append(f"github mirror falhou: {e2}")
                print(f"  Mirror falhou: {e2}", file=sys.stderr)

    extract = out / "idhm_extract.jsonl"
    if rows:
        write_jsonl(extract, rows)

    write_json(
        out / "idhm_meta.json",
        {
            "em": utc_now(),
            "fonte": "idhm_atlas",
            "rows": len(rows),
            "messages": messages,
            "series": SERIES,
            "extract": extract.name if rows else None,
            "ingestion_run_id": run["ingestion_run_id"],
            "day": day_stamp(),
        },
    )
    mark_ingested(
        "idhm_atlas",
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        ok=len(rows) > 0,
        error=None if rows else (messages[-1] if messages else "sem dados"),
        dataset_id="idhm.atlas",
    )
    print(f"OK IDHM: rows={len(rows)} -> {out}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
