#!/usr/bin/env python3
"""FASE 7 histórico — TSE consulta_cand 1982–2018 + merge governadores."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent
ROOT = PIPELINES.parent

# Spec §40 lista 1982–2022; TSE CKAN só publica consulta_cand a partir de 1994
# (1982/86/90: só legendas/vagas — sem microdados de candidatos ELEITO).
HIST_PACKAGES = (
    "candidatos-1994,candidatos-1998,candidatos-2002,candidatos-2006,"
    "candidatos-2010,candidatos-2014,candidatos-2018"
)


def run(script: str, env: dict | None = None) -> int:
    print(f"\n=== {script} ===", flush=True)
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, "-u", str(PIPELINES / script)],
        cwd=str(ROOT),
        env=e,
    ).returncode


def main() -> int:
    os.environ.setdefault("ATLAS_REPLACE_LEGACY_KB", "1")
    fail = 0
    if run(
        "ingest/tse_bulk.py",
        {
            "TSE_PACKAGES": HIST_PACKAGES,
            "TSE_MAX_RESOURCES": "1",
            "TSE_BRASIL_ONLY": "1",
        },
    ):
        fail += 1
        print("FALHA ingest (seguindo se houver bronze parcial)", flush=True)
    for s in (
        "transform/silver_governadores.py",
        "transform/gold_governadores_merge.py",
        "load/export_kb_web.py",
    ):
        if run(s):
            fail += 1
            print(f"FALHA {s}", flush=True)
            break
    print(f"\nOK run_governadores_historico: falhas={fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
