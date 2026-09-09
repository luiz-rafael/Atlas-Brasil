#!/usr/bin/env python3
"""Após SIH terminar: silver → gold → iceberg → serving (refresh)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERM = Path(
    r"C:\Users\k13ra\.cursor\projects\c-Users-k13ra-OneDrive-Documentos-AntiSistema\terminals\906030.txt"
)


def sih_done() -> bool:
    if not TERM.exists():
        return False
    text = TERM.read_text(encoding="utf-8", errors="replace")
    return "exit_code:" in text and "OK DATASUS SIH" in text


def run(argv: list[str]) -> int:
    print(f"\n>>> {' '.join(argv)}", flush=True)
    return subprocess.run(argv, cwd=str(ROOT)).returncode


def main() -> int:
    print("aguardando SIH (terminal 906030)…", flush=True)
    for _ in range(360):  # até ~3h com sleep 30s
        if sih_done():
            break
        time.sleep(30)
    else:
        print("timeout aguardando SIH", file=sys.stderr)
        return 1

    steps = [
        [sys.executable, "-u", "pipelines/transform/silver_datasus_sih.py"],
        [sys.executable, "-u", "pipelines/transform/gold_indicadores_merge.py"],
        [sys.executable, "-u", "pipelines/transform/iceberg_indicadores.py"],
        [sys.executable, "-u", "pipelines/load/serving_to_postgres.py"],
    ]
    for s in steps:
        rc = run(s)
        if rc != 0:
            print(f"falhou {s}: {rc}", file=sys.stderr)
            return rc
    print("SIH + serving refresh OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
