#!/usr/bin/env python3
"""
Ingest DATASUS SINAN — notificações (slice dengue nacional DENGBR{YY}.dbc).

FTP: ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/FINAIS/DENGBR{YY}.dbc
Fallback PRELIM. Alternativa: ATLAS_SINAN_FILE (csv/xlsx agregado).

Indicador alvo: casos dengue / agravos notificados (contagem).
Bronze: sinan_extract.jsonl
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from ftplib import FTP, error_perm
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

FTP_HOST = "ftp.datasus.gov.br"
SINAN_DIRS = [
    "/dissemin/publicos/SINAN/DADOS/FINAIS",
    "/dissemin/publicos/SINAN/DADOS/PRELIM",
]

YEARS = list(
    range(
        int(os.getenv("ATLAS_SINAN_YEAR_START", "2019")),
        int(os.getenv("ATLAS_SINAN_YEAR_END", "2023")) + 1,
    )
)

UF_CODE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


def load_mun6_map() -> dict[str, str]:
    sil = ROOT / "data" / "lake" / "silver" / "indicadores" / "territories_latest.json"
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


def ftp_download(ftp: FTP, remote_dir: str, filename: str, dest: Path) -> bool:
    try:
        ftp.cwd(remote_dir)
    except error_perm:
        return False
    names: list[str] = []
    try:
        ftp.retrlines("NLST", names.append)
    except error_perm:
        return False
    lookup = {n.upper(): n for n in names}
    real = lookup.get(filename.upper())
    if not real:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        ftp.retrbinary(f"RETR {real}", f.write)
    return dest.exists() and dest.stat().st_size > 0


def aggregate_dbc(dbc_path: Path, mun6: dict[str, str], year: int) -> list[dict]:
    from dbfread import DBF
    from pyreaddbc import dbc2dbf

    by_uf: dict[str, int] = defaultdict(int)
    by_mun: dict[str, int] = defaultdict(int)
    with tempfile.TemporaryDirectory(prefix="atlas_sinan_") as td:
        dbf = Path(td) / (dbc_path.stem + ".dbf")
        dbc2dbf(str(dbc_path), str(dbf))
        table = DBF(str(dbf), encoding="latin-1", ignore_missing_memofile=True)
        for rec in table:
            # ID_MN_RESI / ID_MUNICIP / CODMUNRES
            code = str(
                rec.get("ID_MN_RESI")
                or rec.get("ID_MUNICIP")
                or rec.get("CODMUNRES")
                or ""
            ).strip()
            code6 = re.sub(r"\D", "", code)[:6]
            uf = ""
            if len(code6) >= 2:
                uf = UF_CODE.get(code6[:2], "")
            if not uf:
                sg = str(rec.get("SG_UF") or rec.get("SG_UF_NOT") or "").upper()[:2]
                if sg.isalpha():
                    uf = sg
            if uf:
                by_uf[uf] += 1
            if code6.isdigit() and code6 in mun6:
                by_mun[mun6[code6]] += 1

    now = utc_now()
    rows = []
    for uf, n in by_uf.items():
        rows.append(
            {
                "nivel": "STATE",
                "territory_id": f"uf_{uf}",
                "uf": uf,
                "ano": year,
                "agravos": n,
                "agravo": "dengue",
                "retrieved_at": now,
                "fonte": "datasus_sinan_dengue",
            }
        )
    for tid, n in by_mun.items():
        rows.append(
            {
                "nivel": "MUNICIPALITY",
                "territory_id": tid,
                "cod_ibge": tid.replace("mun_", ""),
                "ano": year,
                "agravos": n,
                "agravo": "dengue",
                "retrieved_at": now,
                "fonte": "datasus_sinan_dengue",
            }
        )
    return rows


def parse_local(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.suffix.lower() == ".csv" else ""
    now = utc_now()
    out = []
    if path.suffix.lower() == ".csv":
        delim = ";" if text[:2048].count(";") >= text[:2048].count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        for row in reader:
            keys = {k.lower(): k for k in row}
            try:
                ano = int(float(row.get(keys.get("ano") or keys.get("year") or 0)))
            except (TypeError, ValueError):
                continue
            val = row.get(keys.get("casos") or keys.get("agravos") or keys.get("dengue") or "")
            try:
                n = float(str(val).replace(",", "."))
            except ValueError:
                continue
            code = re.sub(r"\D", "", str(row.get(keys.get("cod_ibge") or keys.get("ibge") or "") or ""))
            uf = str(row.get(keys.get("uf") or "") or "").upper()[:2]
            if len(code) >= 6:
                tid = f"mun_{code[:7]}"
                nivel = "MUNICIPALITY"
            elif uf:
                tid, nivel, code = f"uf_{uf}", "STATE", uf
            else:
                continue
            out.append(
                {
                    "nivel": nivel,
                    "territory_id": tid,
                    "cod_ibge": code,
                    "uf": uf,
                    "ano": ano,
                    "agravos": n,
                    "agravo": "dengue",
                    "retrieved_at": now,
                    "fonte": "ATLAS_SINAN_FILE",
                }
            )
    return out


def main() -> int:
    run = start_run("datasus_sinan", "datasus.sinan_dengue")
    out = bronze_dir("datasus_sinan")
    raw = out / "dbc"
    raw.mkdir(exist_ok=True)
    rows: list[dict] = []
    messages: list[str] = []

    local = os.getenv("ATLAS_SINAN_FILE")
    if local:
        p = Path(local)
        if p.is_file():
            rows = parse_local(p)
            messages.append(f"local rows={len(rows)}")
        else:
            messages.append(f"ATLAS_SINAN_FILE ausente: {local}")

    if not rows:
        mun6 = load_mun6_map()
        try:
            ftp = FTP(FTP_HOST, timeout=180)
            ftp.login()
        except Exception as e:
            messages.append(f"FTP falhou: {e}")
            print(f"SKIPPED datasus_sinan: {e}", flush=True)
            write_json(
                out / "sinan_meta.json",
                {
                    "em": utc_now(),
                    "messages": messages,
                    "rows": 0,
                    "ingestion_run_id": run["ingestion_run_id"],
                    "day": day_stamp(),
                },
            )
            mark_ingested(
                "datasus_sinan",
                run_id=run["ingestion_run_id"],
                counts={"rows": 0},
                ok=False,
                error=str(e),
                dataset_id="datasus.sinan_dengue",
            )
            return 0

        for year in YEARS:
            yy = str(year)[2:]
            fname = f"DENGBR{yy}.dbc"
            dest = raw / fname
            got = False
            for remote in SINAN_DIRS:
                if dest.exists() and dest.stat().st_size > 0:
                    got = True
                    break
                print(f"  baixando {fname} em {remote} …", flush=True)
                if ftp_download(ftp, remote, fname, dest):
                    got = True
                    break
            if not got:
                messages.append(f"ausente {fname}")
                continue
            try:
                chunk = aggregate_dbc(dest, mun6, year)
                rows.extend(chunk)
                print(f"  OK dengue {year}: {len(chunk)} linhas", flush=True)
                if os.getenv("ATLAS_SINAN_KEEP_DBC", "").strip() not in ("1", "true"):
                    try:
                        dest.unlink(missing_ok=True)
                    except OSError:
                        pass
            except Exception as e:
                messages.append(f"{fname}: {e}")
                print(f"  FALHA {fname}: {e}", file=sys.stderr)
        try:
            ftp.quit()
        except Exception:
            pass

    if rows:
        write_jsonl(out / "sinan_extract.jsonl", rows)
    else:
        messages.append(
            "SKIPPED datasus_sinan: sem dados. Use ATLAS_SINAN_FILE ou verifique FTP DENGBR*."
        )
        print(messages[-1], flush=True)

    write_json(
        out / "sinan_meta.json",
        {
            "em": utc_now(),
            "fonte": "datasus_sinan",
            "rows": len(rows),
            "years": YEARS,
            "messages": messages,
            "ingestion_run_id": run["ingestion_run_id"],
            "day": day_stamp(),
            "agravo": "dengue",
        },
    )
    mark_ingested(
        "datasus_sinan",
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        ok=len(rows) > 0,
        dataset_id="datasus.sinan_dengue",
    )
    print(f"OK DATASUS SINAN: rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
