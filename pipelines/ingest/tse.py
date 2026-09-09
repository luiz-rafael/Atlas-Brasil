#!/usr/bin/env python3
"""Ingestor TSE — páginas públicas (notícias / dados eleitorais de entrada)."""

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
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
RAW = LAKE / "bronze" / "tse"
KAFKA = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092")
TOPIC = os.getenv("KAFKA_TOPIC_DOCS", "document.discovered")

SEEDS = [
    "https://www.tse.jus.br/",
    "https://www.tse.jus.br/comunicacao/noticias",
]


def _slug(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def fetch(url: str) -> str | None:
    try:
        r = httpx.get(
            url,
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "ATLAS-BRASIL-Ingestor/2.0 (+pesquisa documental)"},
        )
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
        if "tse.jus.br" in full and ("noticia" in full.lower() or "comunicacao" in full.lower()):
            out.append(full)
    return list(dict.fromkeys(out))[:40]


def extract_title(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html, flags=re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else "Sem título"


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
    except Exception:
        q = LAKE / "events" / "document.discovered.jsonl"
        q.parent.mkdir(parents=True, exist_ok=True)
        with q.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    saved = 0
    seen = set()
    for seed in SEEDS:
        html = fetch(seed)
        if not html:
            continue
        for url in extract_links(html, seed) or [seed]:
            if url in seen:
                continue
            seen.add(url)
            body = fetch(url)
            if not body:
                continue
            doc_id = f"tse_{_slug(url)}"
            path = RAW / f"{doc_id}.json"
            rec = {
                "id": doc_id,
                "fonte": "TSE",
                "orgao": "TSE",
                "nivel_fonte": "1_primaria",
                "tipo": "noticia_oficial",
                "titulo": extract_title(body),
                "url": url,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "html_path": str(path.with_suffix(".html").relative_to(LAKE)),
            }
            path.with_suffix(".html").write_text(body, encoding="utf-8", errors="ignore")
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            publish_kafka(
                {
                    "event": "document.discovered",
                    "source": "tse",
                    "document_id": doc_id,
                    "url": url,
                    "titulo": rec["titulo"],
                    "ts": rec["collected_at"],
                }
            )
            saved += 1
            print(f"OK {doc_id} {rec['titulo'][:60]}")
    print(f"tse ingest saved={saved}")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
