#!/usr/bin/env python3
"""
Ingestor TSE — Dados Abertos (CKAN) bulk ZIP/CSV -> bronze.

Prioriza pacotes candidatos-2022 e candidatos-2024.
Por padrão baixa apenas o recurso principal de candidatos (consulta_cand),
não todos os anexos (bens/fotos), para caber em disco no MVP.
"""

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
    sha1_bytes,
    utc_now,
    write_json,
    write_manifest,
    write_raw_record,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

CKAN = "https://dadosabertos.tse.jus.br/api/3/action"
PACKAGES = [
    p.strip()
    for p in os.getenv("TSE_PACKAGES", "candidatos-2022,candidatos-2024").split(",")
    if p.strip()
]
# palavras no nome do resource para priorizar
WANT = ("candidato", "consulta_cand", "cand_")
SKIP = ("foto", "proposta", "rede", "bem", "coligacao", "motivo", "vaga")


def package_show(pkg_id: str) -> dict:
    r = http_get(f"{CKAN}/package_show?id={pkg_id}", timeout=120.0)
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"CKAN falhou: {pkg_id} -> {body}")
    return body["result"]


def pick_resources(pkg: dict, max_files: int = 3) -> list[dict]:
    resources = pkg.get("resources") or []
    scored = []
    for res in resources:
        name = (res.get("name") or res.get("description") or "").lower()
        fmt = (res.get("format") or "").lower()
        url = (res.get("url") or "").lower()
        if not url:
            continue
        # legendas / coligações / bens etc. não servem para mandato
        if any(
            s in name or s in url
            for s in (
                "legenda",
                "coligacao",
                "coligação",
                "foto",
                "proposta",
                "rede",
                "bem",
                "motivo",
                "vaga",
            )
        ):
            continue
        if any(s in name for s in SKIP) and "candidato" not in name:
            continue
        score = 0
        if "consulta_cand" in url or "consulta_cand" in name:
            score += 20
        if any(w in name for w in WANT):
            score += 5
        if "brasil" in name or "br.csv" in url:
            score += 3
        if fmt in ("zip", "csv") or url.endswith((".zip", ".csv")):
            score += 1
        if score > 0:
            scored.append((score, res))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:max_files]]


def download_file(url: str, dest: Path) -> dict:
    print(f"  baixando {url[:90]}...")
    r = http_get(url, timeout=600.0)
    r.raise_for_status()
    dest.write_bytes(r.content)
    meta = {
        "url": url,
        "file": dest.name,
        "bytes": len(r.content),
        "sha1": sha1_bytes(r.content),
    }
    brasil_only = os.getenv("TSE_BRASIL_ONLY", "1") == "1"
    max_csv = int(os.getenv("TSE_MAX_CSV_BYTES", str(400_000_000)))
    # extrair CSV do ZIP (por padrão só *BRASIL* não complementar)
    if dest.suffix.lower() == ".zip" or zipfile.is_zipfile(dest):
        extract_dir = dest.with_suffix("")
        extract_dir.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                names = zf.namelist()
                meta["zip_entries"] = len(names)
                csvs = [n for n in names if n.lower().endswith(".csv")]
                if brasil_only:
                    prefer = [
                        n
                        for n in csvs
                        if "brasil" in Path(n).name.lower()
                        and "complementar" not in Path(n).name.lower()
                    ]
                    if prefer:
                        csvs = prefer
                for n in csvs:
                    info = zf.getinfo(n)
                    if info.file_size > max_csv:
                        meta.setdefault("skipped_large", []).append(n)
                        continue
                    zf.extract(n, extract_dir)
                    print(
                        f"    extraiu {Path(n).name} ({info.file_size // 1_000_000}MB)",
                        flush=True,
                    )
                meta["extracted_to"] = str(extract_dir)
        except zipfile.BadZipFile:
            meta["zip_error"] = "bad_zip"
    return meta


def main() -> int:
    run = start_run("tse_ckan", "tse.candidatos_2022")
    max_per_pkg = int(os.getenv("TSE_MAX_RESOURCES", "2"))
    out = bronze_dir("tse_ckan")
    print(f"bronze -> {out} run={run['ingestion_run_id']}")
    all_files = []
    packages_meta = []

    for pkg_id in PACKAGES:
        try:
            pkg = package_show(pkg_id)
        except Exception as e:
            print(f"fail package {pkg_id}: {e}", file=sys.stderr)
            packages_meta.append({"id": pkg_id, "error": str(e)})
            continue
        write_json(out / f"package_{pkg_id}.json", pkg)
        resources = pick_resources(pkg, max_files=max_per_pkg)
        pkg_dir = out / pkg_id
        pkg_dir.mkdir(exist_ok=True)
        downloaded = []
        for res in resources:
            url = res["url"]
            fname = Path(url).name or f"{res.get('id', 'res')}.bin"
            # limpar querystring no nome
            fname = fname.split("?")[0]
            dest = pkg_dir / fname
            try:
                meta = download_file(url, dest)
                meta["resource_name"] = res.get("name")
                meta["package"] = pkg_id
                downloaded.append(meta)
                all_files.append(meta)
            except Exception as e:
                print(f"  fail download {url}: {e}", file=sys.stderr)
                downloaded.append({"url": url, "error": str(e), "package": pkg_id})
        packages_meta.append(
            {
                "id": pkg_id,
                "title": pkg.get("title"),
                "resources_picked": len(resources),
                "downloaded": downloaded,
            }
        )

    write_manifest(
        out,
        "tse_ckan",
        all_files,
        extra={
            "packages": packages_meta,
            "fetched_at": utc_now(),
            "ingestion_run_id": run["ingestion_run_id"],
        },
    )
    write_raw_record(
        source_id="tse_ckan",
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=run["connector_version"],
        payload={"packages": packages_meta, "files": all_files},
        filename="tse_download_index.json",
        source_url=CKAN,
        dataset_id="tse.candidatos_2022",
    )
    append_event(
        "document.discovered",
        {
            "document_id": f"tse_ckan_{out.name}",
            "source": "tse_ckan",
            "path": str(out),
            "packages": [p["id"] for p in packages_meta],
        },
    )
    ok = sum(1 for f in all_files if "error" not in f)
    mark_ingested(
        "tse_ckan",
        run_id=run["ingestion_run_id"],
        counts={"arquivos": ok, "packages": len(packages_meta)},
        ok=bool(ok or packages_meta),
    )
    print(f"OK TSE: {ok} arquivos baixados em {out}")
    return 0 if ok or packages_meta else 1


if __name__ == "__main__":
    raise SystemExit(main())
