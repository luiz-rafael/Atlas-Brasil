#!/usr/bin/env python3
"""
Ingest DATASUS SIM — homicídios (agressões CID-10 X85–Y09) e causas externas (V01–Y98).

FTP: ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DO{UF}{ANO}.dbc

Reutiliza DBC locais em bronze/datasus/*/dbc quando existirem.
Bronze: sim_homicidios_extract.jsonl (STATE + MUNICIPALITY).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from ftplib import FTP, error_perm
from pathlib import Path

from dbfread import DBF
from pyreaddbc import dbc2dbf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, bronze_dir, day_stamp, utc_now, write_json  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

FTP_HOST = "ftp.datasus.gov.br"
SIM_DIR = "/dissemin/publicos/SIM/CID10/DORES"

UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]

YEARS = list(
    range(
        int(os.getenv("ATLAS_HOMICIDIOS_YEAR_START", "2015")),
        int(os.getenv("ATLAS_HOMICIDIOS_YEAR_END", "2022")) + 1,
    )
)
UF_ONLY = os.getenv("ATLAS_DATASUS_UF_ONLY", "").strip() in ("1", "true", "yes")
EXTRACT_NAME = "sim_homicidios_extract.jsonl"


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
            m[code[:6]] = code  # IBGE 6/7 dígitos
    return m


def _cid_num(code: str) -> tuple[str, int] | None:
    c = (code or "").strip().upper()
    m = re.match(r"^([A-Z])(\d{2})", c)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def is_aggression(code: str) -> bool:
    """CID-10 X85–Y09 (agressões / homicídios)."""
    parsed = _cid_num(code)
    if not parsed:
        return False
    letter, num = parsed
    if letter == "X" and 85 <= num <= 99:
        return True
    if letter == "Y" and 0 <= num <= 9:
        return True
    return False


def is_external(code: str) -> bool:
    """CID-10 V01–Y98 (causas externas)."""
    parsed = _cid_num(code)
    if not parsed:
        return False
    letter, num = parsed
    if letter == "V" and 1 <= num <= 99:
        return True
    if letter == "W" and 0 <= num <= 99:
        return True
    if letter == "X" and 0 <= num <= 99:
        return True
    if letter == "Y" and 0 <= num <= 98:
        return True
    return False


def find_local_dbc(fname: str) -> Path | None:
    base = LAKE / "bronze" / "datasus"
    if not base.exists():
        return None
    candidates: list[Path] = []
    for day in base.iterdir():
        if not day.is_dir():
            continue
        p = day / "dbc" / fname
        if p.exists() and p.stat().st_size > 0:
            candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


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


def aggregate_sim(dbf_path: Path, mun6: dict[str, str]) -> tuple[dict, dict]:
    uf = {"homicidios": 0, "causas_externas": 0}
    by_mun: dict[str, dict[str, int]] = defaultdict(
        lambda: {"homicidios": 0, "causas_externas": 0}
    )
    table = DBF(str(dbf_path), encoding="latin-1", ignore_missing_memofile=True)
    for rec in table:
        causa = str(rec.get("CAUSABAS") or "").strip()
        hom = is_aggression(causa)
        ext = is_external(causa)
        if hom:
            uf["homicidios"] += 1
        if ext:
            uf["causas_externas"] += 1
        if UF_ONLY or (not hom and not ext):
            continue
        code6 = str(rec.get("CODMUNRES") or "").strip()[:6]
        if code6.isdigit() and code6 in mun6:
            tid_code = mun6[code6]
            if hom:
                by_mun[tid_code]["homicidios"] += 1
            if ext:
                by_mun[tid_code]["causas_externas"] += 1
    return uf, {k: dict(v) for k, v in by_mun.items()}


def process_dbc(dbc_path: Path, mun6: dict[str, str]):
    with tempfile.TemporaryDirectory(prefix="atlas_hom_") as td:
        dbf = Path(td) / (dbc_path.stem + ".dbf")
        dbc2dbf(str(dbc_path), str(dbf))
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
            key = f"{row.get('nivel')}|{row.get('uf')}|{row.get('cod_ibge')}|{row.get('ano')}"
            done.add(key)
        except json.JSONDecodeError:
            continue
    return done


def main() -> int:
    run = start_run("datasus", "datasus.sim_homicidios")
    out = bronze_dir("datasus")
    raw = out / "dbc"
    raw.mkdir(exist_ok=True)
    extract = out / EXTRACT_NAME
    done = load_done(extract)
    mun6 = load_mun6_map()
    print(
        f"  mun map={len(mun6)} years={YEARS[0]}-{YEARS[-1]} uf_only={UF_ONLY}",
        flush=True,
    )

    ftp: FTP | None = None
    try:
        ftp = FTP(FTP_HOST, timeout=180)
        ftp.login()
    except Exception as e:
        print(f"  FTP indisponível ({e}); só DBC locais", flush=True)
        ftp = None

    ok = 0
    fail = 0
    now = utc_now()

    for year in YEARS:
        for uf in UFS:
            key_uf = f"STATE|{uf}|{uf}|{year}"
            need = key_uf not in done
            if not need and UF_ONLY:
                continue
            fname = f"DO{uf}{year % 100:02d}.dbc"
            # anos com 4 dígitos no FTP recente (padrão DO{UF}{YYYY})
            fname_full = f"DO{uf}{year}.dbc"
            dest = raw / fname_full
            local = find_local_dbc(fname_full) or find_local_dbc(fname)
            try:
                if local and (not dest.exists() or dest.stat().st_size == 0):
                    dest.write_bytes(local.read_bytes())
                    print(f"  reuse local {local}", flush=True)
                if not dest.exists() or dest.stat().st_size == 0:
                    if ftp is None:
                        print(f"  skip sem FTP/local {fname_full}", flush=True)
                        fail += 1
                        continue
                    print(f"  baixando {fname_full} …", flush=True)
                    if not ftp_download(ftp, SIM_DIR, fname_full, dest):
                        # tenta YY
                        if not ftp_download(ftp, SIM_DIR, fname, dest):
                            print(f"  skip ausente {fname_full}", flush=True)
                            continue
                uf_agg, mun_agg = process_dbc(dest, mun6)
                if key_uf not in done:
                    append_jsonl(
                        extract,
                        {
                            "nivel": "STATE",
                            "uf": uf,
                            "cod_ibge": uf,
                            "territory_id": f"uf_{uf}",
                            "ano": year,
                            "homicidios": uf_agg["homicidios"],
                            "causas_externas": uf_agg["causas_externas"],
                            "retrieved_at": now,
                            "file": dest.name,
                        },
                    )
                    done.add(key_uf)
                if not UF_ONLY:
                    for code, metrics in mun_agg.items():
                        cod = str(code)
                        key_m = f"MUNICIPALITY|{uf}|{cod}|{year}"
                        if key_m in done:
                            continue
                        append_jsonl(
                            extract,
                            {
                                "nivel": "MUNICIPALITY",
                                "uf": uf,
                                "cod_ibge": cod,
                                "territory_id": f"mun_{cod}",
                                "ano": year,
                                "homicidios": metrics.get("homicidios") or 0,
                                "causas_externas": metrics.get("causas_externas") or 0,
                                "retrieved_at": utc_now(),
                                "file": dest.name,
                            },
                        )
                        done.add(key_m)
                ok += 1
                print(
                    f"  OK {uf} {year}: hom={uf_agg['homicidios']} ext={uf_agg['causas_externas']} mun={len(mun_agg)}",
                    flush=True,
                )
                if os.getenv("ATLAS_DATASUS_KEEP_DBC", "").strip() not in ("1", "true"):
                    # não apaga se veio de reuse cross-day; só cópia do dia atual sem keep
                    pass
            except Exception as e:
                fail += 1
                print(f"  FALHA {uf} {year}: {e}", file=sys.stderr)
                append_jsonl(
                    out / "errors_homicidios.jsonl",
                    {"uf": uf, "ano": year, "error": str(e)},
                )

    if ftp is not None:
        try:
            ftp.quit()
        except Exception:
            pass

    meta = {
        "em": utc_now(),
        "fonte": "datasus",
        "dataset": "sim_homicidios",
        "ftp": FTP_HOST,
        "years": YEARS,
        "uf_only": UF_ONLY,
        "ok": ok,
        "fail": fail,
        "extract": extract.name,
        "ingestion_run_id": run["ingestion_run_id"],
        "day": day_stamp(),
        "nota": "homicidios=CAUSABAS X85–Y09; causas_externas=V01–Y98",
    }
    write_json(out / "datasus_homicidios_meta.json", meta)
    mark_ingested(
        "datasus",
        run_id=run["ingestion_run_id"],
        counts={"ok": ok, "fail": fail},
        ok=ok > 0,
        dataset_id="datasus.sim_homicidios",
    )
    print(f"OK DATASUS homicídios: ok={ok} fail={fail} -> {out}")
    if ok == 0 and fail:
        print("Remoto/local indisponível — nenhuma observação gerada.", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
