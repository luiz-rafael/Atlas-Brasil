#!/usr/bin/env python3
"""Roda só o bloco legislativo + remuneração macro → silver → gold."""

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
    from datetime import datetime

    y = datetime.now().year
    env.setdefault("LEG_ANOS", ",".join(str(a) for a in range(2022, y + 1)))
    env.setdefault("ATLAS_REPLACE_LEGACY_KB", "1")
    env.setdefault("ATLAS_HTTP_RPS", "2")

    steps = [
        ("ingest/camara_legislativo.py", "Câmara legislativo"),
        ("ingest/senado_legislativo.py", "Senado legislativo"),
        ("ingest/remuneracao_oficial.py", "Remuneração macro"),
        ("transform/silver_legislativo.py", "Silver"),
        ("transform/gold_legislativo_merge.py", "Gold"),
    ]
    for script, label in steps:
        print(f"\n=== {label} ===", flush=True)
        r = subprocess.run([PY, str(ROOT / script)], cwd=str(PROJECT), env=env)
        if r.returncode != 0:
            print(f"falhou {label} code={r.returncode}", file=sys.stderr)
            return r.returncode
    print("\nBloco legislativo concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
