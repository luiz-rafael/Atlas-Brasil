#!/usr/bin/env python3
"""Helpers compartilhados dos coletores Receita Federal (complementar).

Não altera cnpj_rfb / arrecadação.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from pipelines.common import ROOT, http_get, sha1_bytes


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("$env:"):
            line = line[5:]
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def norm_text(s: str | None) -> str:
    t = unicodedata.normalize("NFKD", s or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().upper()


def only_digits(val: Any) -> str:
    return re.sub(r"\D", "", str(val or ""))


def only_cnpj14(val: Any) -> str | None:
    """CNPJ completo (14 dígitos). NÃO inventa a partir de raiz (8)."""
    d = only_digits(val)
    if len(d) == 14:
        return d
    if len(d) > 14:
        return d[-14:]
    return None


def company_id_from_cnpj(cnpj: str | None) -> str | None:
    c = only_cnpj14(cnpj)
    return f"co_{c}" if c else None


def to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(".", "").replace(",", ".")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in (".", "-", "-."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def year_from_header(cell: Any) -> int | None:
    if cell is None:
        return None
    if isinstance(cell, int) and 1900 <= cell <= 2100:
        return cell
    m = re.search(r"(19|20)\d{2}", str(cell))
    return int(m.group(0)) if m else None


def copy_env_file(env_var: str, out_dir: Path) -> tuple[Path | None, dict]:
    env_file = os.getenv(env_var, "").strip()
    if not env_file:
        return None, {}
    p = Path(env_file)
    if not p.is_file():
        return None, {"via": env_var, "error": f"arquivo inexistente: {env_file}"}
    dest = out_dir / p.name
    dest.write_bytes(p.read_bytes())
    return dest, {"via": env_var, "file": dest.name, "bytes": dest.stat().st_size}


def download_bytes(
    url: str,
    *,
    timeout: float = 180.0,
    min_bytes: int = 500,
) -> tuple[bytes | None, dict]:
    try:
        r = http_get(url, timeout=timeout)
        meta = {
            "url": url,
            "status_code": r.status_code,
            "bytes": len(r.content),
            "content_type": r.headers.get("content-type"),
            "sha1": sha1_bytes(r.content) if r.content else None,
        }
        if r.status_code != 200 or len(r.content) < min_bytes:
            return None, {**meta, "error": f"HTTP {r.status_code} bytes={len(r.content)}"}
        return r.content, meta
    except Exception as e:
        return None, {"url": url, "error": str(e)}


def download_to(
    url: str,
    dest: Path,
    *,
    timeout: float = 180.0,
    min_bytes: int = 500,
) -> tuple[Path | None, dict]:
    data, meta = download_bytes(url, timeout=timeout, min_bytes=min_bytes)
    if data is None:
        return None, meta
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest, {**meta, "file": dest.name, "via": "http"}


def try_urls(
    urls: list[str],
    out_dir: Path,
    *,
    filename: str,
    timeout: float = 180.0,
    min_bytes: int = 1000,
) -> tuple[Path | None, dict]:
    last: dict = {"candidates": urls}
    for url in urls:
        path, meta = download_to(
            url, out_dir / filename, timeout=timeout, min_bytes=min_bytes
        )
        if path:
            return path, meta
        last = {**last, **meta}
    return None, last


def scrape_download_links(page_url: str, *, keywords: tuple[str, ...] = ()) -> list[str]:
    """Extrai hrefs candidatos a download de uma página HTML."""
    data, meta = download_bytes(page_url, min_bytes=200, timeout=90.0)
    if not data:
        return []
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return []
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I)
    out: list[str] = []
    for h in hrefs:
        abs_u = urljoin(page_url, h)
        low = abs_u.lower()
        if keywords and not any(k in low for k in keywords):
            continue
        if any(
            x in low
            for x in (
                ".xlsx",
                ".csv",
                ".ods",
                ".zip",
                ".xls",
                "@@download",
            )
        ):
            out.append(abs_u)
    # dedupe preservando ordem
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def load_cnpj_interest(limit: int | None = None) -> set[str]:
    path = ROOT / "data" / "lake" / "queues" / "cnpj_interest.jsonl"
    if not path.is_file():
        return set()
    import json

    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        c = only_cnpj14(row.get("cnpj") or row.get("cnpj_completo"))
        if c:
            out.add(c)
        if limit and len(out) >= limit:
            break
    return out
