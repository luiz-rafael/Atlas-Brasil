#!/usr/bin/env python3
"""
Ingest DATASUS SIH — AIH Reduzidas (RD) agregadas por UF/ano.

FTP: ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RD{UF}{YY}{MM}.dbc

Conta registros (internações) por UF e ano. Município opcional via ATLAS_SIH_MUN=1
(mais lento). Anos via ATLAS_SIH_YEAR_START / ATLAS_SIH_YEAR_END.

Bronze: sih_extract.jsonl
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
SIH_DIR = "/dissemin/publicos/SIHSUS/200801_/Dados"

UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]

YEARS = list(
    range(
        int(os.getenv("ATLAS_SIH_YEAR_START", "2021")),
        int(os.getenv("ATLAS_SIH_YEAR_END", "2022")) + 1,
    )
)
DO_MUN = os.getenv("ATLAS_SIH_MUN", "").strip().lower() in ("1", "true", "yes")
# limitar UFs p/ smoke: ATLAS_SIH_UFS=RJ,SP
UF_FILTER = [u.strip().upper() for u in os.getenv("ATLAS_SIH_UFS", "").split(",") if u.strip()]


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


def ftp_download(ftp: FTP, filename: str, dest: Path) -> bool:
    try:
        ftp.cwd(SIH_DIR)
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


def count_dbc(dbc_path: Path, mun6: dict[str, str]) -> tuple[int, dict[str, int]]:
    by_mun: dict[str, int] = defaultdict(int)
    total = 0
    with tempfile.TemporaryDirectory(prefix="atlas_sih_") as td:
        dbf = Path(td) / (dbc_path.stem + ".dbf")
        dbc2dbf(str(dbc_path), str(dbf))
        table = DBF(str(dbf), encoding="latin-1", ignore_missing_memofile=True)
        for rec in table:
            total += 1
            if not DO_MUN:
                continue
            # MUNIC_RES ou MUNIC_MOV
            code6 = str(rec.get("MUNIC_RES") or rec.get("MUNIC_MOV") or "").strip()[:6]
            if code6.isdigit() and code6 in mun6:
                by_mun[mun6[code6]] += 1
    return total, dict(by_mun)


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
            done.add(f"{row.get('uf')}|{row.get('exercicio')}|{row.get('mes')}")
        except json.JSONDecodeError:
            continue
    return done


def main() -> int:
    run = start_run("datasus_sih", "datasus.sih_rd")
    out = bronze_dir("datasus_sih")
    raw = out / "dbc"
    raw.mkdir(exist_ok=True)
    extract = out / "sih_extract.jsonl"
    done = load_done(extract)
    mun6 = load_mun6_map() if DO_MUN else {}
    ufs = UF_FILTER or UFS
    print(f"  years={YEARS[0]}-{YEARS[-1]} ufs={len(ufs)} mun={DO_MUN}", flush=True)

    try:
        ftp = FTP(FTP_HOST, timeout=180)
        ftp.login()
    except Exception as e:
        print(f"SKIPPED datasus_sih: FTP indisponível ({e})", flush=True)
        mark_ingested(
            "datasus_sih",
            run_id=run["ingestion_run_id"],
            counts={"ok": 0},
            ok=False,
            error=str(e),
            dataset_id="datasus.sih_rd",
        )
        return 0

    ok = 0
    fail = 0

    for year in YEARS:
        yy = str(year)[2:]
        for uf in ufs:
            for month in range(1, 13):
                key = f"{uf}|{year}|{month:02d}"
                if key in done:
                    continue
                fname = f"RD{uf}{yy}{month:02d}.dbc"
                dest = raw / fname
                try:
                    if not dest.exists() or dest.stat().st_size == 0:
                        print(f"  baixando {fname} …", flush=True)
                        if not ftp_download(ftp, fname, dest):
                            append_jsonl(
                                extract,
                                {
                                    "uf": uf,
                                    "exercicio": year,
                                    "mes": f"{month:02d}",
                                    "missing": True,
                                    "retrieved_at": utc_now(),
                                },
                            )
                            done.add(key)
                            continue
                    n, mun_agg = count_dbc(dest, mun6)
                    row = {
                        "uf": uf,
                        "exercicio": year,
                        "mes": f"{month:02d}",
                        "internacoes": n,
                        "mun_metrics": mun_agg,
                        "retrieved_at": utc_now(),
                        "file": fname,
                    }
                    append_jsonl(extract, row)
                    done.add(key)
                    ok += 1
                    print(f"  OK {fname}: {n}", flush=True)
                    if os.getenv("ATLAS_SIH_KEEP_DBC", "").strip() not in ("1", "true"):
                        try:
                            dest.unlink(missing_ok=True)
                        except OSError:
                            pass
                except Exception as e:
                    fail += 1
                    print(f"  FALHA {fname}: {e}", file=sys.stderr)
                    append_jsonl(
                        out / "errors.jsonl",
                        {"uf": uf, "exercicio": year, "mes": month, "error": str(e)},
                    )

    # resumo anual a partir do extract (inclui resume)
    annual: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"internacoes": 0, "mun_metrics": defaultdict(int)}
    )
    annual_path = out / "sih_annual_extract.jsonl"
    now = utc_now()
    if extract.exists():
        for line in extract.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("missing"):
                continue
            uf, year = row.get("uf"), row.get("exercicio")
            if not uf or not year:
                continue
            annual[(uf, int(year))]["internacoes"] += int(row.get("internacoes") or 0)
            for tid, c in (row.get("mun_metrics") or {}).items():
                annual[(uf, int(year))]["mun_metrics"][tid] += int(c)

    with annual_path.open("w", encoding="utf-8") as f:
        for (uf, year), m in sorted(annual.items()):
            f.write(
                json.dumps(
                    {
                        "uf": uf,
                        "exercicio": year,
                        "internacoes": m["internacoes"],
                        "mun_metrics": dict(m["mun_metrics"]),
                        "retrieved_at": now,
                        "fonte": "datasus_sih_rd",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    try:
        ftp.quit()
    except Exception:
        pass

    write_json(
        out / "sih_meta.json",
        {
            "em": utc_now(),
            "fonte": "datasus_sih",
            "ftp": FTP_HOST,
            "years": YEARS,
            "ok": ok,
            "fail": fail,
            "ingestion_run_id": run["ingestion_run_id"],
            "day": day_stamp(),
        },
    )
    mark_ingested(
        "datasus_sih",
        run_id=run["ingestion_run_id"],
        counts={"ok": ok, "fail": fail, "annual": len(annual)},
        ok=ok > 0 or len(annual) > 0,
        dataset_id="datasus.sih_rd",
    )
    print(f"OK DATASUS SIH: ok={ok} fail={fail} annual={len(annual)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
