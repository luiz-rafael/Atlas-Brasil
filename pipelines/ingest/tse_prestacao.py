#!/usr/bin/env python3
"""
TSE prestação de contas — prioriza ZIP de CANDIDATOS (FASE 2).

Baixa streaming para disco e extrai só CSVs relevantes:
  despesas_contratadas_candidatos_*.csv
  receitas_candidatos_*.csv

Env:
  TSE_PRESTACAO_PACKAGES  (default: pacote 2022 correto + 2024)
  TSE_PRESTACAO_MAX_MB    (default: 450)
  TSE_PRESTACAO_ONLY_CANDIDATOS=1
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
    UA,
    append_event,
    bronze_dir,
    http_get,
    throttle,
    utc_now,
    write_json,
    write_manifest,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

CKAN = "https://dadosabertos.tse.jus.br/api/3/action"
PACKAGES = [
    p.strip()
    for p in os.getenv(
        "TSE_PRESTACAO_PACKAGES",
        "dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2022,"
        "prestacao-de-contas-eleitorais-2024",
    ).split(",")
    if p.strip()
]

EXTRACT_PREFIXES = (
    "despesas_contratadas_candidatos",
    "receitas_candidatos",
)

# UFs grandes (SP/MG/BRASIL) passam de 150MB — default 220MB cobre SP
# BRASIL (~1.3GB) continua fora de propósito.


def _norm(s: str) -> str:
    return (
        (s or "")
        .lower()
        .replace("ç", "c")
        .replace("ã", "a")
        .replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
    )


def package_show(pkg_id: str) -> dict | None:
    try:
        r = http_get(f"{CKAN}/package_show?id={pkg_id}", timeout=90.0)
        if r.status_code != 200:
            return None
        body = r.json()
        return body.get("result") if body.get("success") else None
    except Exception:
        return None


def pick_resources(pkg: dict) -> list[dict]:
    """Prioriza prestação de candidatos; evita extrato bancário e órgãos."""
    only_cand = os.getenv("TSE_PRESTACAO_ONLY_CANDIDATOS", "1") == "1"
    scored: list[tuple[int, dict]] = []
    for res in pkg.get("resources") or []:
        name = _norm(res.get("name") or "")
        url = _norm(res.get("url") or "")
        blob = f"{name} {url}"
        if "extrato" in blob:
            continue
        if only_cand and "candidato" not in blob:
            continue
        if "orgao" in blob or "partido" in blob:
            continue
        score = 0
        if "candidato" in blob and "prestacao" in blob:
            score = 100
        elif "candidato" in blob and "despesa" in blob:
            score = 90
        elif "candidato" in blob:
            score = 80
        elif "despesa" in blob or "receita" in blob:
            score = 40
        if score:
            scored.append((score, res))
    scored.sort(key=lambda x: -x[0])
    limit = int(os.getenv("TSE_PRESTACAO_MAX", "2"))
    return [r for _, r in scored[:limit]]


def stream_download(url: str, dest: Path, max_mb: int) -> int:
    """Baixa para arquivo; retorna bytes. Levanta se passar do limite."""
    import httpx

    throttle()
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    limit = max_mb * 1_000_000
    with httpx.stream(
        "GET", url, headers={"User-Agent": UA}, timeout=600.0, follow_redirects=True
    ) as r:
        r.raise_for_status()
        cl = int(r.headers.get("content-length") or "0")
        if cl and cl > limit:
            raise RuntimeError(f"arquivo {cl} bytes > limite {limit}")
        with dest.open("wb") as f:
            for chunk in r.iter_bytes(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise RuntimeError(f"download abortado > {max_mb}MB")
                f.write(chunk)
    return written


def extract_candidato_csvs(zip_path: Path, out_csv: Path) -> list[str]:
    out_csv.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    max_csv = int(os.getenv("TSE_PRESTACAO_MAX_CSV_MB", "120")) * 1_000_000
    with zipfile.ZipFile(zip_path) as zf:
        for n in zf.namelist():
            low = n.lower().replace("\\", "/")
            base = Path(low).name
            if not base.endswith(".csv"):
                continue
            if not any(base.startswith(p) for p in EXTRACT_PREFIXES):
                continue
            info = zf.getinfo(n)
            if info.file_size > max_csv:
                print(f"  skip csv grande {base} ({info.file_size})", flush=True)
                continue
            target = out_csv / base
            if target.exists() and target.stat().st_size == info.file_size:
                extracted.append(base)
                continue
            print(f"  extraindo {base} …", flush=True)
            with zf.open(n) as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
            extracted.append(base)
    return extracted


def main() -> int:
    run = start_run("tse_prestacao", "tse.prestacao_candidatos")
    out = bronze_dir("tse_prestacao")
    csv_dir = out / "csv_candidatos"
    downloaded = 0
    extracted_all: list[str] = []
    meta_pkgs = []
    max_mb = int(os.getenv("TSE_PRESTACAO_MAX_MB", "450"))

    for pkg_id in PACKAGES:
        pkg = package_show(pkg_id)
        if not pkg:
            meta_pkgs.append({"id": pkg_id, "error": "not_found"})
            print(f"pacote não encontrado: {pkg_id}", file=sys.stderr)
            continue
        write_json(
            out / f"package_{pkg_id.replace('/', '_')[:80]}.json",
            {"id": pkg_id, "title": pkg.get("title")},
        )
        resources = pick_resources(pkg)
        print(f"{pkg_id}: {len(resources)} recurso(s) candidatos", flush=True)
        for res in resources:
            url = res.get("url")
            if not url:
                continue
            fname = Path(url.split("?")[0]).name or f"{res.get('id')}.zip"
            dest = out / fname
            try:
                if dest.exists() and dest.stat().st_size > 1_000_000:
                    print(f"já existe {fname} ({dest.stat().st_size} bytes)", flush=True)
                    nbytes = dest.stat().st_size
                else:
                    print(f"baixando {fname} (limite {max_mb}MB) …", flush=True)
                    nbytes = stream_download(url, dest, max_mb)
                    print(f"  ok {nbytes} bytes", flush=True)
                downloaded += 1
                if zipfile.is_zipfile(dest):
                    extracted_all.extend(extract_candidato_csvs(dest, csv_dir))
            except Exception as e:
                write_json(
                    out / f"skip_{fname}.json",
                    {"url": url, "error": str(e)},
                )
                print(f"fail {fname}: {e}", file=sys.stderr)
        meta_pkgs.append({"id": pkg_id, "resources": len(resources)})

    write_manifest(
        out,
        "tse_prestacao",
        [{"downloaded": downloaded, "csvs": len(set(extracted_all))}],
        extra={
            "packages": meta_pkgs,
            "extracted": sorted(set(extracted_all))[:80],
            "ingestion_run_id": run["ingestion_run_id"],
            "fetched_at": utc_now(),
        },
    )
    append_event("document.discovered", {"source": "tse_prestacao", "path": str(out)})
    mark_ingested(
        "tse_prestacao",
        run_id=run["ingestion_run_id"],
        counts={"arquivos": downloaded, "csvs_candidatos": len(set(extracted_all))},
        ok=downloaded > 0 or bool(extracted_all),
    )
    print(
        f"OK TSE prestacao candidatos: downloads={downloaded} "
        f"csvs={len(set(extracted_all))}"
    )
    return 0 if (downloaded or extracted_all) else 1


if __name__ == "__main__":
    raise SystemExit(main())
