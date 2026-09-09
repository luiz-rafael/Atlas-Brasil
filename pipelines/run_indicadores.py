#!/usr/bin/env python3
"""Camada indicadores P0 — IBGE território + população UF → silver → gold."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent
ROOT = PIPELINES.parent


def run(script: str) -> int:
    print(f"\n=== {script} ===", flush=True)
    return subprocess.run(
        [sys.executable, "-u", str(PIPELINES / script)],
        cwd=str(ROOT),
    ).returncode


def main() -> int:
    os.environ.setdefault("ATLAS_REPLACE_LEGACY_KB", "1")
    steps = [
        "ingest/ibge_territorios.py",
        "ingest/ibge_sidra_populacao.py",
        "ingest/ibge_sidra_pib.py",
        "transform/silver_indicadores.py",
        "ingest/inep_ideb.py",
        "transform/silver_ideb.py",
        "ingest/siconfi_dca.py",
        "transform/silver_siconfi.py",
        "ingest/datasus_sim_sinasc.py",
        "transform/silver_datasus.py",
        "ingest/caged_mov.py",
        "transform/silver_caged.py",
        "transform/gold_indicadores_merge.py",
        "load/export_kb_web.py",
    ]
    fails = 0
    for s in steps:
        if run(s) != 0:
            fails += 1
            print(f"FALHA {s}", flush=True)
            break
    print(f"\nOK run_indicadores: falhas={fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
