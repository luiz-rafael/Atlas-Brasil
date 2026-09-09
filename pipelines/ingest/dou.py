#!/usr/bin/env python3
"""Ingestor DOU — Diário Oficial da União (páginas públicas in.gov.br)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    LAKE,
    write_raw_record,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

RAW = LAKE / "bronze" / "dou"
KAFKA = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092")
TOPIC = os.getenv("KAFKA_TOPIC_DOCS", "document.discovered")

SEEDS = [
    "https://www.in.gov.br/leiturajornal",
    "https://www.in.gov.br/consulta",
    "https://www.in.gov.br/web/guest/inicio",
]


def _slug(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def fetch(url: str) -> str | None:
    headers = {"User-Agent": "ATLAS-BRASIL-Ingestor/5.1 (+pesquisa documental DOU)"}
    try:
        r = httpx.get(url, timeout=40.0, follow_redirects=True, headers=headers)
        if r.status_code != 200:
            return None
        return r.text
    except Exception as e:
        print(f"fail {url}: {e}", file=sys.stderr)
        return None


def extract_links(html: str, base: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    out = []
    for h in hrefs:
        full = urljoin(base, h).split("#")[0]
        if not full.startswith(("http://", "https://")):
            continue
        if full.lower().endswith((".css", ".js", ".png", ".jpg", ".svg", ".ico", ".pdf")):
            continue
        low = full.lower()
        if "in.gov.br" in low and (
            "/web/dou" in low
            or "materia" in low
            or "leiturajornal" in low
            or "consulta" in low
            or "/dou/" in low
        ):
            out.append(full)
    return list(dict.fromkeys(out))[:50]


def extract_title(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html, flags=re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, flags=re.I)
    return m.group(1).strip() if m else "Sem título"


def publish_kafka(event: dict) -> None:
    try:
        from kafka import KafkaProducer

        p = KafkaProducer(
            bootstrap_servers=KAFKA.split(","),
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            request_timeout_ms=5000,
        )
        p.send(TOPIC, event)
        p.flush(5)
        p.close()
    except Exception as e:
        q = LAKE / "events" / "document.discovered.jsonl"
        q.parent.mkdir(parents=True, exist_ok=True)
        with q.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(f"kafka fallback file: {e}")


def main() -> int:
    run = start_run("dou", "dou.paginas")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = RAW / day
    out.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    saved = 0
    for seed in SEEDS:
        html = fetch(seed)
        if not html:
            continue
        links = extract_links(html, seed) or [seed]
        for url in links:
            if url in seen:
                continue
            seen.add(url)
            body = fetch(url)
            if not body:
                continue
            doc_id = f"dou_{_slug(url)}"
            path = out / f"{doc_id}.json"
            rec = {
                "id": doc_id,
                "fonte": "DOU",
                "orgao": "Imprensa Nacional / DOU",
                "nivel_fonte": "1_primaria",
                "tipo": "dou",
                "titulo": extract_title(body),
                "url": url,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "html_bytes": len(body),
                "html_path": str(path.with_suffix(".html").relative_to(LAKE)),
                "ingestion_run_id": run["ingestion_run_id"],
            }
            path.with_suffix(".html").write_text(body, encoding="utf-8", errors="ignore")
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            write_raw_record(
                source_id="dou",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=rec,
                filename=f"{doc_id}.json",
                source_url=url,
                dataset_id="dou.paginas",
                source_record_id=doc_id,
            )
            publish_kafka(
                {
                    "event": "document.discovered",
                    "source": "dou",
                    "document_id": doc_id,
                    "url": url,
                    "titulo": rec["titulo"],
                    "ts": rec["collected_at"],
                }
            )
            saved += 1
            print(f"OK {doc_id} {rec['titulo'][:60]}")
    mark_ingested("dou", run_id=run["ingestion_run_id"], counts={"docs": saved}, ok=saved > 0)
    print(f"dou ingest saved={saved}")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
