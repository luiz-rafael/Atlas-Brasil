#!/usr/bin/env python3
"""
Receita Federal — Cadastro Nacional de Obras (CNO).

CKAN dados.gov frequentemente 401. Tenta links alternativos + ATLAS_CNO_FILE.
Silver filtra à fila cnpj_interest (evita dump nacional).
"""

from __future__ import annotations

import csv
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
    write_jsonl,
    write_manifest,
    write_raw_record,
)
from pipelines.ingest.receita_common import (  # noqa: E402
    company_id_from_cnpj,
    load_cnpj_interest,
    load_dotenv,
    only_cnpj14,
    scrape_download_links,
    try_urls,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

SOURCE_ID = "receita_cno"
DATASET_ID = "rfb.cno"
PORTAL = "https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-de-obras-cno"
CKAN = "https://dados.gov.br/api/3/action/package_show?id=cadastro-nacional-de-obras-cno"
ALT_PAGES = [
    "https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/cno",
    "https://www.gov.br/receitafederal/dados",
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos",
]
# Mirror histórico RFB (pode timeout) + share SERPRO+/Nextcloud (WebDAV)
# Token: defina ATLAS_SERPRO_CNO_SHARE_TOKEN no .env (não versionar).
KNOWN_ZIP_URLS = [
    "https://arquivos.receitafederal.gov.br/public.php/webdav/",
    "http://200.152.38.155/CNO/cno.zip",
    "https://200.152.38.155/CNO/cno.zip",
]
SERPRO_CNO_SHARE_TOKEN = os.getenv("ATLAS_SERPRO_CNO_SHARE_TOKEN", "").strip()
SERPRO_CNO_WEBDAV = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
SERPRO_CNO_META = os.getenv(
    "ATLAS_SERPRO_CNO_META_URL",
    "https://arquivos.receitafederal.gov.br/index.php/s/XEa8aE7wJdMGzkE",
)
SAMPLE_LIMIT = int(os.getenv("ATLAS_CNO_SAMPLE_LIMIT", "5000"))


def probe_urls() -> list[str]:
    urls: list[str] = list(KNOWN_ZIP_URLS)
    try:
        r = http_get(CKAN, timeout=60.0)
        if r.status_code == 200 and r.content:
            blob = r.json()
            for res in (blob.get("result") or {}).get("resources") or []:
                u = res.get("url")
                if u:
                    urls.append(u)
    except Exception:
        pass
    for page in ALT_PAGES:
        try:
            found = scrape_download_links(page, keywords=("cno", "obra", "csv", "zip", "xlsx"))
            for u in found:
                low = u.lower()
                if "cno" not in low and "obra" not in low:
                    continue
                if low.endswith(".pdf") or low.endswith(".pdf/view"):
                    continue
                if u.endswith("/view"):
                    u = u[: -len("/view")] + "/@@download/file"
                urls.append(u)
        except Exception:
            continue
    seen: set[str] = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _pick_cno_member(names: list[str]) -> str | None:
    preferred = [n for n in names if Path(n).name.lower() == "cno.csv"]
    if preferred:
        return preferred[0]
    csvs = [n for n in names if n.lower().endswith((".csv", ".txt")) and "total" not in n.lower()]
    return csvs[0] if csvs else None


def extract_csv_from_zip(path: Path, out_dir: Path) -> Path | None:
    """Extrai só o ponteiro do member preferido — preferir parse_cno_zip (stream)."""
    if not zipfile.is_zipfile(path):
        return None
    with zipfile.ZipFile(path) as zf:
        name = _pick_cno_member(zf.namelist())
        if not name:
            return None
        dest = out_dir / Path(name).name
        # stream copy (cno.csv ~880MB)
        with zf.open(name) as src, open(dest, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        return dest


def _ni_cnpj_from_row(flat: dict) -> str | None:
    """NI do responsável — CNPJ 14. Aceita encoding quebrado (responsavel/responsável)."""
    for k, v in flat.items():
        kl = k.lower()
        if "cnpj" in kl:
            c = only_cnpj14(v)
            if c:
                return c
        # "ni do responsável" / "ni do responsavel" / latin-1 mojibake
        if "ni" in kl and "respons" in kl:
            c = only_cnpj14(v)
            if c:
                return c
    return None


def parse_cno_csv(path: Path, interest: set[str]) -> tuple[list[dict], dict]:
    """Parse streaming de cno.csv (latin-1/utf-8)."""
    rows: list[dict] = []
    total = 0
    matched = 0
    with_cnpj = 0

    def _open_reader():
        for enc in ("latin-1", "utf-8", "cp1252"):
            try:
                f = open(path, "r", encoding=enc, newline="")
                sample = f.read(8192)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
                except csv.Error:
                    dialect = csv.excel
                    dialect.delimiter = "," if sample.count(",") >= sample.count(";") else ";"
                return csv.DictReader(f, dialect=dialect), f
            except Exception:
                continue
        raise ValueError("não abriu CSV CNO")

    reader, fh = _open_reader()
    try:
        for row in reader:
            total += 1
            flat = {str(k).lower().strip(): v for k, v in row.items() if k}
            cnpj = _ni_cnpj_from_row(flat)
            if cnpj:
                with_cnpj += 1
            cno_id = None
            for k, v in flat.items():
                if k.strip('"') == "cno" or k == "cno":
                    cno_id = str(v).strip() or None
                    break
            if not cno_id:
                for k, v in flat.items():
                    if k == "cno" or (k.startswith("cno") and "vincul" not in k and "cnae" not in k):
                        cno_id = str(v).strip() or None
                        if cno_id:
                            break
            mun = None
            for k, v in flat.items():
                if "municip" in k or k in ("cidade", "nm_municipio"):
                    mun = str(v).strip() or None
                    if mun:
                        break
            uf = None
            for k, v in flat.items():
                if k in ("estado", "uf") or k.endswith("estado"):
                    uf = str(v).strip() or None
                    if uf:
                        break
            nome = None
            for k, v in flat.items():
                if "empresarial" in k or k == "nome":
                    nome = str(v).strip() or None
                    if nome and "empresarial" in k:
                        break

            keep = False
            if interest:
                if cnpj and cnpj in interest:
                    keep = True
                    matched += 1
            else:
                if len(rows) < SAMPLE_LIMIT:
                    keep = True
            if not keep:
                continue
            rows.append(
                {
                    "cno_id": cno_id or f"cno_row_{total}",
                    "cnpj": cnpj,
                    "company_id": company_id_from_cnpj(cnpj),
                    "municipality": mun,
                    "uf": uf,
                    "nome_empresarial": nome,
                    "raw": {k: (str(v)[:200] if v is not None else None) for k, v in list(row.items())[:25]},
                    "fonte": SOURCE_ID,
                    "dataset_id": DATASET_ID,
                    "source_file": path.name,
                }
            )
            if not interest and len(rows) >= SAMPLE_LIMIT:
                break
    finally:
        fh.close()

    stats = {
        "csv_rows_scanned": total,
        "rows_with_cnpj14": with_cnpj,
        "interest_size": len(interest),
        "matched_interest": matched,
        "kept": len(rows),
        "mode": "interest" if interest else "sample",
    }
    return rows, stats


def parse_cno_zip(zip_path: Path, interest: set[str], out_dir: Path) -> tuple[list[dict], dict]:
    """Stream cno.csv de dentro do ZIP (latin-1)."""
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("não é zip")

    rows: list[dict] = []
    total = 0
    matched = 0
    with_cnpj = 0

    with zipfile.ZipFile(zip_path) as zf:
        name = _pick_cno_member(zf.namelist())
        if not name:
            raise ValueError("ZIP sem cno.csv")
        with zf.open(name) as raw:
            tw = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            reader = csv.DictReader(tw)
            for row in reader:
                total += 1
                flat = {str(k).lower().strip(): v for k, v in row.items() if k}
                cnpj = _ni_cnpj_from_row(flat)
                if cnpj:
                    with_cnpj += 1
                cno_id = None
                for k, v in flat.items():
                    if k == "cno":
                        cno_id = str(v).strip() or None
                        break
                mun = None
                for k, v in flat.items():
                    if "municip" in k:
                        mun = str(v).strip() or None
                        if mun:
                            break
                uf = None
                for k, v in flat.items():
                    if k in ("estado", "uf"):
                        uf = str(v).strip() or None
                        if uf:
                            break
                nome = None
                for k, v in flat.items():
                    if "empresarial" in k:
                        nome = str(v).strip() or None
                        break

                keep = False
                if interest:
                    if cnpj and cnpj in interest:
                        keep = True
                        matched += 1
                else:
                    if len(rows) < SAMPLE_LIMIT:
                        keep = True
                if not keep:
                    continue
                rows.append(
                    {
                        "cno_id": cno_id or f"cno_row_{total}",
                        "cnpj": cnpj,
                        "company_id": company_id_from_cnpj(cnpj),
                        "municipality": mun,
                        "uf": uf,
                        "nome_empresarial": nome,
                        "raw": {
                            k: (str(v)[:200] if v is not None else None)
                            for k, v in list(row.items())[:25]
                        },
                        "fonte": SOURCE_ID,
                        "dataset_id": DATASET_ID,
                        "source_file": name,
                    }
                )
                if not interest and len(rows) >= SAMPLE_LIMIT:
                    break

    stats = {
        "csv_rows_scanned": total,
        "rows_with_cnpj14": with_cnpj,
        "interest_size": len(interest),
        "matched_interest": matched,
        "kept": len(rows),
        "mode": "interest" if interest else "sample",
        "zip_member": name,
    }
    return rows, stats


def try_download(out: Path) -> tuple[Path | None, dict]:
    import os
    import shutil

    env_file = os.getenv("ATLAS_CNO_FILE", "").strip()
    if env_file:
        p = Path(env_file)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        if p.is_file():
            # evita duplicar ~330MB na memória: hardlink/copy para bronze
            dest = out / p.name
            if dest.resolve() != p.resolve():
                try:
                    if dest.exists():
                        dest.unlink()
                    os.link(p, dest)
                except OSError:
                    shutil.copy2(p, dest)
            return dest, {
                "via": "ATLAS_CNO_FILE",
                "file": dest.name,
                "bytes": dest.stat().st_size,
                "source_share": SERPRO_CNO_WEBDAV,
            }
        return None, {"via": "ATLAS_CNO_FILE", "error": f"arquivo inexistente: {env_file}"}

    # SERPRO+/Nextcloud WebDAV — só se ATLAS_SERPRO_CNO_SHARE_TOKEN estiver no .env
    import httpx

    dest = out / "cno.zip"
    serpro_err = "não tentado"
    if not SERPRO_CNO_SHARE_TOKEN:
        serpro_err = "ATLAS_SERPRO_CNO_SHARE_TOKEN não definido"
    else:
        try:
            with httpx.stream(
                "GET",
                SERPRO_CNO_WEBDAV,
                auth=(SERPRO_CNO_SHARE_TOKEN, ""),
                timeout=600.0,
                follow_redirects=True,
                verify=False,
                headers={"User-Agent": "AtlasBrasil/1.0"},
            ) as r:
                if r.status_code == 200:
                    n = 0
                    with open(dest, "wb") as f:
                        for chunk in r.iter_bytes(1024 * 1024):
                            f.write(chunk)
                            n += len(chunk)
                    magic = open(dest, "rb").read(2)
                    if n > 1000 and magic == b"PK":
                        return dest, {
                            "via": "serpro_webdav",
                            "url": SERPRO_CNO_WEBDAV,
                            "bytes": n,
                            "meta_share": SERPRO_CNO_META,
                        }
                    serpro_err = f"arquivo inválido bytes={n} magic={magic!r}"
                else:
                    serpro_err = f"HTTP {r.status_code}"
        except Exception as e:
            serpro_err = str(e)

    urls = probe_urls()
    if urls:
        path, meta = try_urls(urls[:10], out, filename="cno_download.bin", timeout=300.0, min_bytes=500)
        if path:
            return path, {**meta, "probed_urls": urls[:10]}
    return None, {
        "error": "CKAN 401/indisponível e download SERPRO/WebDAV falhou",
        "portal": PORTAL,
        "ckan": CKAN,
        "serpro": SERPRO_CNO_WEBDAV,
        "serpro_error": serpro_err,
        "hint": "Baixe cno.zip do share SERPRO e defina ATLAS_CNO_FILE",
    }


def main() -> int:
    load_dotenv()
    try:
        run = start_run(SOURCE_ID, DATASET_ID)
    except Exception as e:
        print(f"fail-soft start_run {SOURCE_ID}: {e}", file=sys.stderr)
        return 0

    out = bronze_dir(SOURCE_ID)
    file_path, meta_dl = try_download(out)
    meta = {
        "fetched_at": utc_now(),
        "portal": PORTAL,
        "ingestion_run_id": run["ingestion_run_id"],
        **meta_dl,
    }

    if not file_path:
        meta["status"] = "SKIPPED"
        meta["reason"] = (
            "Download CNO indisponível (CKAN 401 típico). "
            "Defina ATLAS_CNO_FILE apontando para ZIP/CSV do dados.gov.br "
            "(conjunto cadastro-nacional-de-obras-cno)."
        )
        write_json(out / "meta.json", meta)
        write_manifest(out, SOURCE_ID, [], extra=meta)
        mark_ingested(SOURCE_ID, run_id=run["ingestion_run_id"], counts={"rows": 0}, dataset_id=DATASET_ID, ok=True)
        print(
            "SKIPPED receita_cno: sem download. Use ATLAS_CNO_FILE=caminho/para/cno.zip|csv",
            flush=True,
        )
        return 0

    try:
        with open(file_path, "rb") as fh:
            magic = fh.read(4)
        interest = load_cnpj_interest()
        if zipfile.is_zipfile(file_path) or magic[:2] == b"PK":
            rows, stats = parse_cno_zip(file_path, interest, out)
        elif file_path.suffix.lower() == ".csv":
            rows, stats = parse_cno_csv(file_path, interest)
        else:
            raise ValueError("arquivo não é ZIP/CSV reconhecível")
    except Exception as e:
        meta["status"] = "SKIPPED"
        meta["parse_error"] = str(e)
        write_json(out / "meta.json", meta)
        mark_ingested(SOURCE_ID, run_id=run["ingestion_run_id"], counts={"rows": 0}, dataset_id=DATASET_ID, ok=True)
        print(f"SKIPPED {SOURCE_ID} parse: {e}", flush=True)
        return 0

    write_jsonl(out / "cno_extract.jsonl", rows)
    write_json(out / "meta.json", {**meta, "rows": len(rows), "status": "OK", "stats": stats})
    # ZIP ~330MB — não espelhar raw binário no lake; só meta + extract
    if file_path.stat().st_size < 50_000_000:
        write_raw_record(
            source_id=SOURCE_ID,
            ingestion_run_id=run["ingestion_run_id"],
            connector_version=run["connector_version"],
            payload=file_path.read_bytes(),
            filename=file_path.name,
            source_url=PORTAL,
            dataset_id=DATASET_ID,
        )
    write_manifest(out, SOURCE_ID, [{"file": file_path.name, "bytes": file_path.stat().st_size}], extra=meta)
    append_event("document.discovered", {"source": SOURCE_ID, "rows": len(rows), **stats})
    mark_ingested(
        SOURCE_ID,
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows), **{k: v for k, v in stats.items() if isinstance(v, int)}},
        dataset_id=DATASET_ID,
        ok=True,
    )
    print(f"OK {SOURCE_ID} rows={len(rows)} stats={stats} -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
