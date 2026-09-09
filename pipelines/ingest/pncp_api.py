#!/usr/bin/env python3
"""PNCP — contratos públicos (API consulta, paginado)."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    append_event,
    bronze_dir,
    http_get,
    write_jsonl,
    write_manifest,
    write_raw_record,
)
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402

BASE = os.getenv("PNCP_API_BASE", "https://pncp.gov.br/api/consulta").rstrip("/")


def fetch_page(ini: str, fim: str, pagina: int, tamanho: int) -> tuple[list[dict], str | None]:
    path = (
        f"/v1/contratos?dataInicial={ini}&dataFinal={fim}"
        f"&pagina={pagina}&tamanhoPagina={tamanho}"
    )
    url = BASE + path
    r = http_get(url, headers={"Accept": "application/json"}, timeout=90.0)
    if r.status_code != 200:
        return [], url
    data = r.json()
    rows: list = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data") or data.get("conteudo") or data.get("items") or []
        if isinstance(rows, dict):
            rows = rows.get("content") or []
    return list(rows), url


def try_fetch_contratos() -> tuple[list[dict], str]:
    hoje = datetime.now(timezone.utc).date()
    dias = int(os.getenv("PNCP_DIAS", "14"))
    max_pages = int(os.getenv("PNCP_MAX_PAGES", "20"))
    tamanho = int(os.getenv("PNCP_PAGE_SIZE", "50"))
    max_rows = int(os.getenv("PNCP_MAX_ROWS", "2000"))
    ini = (hoje - timedelta(days=dias)).strftime("%Y%m%d")
    fim = hoje.strftime("%Y%m%d")
    all_rows: list[dict] = []
    last_url = ""
    for page in range(1, max_pages + 1):
        try:
            rows, url = fetch_page(ini, fim, page, tamanho)
            last_url = url or last_url
            if not rows:
                print(f"  PNCP page={page} empty — stop", flush=True)
                break
            all_rows.extend(rows)
            print(
                f"  PNCP page={page} got={len(rows)} total={len(all_rows)}",
                flush=True,
            )
            if len(rows) < tamanho or len(all_rows) >= max_rows:
                break
        except Exception as e:
            print(f"  page {page} fail: {e}", file=sys.stderr)
            break
    return all_rows[:max_rows], last_url


def main() -> int:
    run = start_run("pncp", "pncp.contratos")
    out = bronze_dir("pncp")
    rows, url = try_fetch_contratos()
    write_jsonl(out / "contratos.jsonl", rows)
    write_raw_record(
        source_id="pncp",
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=run["connector_version"],
        payload=rows or {"status": "empty"},
        filename="contratos.jsonl" if rows else "empty.json",
        source_url=url or BASE,
        dataset_id="pncp.contratos",
    )
    write_manifest(
        out,
        "pncp",
        [{"file": "contratos.jsonl", "count": len(rows)}],
        extra={"ingestion_run_id": run["ingestion_run_id"], "source_url": url},
    )
    append_event("document.discovered", {"source": "pncp", "count": len(rows)})
    mark_ingested(
        "pncp",
        run_id=run["ingestion_run_id"],
        counts={"contratos": len(rows)},
        ok=True,
        dataset_id=dataset_id_from_env("pncp_api"),
    )
    print(f"OK PNCP: {len(rows)} contratos")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
