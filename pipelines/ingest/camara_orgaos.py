#!/usr/bin/env python3
"""Camara — orgaos, frentes e membros."""

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

BASE = "https://dadosabertos.camara.leg.br/api/v2"
HEADERS = {"Accept": "application/json"}


def fetch_json(url: str) -> dict:
    r = http_get(url, headers=HEADERS, timeout=60.0)
    r.raise_for_status()
    return r.json()


def paginate(path: str, limit_pages: int) -> list[dict]:
    url = f"{BASE}{path}"
    rows: list[dict] = []
    page = 0
    while url and page < limit_pages:
        page += 1
        data = fetch_json(url)
        rows.extend(data.get("dados") or [])
        next_u = None
        for link in data.get("links") or []:
            if link.get("rel") == "next":
                next_u = link.get("href")
                break
        url = next_u
    return rows


def main() -> int:
    run = start_run("camara_orgaos", "camara.orgaos")
    out = bronze_dir("camara_orgaos")
    pages = int(os.getenv("CAMARA_ORGAOS_PAGES", "50"))
    membros_limit = int(os.getenv("CAMARA_FRENTES_MEMBROS_LIMIT", "15"))
    # -1 = todas as frentes
    orgaos = paginate("/orgaos?itens=100", pages)
    frentes = paginate("/frentes?itens=100", pages)
    alvo_frentes = frentes if membros_limit < 0 else frentes[:membros_limit]
    membros = []
    for i, fr in enumerate(alvo_frentes, 1):
        fid = fr.get("id")
        if not fid:
            continue
        try:
            data = fetch_json(f"{BASE}/frentes/{fid}/membros")
            for m in data.get("dados") or []:
                m["_frente_id"] = fid
                m["_frente_titulo"] = fr.get("titulo")
                membros.append(m)
        except Exception as e:
            print(f"  frente {fid}: {e}", file=sys.stderr)
        if i % 25 == 0:
            print(f"  frentes membros {i}/{len(alvo_frentes)}", flush=True)

    write_jsonl(out / "orgaos.jsonl", orgaos)
    write_jsonl(out / "frentes.jsonl", frentes)
    write_jsonl(out / "frente_membros.jsonl", membros)
    for name, payload, ds in [
        ("orgaos.jsonl", orgaos, "camara.orgaos"),
        ("frentes.jsonl", frentes, "camara.frentes"),
        ("frente_membros.jsonl", membros, "camara.frentes"),
    ]:
        write_raw_record(
            source_id="camara_orgaos",
            ingestion_run_id=run["ingestion_run_id"],
            connector_version=run["connector_version"],
            payload=payload,
            filename=name,
            source_url=BASE,
            dataset_id=ds,
        )

    write_manifest(
        out,
        "camara_orgaos",
        [
            {"file": "orgaos.jsonl", "count": len(orgaos)},
            {"file": "frentes.jsonl", "count": len(frentes)},
            {"file": "frente_membros.jsonl", "count": len(membros)},
        ],
        extra={
            "ingestion_run_id": run["ingestion_run_id"],
            "fetched_at": utc_now(),
            "frentes_com_membros": len(alvo_frentes),
        },
    )
    append_event(
        "document.discovered",
        {"source": "camara_orgaos", "orgaos": len(orgaos), "frentes": len(frentes)},
    )
    mark_ingested(
        "camara_orgaos",
        run_id=run["ingestion_run_id"],
        counts={"orgaos": len(orgaos), "frentes": len(frentes), "membros": len(membros)},
    )
    print(f"OK Camara orgaos={len(orgaos)} frentes={len(frentes)} membros={len(membros)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
