#!/usr/bin/env python3
"""Ingestor STF — coleta páginas públicas de notícias e grava RAW + evento Kafka."""

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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
RAW = LAKE / "bronze" / "stf"
KAFKA = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092")
TOPIC = os.getenv("KAFKA_TOPIC_DOCS", "document.discovered")

SEEDS = [
    "https://noticias.stf.jus.br/",
    "https://portal.stf.jus.br/noticias/",
]


def _slug(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def fetch(url: str) -> str | None:
    headers = {"User-Agent": "ATLAS-BRASIL-Ingestor/2.0 (+pesquisa documental)"}
    try:
        r = httpx.get(url, timeout=30.0, follow_redirects=True, headers=headers)
        if r.status_code != 200:
            return None
        return r.text
    except httpx.ConnectError:
        # alguns hosts STF falham SSL no Windows; retry sem verify
        try:
            r = httpx.get(
                url, timeout=30.0, follow_redirects=True, headers=headers, verify=False
            )
            if r.status_code == 200:
                return r.text
        except Exception as e:
            print(f"fail {url}: {e}", file=sys.stderr)
        return None
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
        if full.lower().endswith((".css", ".js", ".png", ".jpg", ".svg", ".ico")):
            continue
        if "stf.jus.br" in full and ("noticia" in full.lower() or "postsnoticias" in full.lower()):
            out.append(full)
    return list(dict.fromkeys(out))[:40]


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
        # fallback fila local
        q = LAKE / "events" / "document.discovered.jsonl"
        q.parent.mkdir(parents=True, exist_ok=True)
        with q.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(f"kafka fallback file: {e}")


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    seen = set()
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
            doc_id = f"stf_{_slug(url)}"
            path = RAW / f"{doc_id}.json"
            rec = {
                "id": doc_id,
                "fonte": "STF",
                "orgao": "STF",
                "nivel_fonte": "1_primaria",
                "tipo": "noticia_oficial",
                "titulo": extract_title(body),
                "url": url,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "html_bytes": len(body),
                "html_path": str(path.with_suffix(".html").relative_to(LAKE)),
            }
            path.with_suffix(".html").write_text(body, encoding="utf-8", errors="ignore")
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                from pipelines.ops.plug_datajud_discovery import append_text_discoveries

                n = append_text_discoveries(body, source="stf", url=url)
                if n:
                    print(f"  discovery +{n} NPU(s)")
            except Exception as e:
                print(f"discovery hook fail-soft: {e}", file=sys.stderr)
            publish_kafka(
                {
                    "event": "document.discovered",
                    "source": "stf",
                    "document_id": doc_id,
                    "url": url,
                    "titulo": rec["titulo"],
                    "ts": rec["collected_at"],
                }
            )
            saved += 1
            print(f"OK {doc_id} {rec['titulo'][:60]}")
    print(f"stf ingest saved={saved}")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
