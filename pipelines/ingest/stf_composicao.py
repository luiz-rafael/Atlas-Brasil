#!/usr/bin/env python3
"""
Composição do STF — seed curado dos ministros em exercício.

Fonte: portal STF / cobertura pública (set/2026: 10 titulares + 1 vaga
após aposentadoria de Luís Roberto Barroso e rejeição da indicação Messias).

Não mistura com ingest/stf.py (notícias).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    bronze_dir,
    utc_now,
    write_json,
    write_jsonl,
    write_manifest,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

FONTE_STF = "https://portal.stf.jus.br/composicao/"

INSTITUICAO = {
    "id": "inst_stf",
    "tipo": "instituicao",
    "nome": "Supremo Tribunal Federal",
    "tags": ["judiciario", "tribunal_superior", "stf"],
    "fonte_url": FONTE_STF,
}

# Composição em exercício (set/2026) — 10 ministros; cadeira Barroso vaga.
MINISTROS_STF = [
    {
        "id": "p_stf_fachin",
        "nome": "Edson Fachin",
        "cargo_label": "Ministro do STF (Presidente)",
        "tags_extra": ["presidente_stf"],
    },
    {
        "id": "p_stf_gilmar",
        "nome": "Gilmar Mendes",
        "cargo_label": "Ministro do STF (Decano)",
        "tags_extra": ["decano"],
    },
    {
        "id": "p_stf_carmen",
        "nome": "Cármen Lúcia",
        "cargo_label": "Ministra do STF",
    },
    {
        "id": "p_stf_toffoli",
        "nome": "Dias Toffoli",
        "cargo_label": "Ministro do STF",
    },
    {
        "id": "p_stf_fux",
        "nome": "Luiz Fux",
        "cargo_label": "Ministro do STF",
    },
    {
        "id": "p_stf_moraes",
        "nome": "Alexandre de Moraes",
        "cargo_label": "Ministro do STF",
    },
    {
        "id": "p_stf_nunes",
        "nome": "Nunes Marques",
        "cargo_label": "Ministro do STF",
    },
    {
        "id": "p_stf_mendonca",
        "nome": "André Mendonça",
        "cargo_label": "Ministro do STF",
    },
    {
        "id": "p_stf_zanin",
        "nome": "Cristiano Zanin",
        "cargo_label": "Ministro do STF",
    },
    {
        "id": "p_stf_dino",
        "nome": "Flávio Dino",
        "cargo_label": "Ministro do STF",
    },
]


def main() -> int:
    run = start_run("stf_composicao", "stf.composicao")
    out = bronze_dir("stf_composicao")
    pessoas = []
    for m in MINISTROS_STF:
        tags = ["judiciario", "ministro_stf", "no_poder", "seed_stf"]
        tags.extend(m.get("tags_extra") or [])
        pessoas.append(
            {
                "id": m["id"],
                "tipo": "pessoa",
                "nome": m["nome"],
                "cargo": "ministro_stf",
                "cargo_atual": m["cargo_label"],
                "cargo_label": m["cargo_label"],
                "no_poder": True,
                "fonte_url": FONTE_STF,
                "tags": tags,
                "fetched_at": utc_now(),
            }
        )

    write_jsonl(out / "pessoas_stf.jsonl", pessoas)
    write_json(out / "instituicao.json", {**INSTITUICAO, "fetched_at": utc_now()})
    write_json(
        out / "resumo.json",
        {
            "fetched_at": utc_now(),
            "ministros": len(pessoas),
            "vagas_abertas": 1,
            "nota": "Composição set/2026: 10 titulares; vaga Barroso em aberto",
            "fonte_url": FONTE_STF,
        },
    )
    write_manifest(
        out,
        "stf_composicao",
        [
            {"file": "pessoas_stf.jsonl", "count": len(pessoas)},
            {"file": "instituicao.json", "count": 1},
        ],
        extra={"ingestion_run_id": run["ingestion_run_id"]},
    )
    mark_ingested(
        "stf_composicao",
        run_id=run["ingestion_run_id"],
        counts={"ministros": len(pessoas), "vagas": 1},
        ok=True,
    )
    print(f"OK stf_composicao: ministros={len(pessoas)} (vaga=1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
