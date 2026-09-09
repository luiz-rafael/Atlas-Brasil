"""Probes de fingerprint remoto para skip-por-hash."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlparse


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def probe_fingerprint(probe: dict[str, Any]) -> str:
    """Calcula fingerprint. Levanta exceção em falha de rede (Airflow retenta)."""
    kind = (probe or {}).get("kind") or "always"
    if kind == "always":
        # muda a cada dia UTC → extract diário se agendado; force via ATLAS_FORCE_UPDATE
        from datetime import datetime, timezone

        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return sha256_text(f"always:{day}:{probe.get('salt', '')}")

    if kind == "http_head":
        return _http_head(probe["url"])
    if kind == "http_get_hash":
        return _http_get_hash(probe["url"])
    if kind == "ckan_package":
        return _ckan_package(probe["url"])
    if kind == "ftp_listing":
        return _ftp_listing(probe["host"], probe.get("path") or "/")
    if kind == "local_file_hash":
        return _local_file_hash(probe["path"])
    raise ValueError(f"probe.kind desconhecido: {kind}")


def _local_file_hash(path: str) -> str:
    """Fingerprint de arquivo local (mtime+size+prefixo) — skip se inalterado."""
    from pathlib import Path

    p = Path(path)
    if not p.is_absolute():
        root = Path(__file__).resolve().parents[2]
        p = root / path
    if not p.exists():
        return sha256_text(f"missing|{p.as_posix()}")
    st = p.stat()
    # lê até 1MB do início + metadados (arquivos grandes de lake)
    with p.open("rb") as f:
        head = f.read(1 * 1024 * 1024)
    return sha256_bytes(
        f"{p.as_posix()}|{st.st_size}|{int(st.st_mtime_ns)}|".encode() + head
    )


def _http_head(url: str) -> str:
    import httpx

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        r = client.head(url)
        if r.status_code >= 400:
            # alguns hosts não aceitam HEAD
            r = client.get(url, headers={"Range": "bytes=0-0"})
        etag = r.headers.get("etag") or r.headers.get("ETag") or ""
        lm = r.headers.get("last-modified") or r.headers.get("Last-Modified") or ""
        cl = r.headers.get("content-length") or r.headers.get("Content-Length") or ""
        if etag or lm or cl:
            return sha256_text(f"head|{url}|{etag}|{lm}|{cl}")
        # fallback: hash dos headers relevantes
        return sha256_text(f"head-fallback|{url}|{r.status_code}|{dict(r.headers)}")


def _http_get_hash(url: str) -> str:
    import httpx

    with httpx.Client(follow_redirects=True, timeout=120.0) as client:
        r = client.get(url)
        r.raise_for_status()
        # limita a 2MB para listagens
        body = r.content[: 2 * 1024 * 1024]
        return sha256_bytes(body)


def _ckan_package(url: str) -> str:
    import httpx

    with httpx.Client(follow_redirects=True, timeout=120.0) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()
        result = data.get("result") or data
        resources = result.get("resources") or []
        slim = [
            {
                "id": x.get("id"),
                "name": x.get("name"),
                "last_modified": x.get("last_modified") or x.get("metadata_modified"),
                "hash": x.get("hash"),
                "size": x.get("size"),
                "url": x.get("url"),
            }
            for x in resources
        ]
        payload = {
            "id": result.get("id") or result.get("name"),
            "metadata_modified": result.get("metadata_modified"),
            "resources": slim,
        }
        return sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def _ftp_listing(host: str, path: str) -> str:
    from ftplib import FTP

    names: list[str] = []
    ftp = FTP(host, timeout=120)
    try:
        ftp.login()
        ftp.cwd(path)
        names = sorted(ftp.nlst())
    finally:
        try:
            ftp.quit()
        except Exception:
            pass
    return sha256_text(f"ftp|{host}|{path}|{'|'.join(names)}")


def parse_probe_url_host(url: str) -> tuple[str, str]:
    p = urlparse(url)
    return p.hostname or "", p.path or "/"
