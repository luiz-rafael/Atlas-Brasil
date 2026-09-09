#!/usr/bin/env python3
"""
Ingest Novo CAGED (MTE/PDET) — fluxo de emprego formal.

FTP: ftp.mtps.gov.br/pdet/microdados/NOVO CAGED/{AAAA}/{AAAAMM}/CAGEDMOV{AAAAMM}.7z

Slice P0: agrega por UF (e opcionalmente município) por competência mensal,
depois rola saldo/admissões/desligamentos anuais.

Não chamar saldo de "taxa de desemprego" — é movimentação formal.
"""

from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
from collections import defaultdict
from ftplib import FTP
from pathlib import Path

import py7zr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, utc_now, write_json  # noqa: E402
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402

FTP_HOST = "ftp.mtps.gov.br"
FTP_BASE = "/pdet/microdados/NOVO CAGED"

# IBGE UF code → sigla
UF_CODE = {
    11: "RO",
    12: "AC",
    13: "AM",
    14: "RR",
    15: "PA",
    16: "AP",
    17: "TO",
    21: "MA",
    22: "PI",
    23: "CE",
    24: "RN",
    25: "PB",
    26: "PE",
    27: "AL",
    28: "SE",
    29: "BA",
    31: "MG",
    32: "ES",
    33: "RJ",
    35: "SP",
    41: "PR",
    42: "SC",
    43: "RS",
    50: "MS",
    51: "MT",
    52: "GO",
    53: "DF",
}

YEARS = [
    int(y)
    for y in os.getenv("ATLAS_CAGED_YEARS", "2024").split(",")
    if y.strip().isdigit()
]
INCLUDE_MUN = os.getenv("ATLAS_CAGED_MUN", "").strip() in ("1", "true", "yes")


def list_months(ftp: FTP, year: int) -> list[str]:
    ftp.cwd(f"{FTP_BASE}/{year}")
    names = ftp.nlst()
    return sorted(n for n in names if n.isdigit() and n.startswith(str(year)))


def download_mov(ftp: FTP, yearmonth: str, dest: Path) -> bool:
    year = yearmonth[:4]
    fname = f"CAGEDMOV{yearmonth}.7z"
    try:
        ftp.cwd(f"{FTP_BASE}/{year}/{yearmonth}")
    except Exception:
        return False
    names = {n.upper(): n for n in ftp.nlst()}
    real = names.get(fname.upper())
    if not real:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    ftp.sendcmd("TYPE I")
    with dest.open("wb") as f:
        ftp.retrbinary(f"RETR {real}", f.write)
    return dest.exists() and dest.stat().st_size > 0


def find_col(fieldnames: list[str], *needles: str) -> str | None:
    lower = {f.lower(): f for f in fieldnames}
    for n in needles:
        for k, orig in lower.items():
            if n in k.replace(" ", ""):
                return orig
    return None


def aggregate_txt(
    txt_path: Path, include_mun: bool | None = None
) -> tuple[dict, dict]:
    """Retorna (by_uf, by_mun) com admissoes/desligamentos/saldo."""
    do_mun = INCLUDE_MUN if include_mun is None else include_mun
    by_uf: dict[str, dict[str, int]] = defaultdict(
        lambda: {"admissoes": 0, "desligamentos": 0, "saldo": 0}
    )
    by_mun: dict[str, dict[str, int]] = defaultdict(
        lambda: {"admissoes": 0, "desligamentos": 0, "saldo": 0}
    )
    with txt_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        reader = csv.DictReader(f, delimiter=dialect.delimiter)
        if not reader.fieldnames:
            return {}, {}
        col_uf = find_col(reader.fieldnames, "uf")
        col_mun = find_col(reader.fieldnames, "municipio", "município")
        col_saldo = find_col(
            reader.fieldnames, "saldomovimentacao", "saldomovimentação", "saldo"
        )
        if not col_uf or not col_saldo:
            raise RuntimeError(f"colunas não encontradas: {reader.fieldnames[:12]}")
        for row in reader:
            try:
                uf_code = int(str(row.get(col_uf) or "0").strip() or 0)
            except ValueError:
                continue
            sigla = UF_CODE.get(uf_code)
            if not sigla:
                continue
            try:
                saldo = int(float(str(row.get(col_saldo) or "0").replace(",", ".")))
            except ValueError:
                continue
            bucket = by_uf[sigla]
            if saldo > 0:
                bucket["admissoes"] += saldo
                bucket["saldo"] += saldo
            elif saldo < 0:
                bucket["desligamentos"] += -saldo
                bucket["saldo"] += saldo
            if do_mun and col_mun:
                code6 = str(row.get(col_mun) or "").strip()[:6]
                if code6.isdigit() and len(code6) == 6:
                    mb = by_mun[code6]
                    if saldo > 0:
                        mb["admissoes"] += saldo
                        mb["saldo"] += saldo
                    elif saldo < 0:
                        mb["desligamentos"] += -saldo
                        mb["saldo"] += saldo
    return dict(by_uf), dict(by_mun)


def process_7z(archive: Path, include_mun: bool | None = None) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory(prefix="caged_") as td:
        with py7zr.SevenZipFile(archive, mode="r") as z:
            z.extractall(path=td)
        txts = list(Path(td).rglob("*.txt")) + list(Path(td).rglob("*.TXT"))
        if not txts:
            raise RuntimeError("sem .txt no 7z")
        return aggregate_txt(txts[0], include_mun=include_mun)


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(__import__("json").dumps(row, ensure_ascii=False) + "\n")


def load_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    import json

    done = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            ym = row.get("competencia")
            if ym:
                done.add(str(ym))
        except json.JSONDecodeError:
            continue
    return done


def main() -> int:
    run = start_run("caged", "caged.novo_mov_p0")
    out = bronze_dir("caged")
    raw = out / "mov"
    raw.mkdir(exist_ok=True)
    extract = out / "caged_mov_uf_extract.jsonl"
    done = load_done(extract)

    ftp = FTP(FTP_HOST, timeout=300)
    ftp.encoding = "latin-1"
    ftp.login()

    ok = 0
    fail = 0
    for year in YEARS:
        try:
            months = list_months(ftp, year)
        except Exception as e:
            print(f"  FALHA listar {year}: {e}", file=sys.stderr)
            fail += 1
            continue
        for ym in months:
            if ym in done:
                continue
            dest = raw / f"CAGEDMOV{ym}.7z"
            try:
                if not dest.exists() or dest.stat().st_size == 0:
                    print(f"  baixando CAGEDMOV{ym}.7z …", flush=True)
                    if not download_mov(ftp, ym, dest):
                        print(f"  skip ausente {ym}", flush=True)
                        continue
                print(f"  agregando {ym} …", flush=True)
                by_uf, by_mun = process_7z(dest)
                append_jsonl(
                    extract,
                    {
                        "competencia": ym,
                        "ano": int(ym[:4]),
                        "mes": int(ym[4:6]),
                        "uf_metrics": by_uf,
                        "mun_metrics": by_mun if INCLUDE_MUN else {},
                        "retrieved_at": utc_now(),
                        "file": dest.name,
                        "bytes": dest.stat().st_size,
                    },
                )
                done.add(ym)
                ok += 1
                sp = by_uf.get("SP", {})
                print(
                    f"  OK {ym}: UFs={len(by_uf)} SP saldo={sp.get('saldo')} adm={sp.get('admissoes')}",
                    flush=True,
                )
                if os.getenv("ATLAS_CAGED_KEEP_7Z", "").strip() not in ("1", "true"):
                    try:
                        dest.unlink(missing_ok=True)
                    except OSError:
                        pass
            except Exception as e:
                fail += 1
                print(f"  FALHA {ym}: {e}", file=sys.stderr)

    try:
        ftp.quit()
    except Exception:
        pass

    meta = {
        "em": utc_now(),
        "fonte": "caged",
        "ftp": f"ftp://{FTP_HOST}{FTP_BASE}",
        "years": YEARS,
        "include_mun": INCLUDE_MUN,
        "ok": ok,
        "fail": fail,
        "extract": extract.name,
        "ingestion_run_id": run["ingestion_run_id"],
        "day": day_stamp(),
        "nota": "Saldo CAGED = fluxo formal (admissões − desligamentos), não taxa de desemprego.",
    }
    write_json(out / "caged_meta.json", meta)
    mark_ingested(
        "caged",
        run_id=run["ingestion_run_id"],
        counts={"ok": ok, "fail": fail},
        ok=ok > 0,
        dataset_id=dataset_id_from_env("caged_mov"),
    )
    print(f"OK CAGED: ok={ok} fail={fail} → {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
