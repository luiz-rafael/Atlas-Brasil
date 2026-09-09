#!/usr/bin/env python3
"""FASE 2 — Campanhas TSE → fornecedores → empresas."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
PY = sys.executable


def load_dotenv() -> None:
    path = PROJECT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("$env:"):
            line = line[5:]
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    load_dotenv()
    env = os.environ.copy()
    env.setdefault("ATLAS_REPLACE_LEGACY_KB", "1")
    env.setdefault(
        "TSE_PRESTACAO_PACKAGES",
        "dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2022",
    )
    env.setdefault("TSE_PRESTACAO_ONLY_CANDIDATOS", "1")
    env.setdefault("TSE_PRESTACAO_MAX", "1")
    env.setdefault("TSE_PRESTACAO_MAX_MB", "450")
    env.setdefault("TSE_PRESTACAO_MAX_CSV_MB", "150")

    steps = [
        ("ingest/tse_prestacao.py", "Download TSE candidatos"),
        ("transform/silver_campanhas.py", "Silver campanhas"),
        ("transform/gold_campanhas_merge.py", "Gold campanhas → empresas"),
    ]
    bad = 0
    for script, label in steps:
        print(f"\n=== {label} ===", flush=True)
        r = subprocess.run([PY, "-u", str(ROOT / script)], cwd=str(PROJECT), env=env)
        if r.returncode != 0:
            print(f"FALHA {label}", file=sys.stderr)
            bad += 1
    print(f"\nOK run_campanhas: falhas={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
