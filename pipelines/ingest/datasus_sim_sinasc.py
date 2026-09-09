#!/usr/bin/env python3
"""
Ingest DATASUS — SIM (óbitos) + SINASC (nascidos vivos) via FTP oficial.

FTP:
  ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DO{UF}{ANO}.dbc
  ftp.datasus.gov.br/dissemin/publicos/SINASC/NOV/DNRES/DN{UF}{ANO}.dbc

Agrega por UF e município (residência):
  nascidos_vivos, obitos, obitos_infantis (IDADE < 400)

Bronze slim: extracts JSONL (não guarda microdados).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import defaultdict
from ftplib import FTP, error_perm
from pathlib import Path

from dbfread import DBF
from pyreaddbc import dbc2dbf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, utc_now, write_json  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

FTP_HOST = "ftp.datasus.gov.br"
SIM_DIR = "/dissemin/publicos/SIM/CID10/DORES"
SINASC_DIR = "/dissemin/publicos/SINASC/NOV/DNRES"

UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]

YEARS = list(
    range(
        int(os.getenv("ATLAS_DATASUS_YEAR_START", "2015")),
        int(os.getenv("ATLAS_DATASUS_YEAR_END", "2023")) + 1,
    )
)
# UF_ONLY=1 só agrega estado (mais rápido)
UF_ONLY = os.getenv("ATLAS_DATASUS_UF_ONLY", "").strip() in ("1", "true", "yes")
# Quando False, grava mun em arquivo separado (não duplica UF no extract principal)
MUN_EXTRACT_NAME = "sim_sinasc_mun_extract.jsonl"


def load_mun6_map() -> dict[str, str]:
    """CODMUNRES 6 dígitos → territory_id mun_XXXXXXX."""
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
    # case variants
    names = []
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


def aggregate_sinasc(dbf_path: Path, mun6: dict[str, str]) -> tuple[dict[str, int], dict[str, int]]:
    by_mun: dict[str, int] = defaultdict(int)
    uf_total = 0
    table = DBF(str(dbf_path), encoding="latin-1", ignore_missing_memofile=True)
    for rec in table:
        uf_total += 1
        if UF_ONLY:
            continue
        code6 = str(rec.get("CODMUNRES") or "").strip()[:6]
        if code6.isdigit() and code6 in mun6:
            by_mun[mun6[code6]] += 1
    return {"nascidos_vivos": uf_total}, dict(by_mun)


def aggregate_sim(dbf_path: Path, mun6: dict[str, str]) -> tuple[dict, dict]:
    uf = {"obitos": 0, "obitos_infantis": 0}
    by_mun: dict[str, dict[str, int]] = defaultdict(lambda: {"obitos": 0, "obitos_infantis": 0})
    table = DBF(str(dbf_path), encoding="latin-1", ignore_missing_memofile=True)
    for rec in table:
        uf["obitos"] += 1
        try:
            idade = int(str(rec.get("IDADE") or "999").strip() or "999")
        except ValueError:
            idade = 999
        infantil = idade < 400
        if infantil:
            uf["obitos_infantis"] += 1
        if UF_ONLY:
            continue
        code6 = str(rec.get("CODMUNRES") or "").strip()[:6]
        if code6.isdigit() and code6 in mun6:
            tid = mun6[code6]
            by_mun[tid]["obitos"] += 1
            if infantil:
                by_mun[tid]["obitos_infantis"] += 1
    return uf, {k: dict(v) for k, v in by_mun.items()}


def process_dbc(dbc_path: Path, kind: str, mun6: dict[str, str]):
    with tempfile.TemporaryDirectory(prefix="atlas_dbc_") as td:
        dbf = Path(td) / (dbc_path.stem + ".dbf")
        dbc2dbf(str(dbc_path), str(dbf))
        if kind == "sinasc":
            return aggregate_sinasc(dbf, mun6)
        return aggregate_sim(dbf, mun6)


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            done.add(f"{row.get('fonte')}|{row.get('uf')}|{row.get('exercicio')}")
        except json.JSONDecodeError:
            continue
    return done


def main() -> int:
    run = start_run("datasus", "datasus.sim_sinasc_p0")
    out = bronze_dir("datasus")
    raw = out / "dbc"
    raw.mkdir(exist_ok=True)
    extract = out / "sim_sinasc_extract.jsonl"
    extract_mun = out / MUN_EXTRACT_NAME
    # UF: skip se já no extract principal; mun: skip se já no extract mun
    done_uf = load_done(extract)
    done_mun = load_done(extract_mun)
    mun6 = load_mun6_map()
    print(
        f"  mun map={len(mun6)} years={YEARS[0]}-{YEARS[-1]} uf_only={UF_ONLY}",
        flush=True,
    )

    ftp = FTP(FTP_HOST, timeout=180)
    ftp.login()

    ok = 0
    fail = 0
    now = utc_now()

    for year in YEARS:
        for uf in UFS:
            for fonte, remote, prefix in (
                ("sinasc", SINASC_DIR, "DN"),
                ("sim", SIM_DIR, "DO"),
            ):
                key = f"{fonte}|{uf}|{year}"
                need_uf = UF_ONLY or key not in done_uf
                need_mun = (not UF_ONLY) and key not in done_mun
                if not need_uf and not need_mun:
                    continue
                # se só falta mun, ainda precisa baixar/processar
                if not need_mun and key in done_uf:
                    continue
                fname = f"{prefix}{uf}{year}.dbc"
                dest = raw / fname
                try:
                    if not dest.exists() or dest.stat().st_size == 0:
                        print(f"  baixando {fname} …", flush=True)
                        if not ftp_download(ftp, remote, fname, dest):
                            print(f"  skip ausente {fname}", flush=True)
                            miss = {
                                "fonte": fonte,
                                "uf": uf,
                                "exercicio": year,
                                "missing": True,
                                "retrieved_at": now,
                            }
                            if need_uf and key not in done_uf:
                                append_jsonl(extract, miss)
                                done_uf.add(key)
                            if need_mun:
                                append_jsonl(extract_mun, miss)
                                done_mun.add(key)
                            continue
                    uf_agg, mun_agg = process_dbc(dest, fonte, mun6)
                    row = {
                        "fonte": fonte,
                        "uf": uf,
                        "exercicio": year,
                        "uf_metrics": uf_agg,
                        "mun_metrics": mun_agg if not UF_ONLY else {},
                        "retrieved_at": utc_now(),
                        "file": fname,
                        "bytes": dest.stat().st_size,
                    }
                    if need_uf and key not in done_uf:
                        # extract principal: UF metrics (mun vazio se modo mun separado)
                        row_uf = dict(row)
                        if not UF_ONLY:
                            row_uf["mun_metrics"] = {}
                        append_jsonl(extract, row_uf)
                        done_uf.add(key)
                    if need_mun:
                        append_jsonl(extract_mun, row)
                        done_mun.add(key)
                    ok += 1
                    n_mun = len(mun_agg) if isinstance(mun_agg, dict) else 0
                    print(f"  OK {fonte} {uf} {year}: {uf_agg} mun={n_mun}", flush=True)
                    if os.getenv("ATLAS_DATASUS_KEEP_DBC", "").strip() not in ("1", "true"):
                        try:
                            dest.unlink(missing_ok=True)
                        except OSError:
                            pass
                except Exception as e:
                    fail += 1
                    print(f"  FALHA {fonte} {uf} {year}: {e}", file=sys.stderr)
                    append_jsonl(
                        out / "errors.jsonl",
                        {"fonte": fonte, "uf": uf, "exercicio": year, "error": str(e)},
                    )

    try:
        ftp.quit()
    except Exception:
        pass

    meta = {
        "em": utc_now(),
        "fonte": "datasus",
        "ftp": FTP_HOST,
        "years": YEARS,
        "uf_only": UF_ONLY,
        "ok": ok,
        "fail": fail,
        "extract": extract.name,
        "extract_mun": extract_mun.name if not UF_ONLY else None,
        "ingestion_run_id": run["ingestion_run_id"],
        "day": day_stamp(),
    }
    write_json(out / "datasus_meta.json", meta)
    mark_ingested(
        "datasus",
        run_id=run["ingestion_run_id"],
        counts={"ok": ok, "fail": fail},
        ok=ok > 0,
    )
    print(f"OK DATASUS: ok={ok} fail={fail} → {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
