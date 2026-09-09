#!/usr/bin/env python3
"""
Ingest IBGE — localidades (Brasil / regiões / UFs) → bronze.

Fonte: https://servicodados.ibge.gov.br/api/v1/localidades/
P0 indicadores.md §2 / §57.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    bronze_dir,
    http_get,
    utc_now,
    write_json,
    write_manifest,
)
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402

BASE = "https://servicodados.ibge.gov.br/api/v1/localidades"


def fetch_json(path: str):
    r = http_get(f"{BASE}/{path}", timeout=90.0)
    r.raise_for_status()
    return r.json()


def main() -> int:
    run = start_run("ibge", "ibge.localidades")
    out = bronze_dir("ibge")
    print(f"bronze -> {out}", flush=True)

    regioes = fetch_json("regioes?orderBy=nome")
    estados = fetch_json("estados?orderBy=nome")
    print("  municípios …", flush=True)
    municipios = fetch_json("municipios")
    write_json(out / "regioes.json", regioes)
    write_json(out / "estados.json", estados)
    write_json(out / "municipios.json", municipios)
    write_json(
        out / "meta.json",
        {
            "em": utc_now(),
            "fonte": "ibge_localidades",
            "url": BASE,
            "regioes": len(regioes),
            "estados": len(estados),
            "municipios": len(municipios),
            "ingestion_run_id": run["ingestion_run_id"],
        },
    )
    write_manifest(
        out,
        "ibge",
        [
            {"file": "regioes.json", "n": len(regioes)},
            {"file": "estados.json", "n": len(estados)},
            {"file": "municipios.json", "n": len(municipios)},
        ],
        extra={"fetched_at": utc_now()},
    )
    mark_ingested(
        "ibge",
        run_id=run["ingestion_run_id"],
        counts={
            "regioes": len(regioes),
            "estados": len(estados),
            "municipios": len(municipios),
        },
        ok=True,
        dataset_id=dataset_id_from_env("ibge_territorios"),
    )
    print(
        f"OK IBGE localidades: regioes={len(regioes)} "
        f"estados={len(estados)} municipios={len(municipios)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
