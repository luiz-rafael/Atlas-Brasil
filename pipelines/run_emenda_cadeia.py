#!/usr/bin/env python3
"""FASE 4 — emenda → documentos → beneficiários (lote + gold + web)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent
ROOT = PIPELINES.parent


def run(script: str) -> int:
    print(f"\n=== {script} ===", flush=True)
    r = subprocess.run(
        [sys.executable, "-u", str(PIPELINES / script)],
        cwd=str(ROOT),
    )
    return r.returncode


def main() -> int:
    os.environ.setdefault("EMENDA_DOC_ANOS", "2024,2025,2026")
    os.environ.setdefault("EMENDA_DOC_DETAIL_PER_EMENDA", "6")
    os.environ.setdefault("EMENDA_DOC_SKIP_DONE", "1")
    os.environ.setdefault("EMENDA_DOC_ENRICH", "1")
    os.environ.setdefault("EMENDA_DOC_SLEEP", "0.1")
    os.environ.setdefault("ATLAS_REPLACE_LEGACY_KB", "1")

    steps = [
        "ingest/cgu_emenda_documentos.py",
        "transform/gold_emenda_cadeia_merge.py",
        "load/export_kb_web.py",
    ]
    fails = 0
    for s in steps:
        if run(s) != 0:
            fails += 1
            print(f"FALHA {s}", flush=True)
            break
    print(f"\nOK run_emenda_cadeia: falhas={fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
