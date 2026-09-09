#!/usr/bin/env python3
"""Smoke: valida APIKey DataJud e enfileira 1 NPU real para enrich."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from pipelines.common import UA  # noqa: E402
from pipelines.legal.npu import format_npu, digits_only  # noqa: E402

BASE = "https://api-publica.datajud.cnj.jus.br"
KEY = os.getenv("ATLAS_DATAJUD_API_KEY", "").strip()
ALIAS = os.getenv("DATAJUD_SMOKE_ALIAS", "api_publica_stj")


def main() -> int:
    if not KEY:
        print("sem ATLAS_DATAJUD_API_KEY", file=sys.stderr)
        return 1
    url = f"{BASE}/{ALIAS}/_search"
    headers = {
        "Authorization": f"APIKey {KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,
    }
    body = {"size": 1, "query": {"match_all": {}}}
    r = httpx.post(url, headers=headers, json=body, timeout=60.0)
    print(f"status={r.status_code} alias={ALIAS}")
    if r.status_code != 200:
        print(r.text[:500], file=sys.stderr)
        return 1
    hits = ((r.json().get("hits") or {}).get("hits")) or []
    if not hits:
        print("sem hits", file=sys.stderr)
        return 1
    src = hits[0].get("_source") or {}
    num = str(src.get("numeroProcesso") or "")
    d = digits_only(num)
    npu = format_npu(d) or num
    qdir = ROOT / "data" / "lake" / "queues"
    qdir.mkdir(parents=True, exist_ok=True)
    qpath = qdir / "datajud_npus.jsonl"
    row = {
        "process_number": npu,
        "tribunal_alias": ALIAS.replace("api_publica_", ""),
        "seed_source_id": "datajud_smoke",
    }
    # append se ainda não estiver
    existing = qpath.read_text(encoding="utf-8") if qpath.exists() else ""
    if d not in existing:
        with qpath.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"OK smoke NPU={npu} movs={len(src.get('movimentos') or [])} → {qpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
