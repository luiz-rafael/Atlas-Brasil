"""Utilitários compartilhados dos pipelines de coleta oficial."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
UA = os.getenv(
    "ATLAS_USER_AGENT",
    "ATLAS-BRASIL-Ingestor/5.1 (+pesquisa documental oficial)",
)
RPS = float(os.getenv("ATLAS_HTTP_RPS", "2"))
_last_request = 0.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def day_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def bronze_dir(fonte: str, day: str | None = None) -> Path:
    d = LAKE / "bronze" / fonte / (day or day_stamp())
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def throttle() -> None:
    global _last_request
    gap = 1.0 / max(RPS, 0.1)
    now = time.monotonic()
    wait = gap - (now - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    follow_redirects: bool = True,
) -> httpx.Response:
    throttle()
    h = {"User-Agent": UA, **(headers or {})}
    return httpx.get(url, headers=h, timeout=timeout, follow_redirects=follow_redirects)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_event(event: str, payload: dict) -> None:
    out = LAKE / "events" / f"{event}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {**payload, "event": event, "ts": utc_now()}
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_manifest(
    outdir: Path, fonte: str, files: list[dict], extra: dict | None = None
) -> Path:
    man = {
        "fonte": fonte,
        "fetched_at": utc_now(),
        "files": files,
        **(extra or {}),
    }
    path = outdir / "manifest.json"
    write_json(path, man)
    return path


def slug_url(url: str) -> str:
    path = urlparse(url).path.replace("/", "_").strip("_") or "root"
    return f"{path[:40]}_{sha1_text(url)[:10]}"


def run_bronze_dir(source_id: str, run_id: str) -> Path:
    """Pasta RAW imutável por run."""
    d = LAKE / "bronze" / source_id / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_raw_record(
    *,
    source_id: str,
    ingestion_run_id: str,
    connector_version: str,
    payload: bytes | str | dict | list,
    filename: str,
    source_url: str | None = None,
    dataset_id: str | None = None,
    source_record_id: str | None = None,
    content_type: str | None = None,
) -> dict:
    """
    Grava payload bruto com SHA-256.
    Nao sobrescreve bytes existentes com mesmo hash no run.
    """
    outdir = run_bronze_dir(source_id, ingestion_run_id)
    if isinstance(payload, (dict, list)):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        content_type = content_type or "application/json"
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
        content_type = content_type or "text/plain; charset=utf-8"
    else:
        raw = payload

    digest = sha256_bytes(raw)
    safe_name = filename.replace("/", "_").replace("\\", "_")
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix or ".bin"
    file_path = outdir / f"{stem}_{digest[:12]}{suffix}"
    if not file_path.exists():
        file_path.write_bytes(raw)

    meta = {
        "raw_record_id": f"raw_{source_id}_{digest[:16]}",
        "source_id": source_id,
        "dataset_id": dataset_id,
        "source_record_id": source_record_id,
        "retrieved_at": utc_now(),
        "published_at": None,
        "updated_at": None,
        "source_url": source_url,
        "file_path": str(file_path.relative_to(LAKE)).replace("\\", "/"),
        "file_hash": digest,
        "hash_algo": "sha256",
        "connector_version": connector_version,
        "ingestion_run_id": ingestion_run_id,
        "content_type": content_type,
        "byte_size": len(raw),
    }
    with (outdir / "raw_index.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")

    # Storage-alvo (MinIO): espelho fail-soft. Local permanece fonte operacional nesta fase.
    try:
        from pipelines.storage.backend import MinioStorage, storage_backend_name

        backend = storage_backend_name()
        if backend in ("dual", "minio"):
            sto = MinioStorage()
            obj = sto.write_raw(
                source_id=source_id,
                run_id=ingestion_run_id,
                filename=file_path.name,
                data=raw,
                meta=meta,
                content_type=content_type,
            )
            meta["storage_backend"] = backend
            meta["storage_uri"] = obj.uri
            meta["storage_skipped"] = obj.skipped
            if obj.meta.get("error"):
                meta["storage_error"] = obj.meta["error"]
    except Exception as e:
        meta["storage_error"] = str(e)

    return meta
