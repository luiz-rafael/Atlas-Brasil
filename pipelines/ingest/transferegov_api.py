#!/usr/bin/env python3
"""Transferegov — APIs publicas (parcerias / transferencias)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    append_event,
    bronze_dir,
    http_get,
    utc_now,
    write_jsonl,
    write_manifest,
    write_raw_record,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

BASE = os.getenv(
    "TRANSFEREGOV_API_BASE",
    "https://api-publica.transferegov.gestao.gov.br",
).rstrip("/")


def try_endpoints() -> tuple[list[dict], str]:
    # Host atual: modulo parcerias responde; especiais/fundoafundo podem 404.
    candidates = [
        "/parcerias/programa",
        "/parcerias/proposta?sg_uf_recebedor=DF",
        "/parcerias/proposta?sg_uf_recebedor=SP",
        "/especiais/plano_acao",
        "/transferencias-especiais/v1/transferencias?pagina=1&tamanhoPagina=50",
    ]
    for path in candidates:
        url = BASE + path
        try:
            r = http_get(url, headers={"Accept": "application/json"}, timeout=45.0)
            if r.status_code != 200:
                continue
            ct = r.headers.get("content-type", "")
            if "json" not in ct and not r.text.strip().startswith(("{", "[")):
                continue
            data = r.json()
            rows: list = []
            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict):
                rows = (
                    data.get("data")
                    or data.get("content")
                    or data.get("items")
                    or data.get("transferencias")
                    or []
                )
            if rows:
                return list(rows)[:150], url
        except Exception as e:
            print(f"  fail {url}: {e}", file=sys.stderr)
    return [], ""


def main() -> int:
    run = start_run("transferegov", "transferegov.especial")
    out = bronze_dir("transferegov")
    rows, url = try_endpoints()
    write_jsonl(out / "transferencias.jsonl", rows)
    write_raw_record(
        source_id="transferegov",
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=run["connector_version"],
        payload=rows or {"status": "empty", "base": BASE},
        filename="transferencias.jsonl",
        source_url=url or BASE,
        dataset_id="transferegov.especial",
    )
    write_manifest(
        out,
        "transferegov",
        [{"count": len(rows)}],
        extra={"fetched_at": utc_now(), "url": url, "ingestion_run_id": run["ingestion_run_id"]},
    )
    append_event("document.discovered", {"source": "transferegov", "count": len(rows)})
    mark_ingested(
        "transferegov",
        run_id=run["ingestion_run_id"],
        counts={"registros": len(rows)},
        ok=True,
    )
    print(f"OK Transferegov: {len(rows)} registros")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
