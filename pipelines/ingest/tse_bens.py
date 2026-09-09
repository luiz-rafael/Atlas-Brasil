#!/usr/bin/env python3
"""TSE bens de candidatos (CKAN) -> bronze RAW."""

from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    append_event,
    bronze_dir,
    http_get,
    utc_now,
    write_json,
    write_manifest,
    write_raw_record,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

CKAN = "https://dadosabertos.tse.jus.br/api/3/action"
PKG = os.getenv("TSE_BENS_PACKAGE", "candidatos-2022")


def package_show(pkg_id: str) -> dict:
    r = http_get(f"{CKAN}/package_show?id={pkg_id}", timeout=120.0)
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(str(body))
    return body["result"]


def pick_bem_resource(pkg: dict) -> dict | None:
    for res in pkg.get("resources") or []:
        name = (res.get("name") or "").lower()
        url = (res.get("url") or "").lower()
        if "bem" in name or "bem_candidato" in url or "bem_cand" in url:
            return res
    return None


def main() -> int:
    run = start_run("tse_bens", "tse.bens_2022")
    out = bronze_dir("tse_bens")
    print(f"bronze -> {out}")
    try:
        pkg = package_show(PKG)
    except Exception as e:
        mark_ingested("tse_bens", run_id=run["ingestion_run_id"], ok=False, error=str(e))
        print(f"fail package: {e}", file=sys.stderr)
        return 1

    write_json(out / f"package_{PKG}.json", pkg)
    res = pick_bem_resource(pkg)
    if not res:
        mark_ingested("tse_bens", run_id=run["ingestion_run_id"], ok=False, error="no_bem_resource")
        print("nenhum resource de bens encontrado", file=sys.stderr)
        return 1

    url = res["url"]
    r = http_get(url, timeout=600.0)
    r.raise_for_status()
    fname = Path(url.split("?")[0]).name or "bens.zip"
    dest = out / fname
    dest.write_bytes(r.content)
    write_raw_record(
        source_id="tse_bens",
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=run["connector_version"],
        payload=r.content,
        filename=fname,
        source_url=url,
        dataset_id="tse.bens_2022",
        content_type="application/zip",
    )

    # extrair CSVs pequenos
    extracted = 0
    if zipfile.is_zipfile(io.BytesIO(r.content)):
        zdir = out / "csv"
        zdir.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            for n in zf.namelist():
                if not n.lower().endswith(".csv"):
                    continue
                info = zf.getinfo(n)
                if info.file_size > 250_000_000:
                    continue
                zf.extract(n, zdir)
                extracted += 1

    write_manifest(
        out,
        "tse_bens",
        [{"file": fname, "bytes": len(r.content), "extracted_csv": extracted}],
        extra={"ingestion_run_id": run["ingestion_run_id"], "fetched_at": utc_now()},
    )
    append_event("document.discovered", {"source": "tse_bens", "path": str(out)})
    mark_ingested(
        "tse_bens",
        run_id=run["ingestion_run_id"],
        counts={"bytes": len(r.content), "csv": extracted},
    )
    print(f"OK TSE bens: {fname} csv={extracted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
