#!/usr/bin/env python3
"""
Ingest Novo CAGED — agregação municipal (extract separado).

Não altera caged_mov_uf_extract.jsonl. Usa INCLUDE_MUN forçado.
Anos: ATLAS_CAGED_YEARS default 2024,2025.
Bronze: caged_mov_mun_extract.jsonl
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# força mun + anos default antes de importar helpers
os.environ.setdefault("ATLAS_CAGED_YEARS", "2024,2025")
os.environ["ATLAS_CAGED_MUN"] = "1"

from ftplib import FTP  # noqa: E402

from pipelines.common import bronze_dir, day_stamp, utc_now, write_json  # noqa: E402
from pipelines.ingest.caged_mov import (  # noqa: E402
    FTP_BASE,
    FTP_HOST,
    YEARS,
    download_mov,
    list_months,
    load_done,
    process_7z,
)
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    run = start_run("caged", "caged.novo_mov_mun")
    out = bronze_dir("caged")
    raw = out / "mov"
    raw.mkdir(exist_ok=True)
    extract = out / "caged_mov_mun_extract.jsonl"
    done = load_done(extract)

    try:
        ftp = FTP(FTP_HOST, timeout=300)
        ftp.encoding = "latin-1"
        ftp.login()
    except Exception as e:
        print(f"FTP CAGED indisponível: {e}", file=sys.stderr)
        mark_ingested(
            "caged",
            run_id=run["ingestion_run_id"],
            counts={"ok": 0, "fail": 1},
            ok=False,
            error=str(e),
            dataset_id=dataset_id_from_env("caged_mov_mun"),
        )
        return 1

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
                print(f"  agregando mun {ym} …", flush=True)
                by_uf, by_mun = process_7z(dest, include_mun=True)
                append_jsonl(
                    extract,
                    {
                        "competencia": ym,
                        "ano": int(ym[:4]),
                        "mes": int(ym[4:6]),
                        "uf_metrics": {},
                        "mun_metrics": by_mun,
                        "retrieved_at": utc_now(),
                        "file": dest.name,
                        "bytes": dest.stat().st_size,
                    },
                )
                done.add(ym)
                ok += 1
                print(f"  OK {ym}: mun={len(by_mun)} (uf agregada omitida neste extract)", flush=True)
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
        "include_mun": True,
        "ok": ok,
        "fail": fail,
        "extract": extract.name,
        "ingestion_run_id": run["ingestion_run_id"],
        "day": day_stamp(),
        "nota": "Extract municipal separado — não altera caged_mov_uf_extract.jsonl",
    }
    write_json(out / "caged_mun_meta.json", meta)
    mark_ingested(
        "caged",
        run_id=run["ingestion_run_id"],
        counts={"ok": ok, "fail": fail},
        ok=ok > 0,
        dataset_id=dataset_id_from_env("caged_mov_mun"),
    )
    print(f"OK CAGED mun: ok={ok} fail={fail} -> {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
