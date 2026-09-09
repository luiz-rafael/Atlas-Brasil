#!/usr/bin/env python3
"""FASE 7 — Governadores TSE → silver → gold → web."""

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
        "transform/silver_governadores.py",
        "transform/gold_governadores_merge.py",
        "load/export_kb_web.py",
    ]
    fails = 0
    for s in steps:
        if run(s) != 0:
            fails += 1
            print(f"FALHA {s}", flush=True)
            break
    print(f"\nOK run_governadores: falhas={fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
