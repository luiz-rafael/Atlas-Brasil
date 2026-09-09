#!/usr/bin/env python3
"""Onda 2+ — orquestra CGU, CNPJ, DOU (existente) e DataJud."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # pipelines/
PROJECT = ROOT.parent
PY = sys.executable

STEPS = [
    ("ingest/cgu_portal.py", "CGU Portal"),
    ("ingest/cnpj_rfb.py", "CNPJ RFB"),
    ("ingest/datajud_cnj.py", "DataJud CNJ"),
]

# DOU scrape HTML e lento — so sob demanda
if os.getenv("ONDA2_DOU", "0") == "1":
    STEPS.insert(2, ("ingest/dou.py", "DOU"))


def main() -> int:
    for script, label in STEPS:
        print(f"\n=== {label} ===")
        r = subprocess.run(
            [PY, str(ROOT / script)], cwd=str(PROJECT), env=os.environ.copy()
        )
        if r.returncode != 0:
            print(f"aviso: {label} code={r.returncode}", file=sys.stderr)
    print("\nOnda 2+ concluida (stubs ok sem chaves de API).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
