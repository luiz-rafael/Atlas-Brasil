#!/usr/bin/env python3
"""Consumer Kafka/arquivo -> marca document.processed (stub de orquestração)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
KAFKA = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092")
TOPIC = os.getenv("KAFKA_TOPIC_DOCS", "document.discovered")
OUT = LAKE / "events" / "document.processed.jsonl"


def consume_file_fallback(limit: int = 50) -> int:
    src = LAKE / "events" / "document.discovered.jsonl"
    if not src.exists():
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    lines = src.read_text(encoding="utf-8").strip().splitlines()[-limit:]
    with OUT.open("a", encoding="utf-8") as f:
        for line in lines:
            ev = json.loads(line)
            ev2 = {
                "event": "document.processed",
                "document_id": ev.get("document_id"),
                "source": ev.get("source"),
                "status": "indexed_pending",
                "ts": time.time(),
            }
            f.write(json.dumps(ev2, ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> int:
    try:
        from kafka import KafkaConsumer

        c = KafkaConsumer(
            TOPIC,
            bootstrap_servers=KAFKA.split(","),
            auto_offset_reset="earliest",
            consumer_timeout_ms=5000,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )
        OUT.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with OUT.open("a", encoding="utf-8") as f:
            for msg in c:
                ev = msg.value
                ev2 = {
                    "event": "document.processed",
                    "document_id": ev.get("document_id"),
                    "source": ev.get("source"),
                    "status": "received",
                    "ts": time.time(),
                }
                f.write(json.dumps(ev2, ensure_ascii=False) + "\n")
                n += 1
        print(f"kafka consumed={n}")
        if n == 0:
            n = consume_file_fallback()
            print(f"file fallback processed={n}")
        return 0
    except Exception as e:
        n = consume_file_fallback()
        print(f"kafka fail ({e}); file processed={n}")
        return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
