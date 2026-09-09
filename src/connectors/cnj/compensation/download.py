"""Download imutável de arquivos descobertos (RAW + SHA-256)."""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.common import http_get, sha256_bytes, write_raw_record  # noqa: E402
from src.connectors.cnj.compensation.courts import (  # noqa: E402
    CONNECTOR_VERSION,
    DATASET_ID,
    SOURCE_ID,
)

MAX_FILES = int(os.getenv("ATLAS_CNJ_COMP_MAX_FILES", "300"))
MAX_BYTES = int(os.getenv("ATLAS_CNJ_COMP_MAX_BYTES", str(80 * 1024 * 1024)))


def _filename_from_url(url: str, fallback: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    return name or fallback or "download.bin"


def _read_local(path: str) -> bytes:
    return Path(path).read_bytes()


def _download_remote(url: str) -> bytes:
    r = http_get(url, timeout=120.0)
    r.raise_for_status()
    data = r.content
    if len(data) > MAX_BYTES:
        raise ValueError(f"arquivo excede ATLAS_CNJ_COMP_MAX_BYTES ({len(data)} bytes)")
    return data


def _extract_zip_members(raw: bytes, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with zipfile.ZipFile(__import__("io").BytesIO(raw)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in {".xlsx", ".xls", ".xlsm", ".ods", ".csv"}:
                continue
            target = dest / Path(info.filename).name
            target.write_bytes(zf.read(info))
            out.append(target)
    return out


def download_discovered(discovery: dict, *, run_id: str) -> dict:
    files = list(discovery.get("files") or [])[:MAX_FILES]
    saved: list[dict] = []
    errors: list[dict] = []

    for item in files:
        url = item.get("url")
        local_path = item.get("path")
        filename = item.get("filename") or "file.bin"
        try:
            if local_path and Path(local_path).is_file():
                payload = _read_local(local_path)
                source_url = item.get("original_source_url") or Path(local_path).as_uri()
            elif url and str(url).startswith("file:"):
                path = Path(urlparse(url).path)
                # Windows file URI
                if os.name == "nt" and str(url).startswith("file:///"):
                    path = Path(url[8:].replace("/", "\\"))
                payload = path.read_bytes()
                source_url = item.get("original_source_url") or url
            elif url:
                payload = _download_remote(url)
                source_url = item.get("original_source_url") or url
                filename = _filename_from_url(url, filename)
            else:
                raise ValueError("item sem url/path")

            digest = sha256_bytes(payload)
            meta = write_raw_record(
                source_id=SOURCE_ID,
                ingestion_run_id=run_id,
                connector_version=CONNECTOR_VERSION,
                payload=payload,
                filename=filename,
                source_url=source_url,
                dataset_id=DATASET_ID,
                content_type=_content_type(filename),
            )
            record = {
                **item,
                "raw_record_id": meta["raw_record_id"],
                "file_hash": meta["file_hash"],
                "file_path": meta["file_path"],
                "byte_size": meta["byte_size"],
                "retrieved_at": meta["retrieved_at"],
                "original_source_url": source_url,
            }
            saved.append(record)

            if filename.lower().endswith(".zip"):
                from pipelines.common import LAKE

                zip_dir = LAKE / "bronze" / SOURCE_ID / run_id / "unzipped" / digest[:12]
                members = _extract_zip_members(payload, zip_dir)
                for member in members:
                    inner = write_raw_record(
                        source_id=SOURCE_ID,
                        ingestion_run_id=run_id,
                        connector_version=CONNECTOR_VERSION,
                        payload=member.read_bytes(),
                        filename=member.name,
                        source_url=source_url,
                        dataset_id=DATASET_ID,
                        content_type=_content_type(member.name),
                    )
                    saved.append(
                        {
                            **item,
                            "filename": member.name,
                            "file_kind": "workbook",
                            "raw_record_id": inner["raw_record_id"],
                            "file_hash": inner["file_hash"],
                            "file_path": inner["file_path"],
                            "byte_size": inner["byte_size"],
                            "retrieved_at": inner["retrieved_at"],
                            "original_source_url": source_url,
                            "extracted_from_zip": digest,
                        }
                    )
        except Exception as exc:
            errors.append(
                {
                    "url": url,
                    "path": local_path,
                    "filename": filename,
                    "court_id": item.get("court_id"),
                    "error": str(exc),
                }
            )

    return {
        "run_id": run_id,
        "saved": saved,
        "errors": errors,
        "counts": {"saved": len(saved), "errors": len(errors), "listed": len(files)},
    }


def _content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
        ".xls": "application/vnd.ms-excel",
        ".ods": "application/vnd.oasis.opendocument.spreadsheet",
        ".csv": "text/csv",
        ".zip": "application/zip",
    }.get(suffix, "application/octet-stream")
