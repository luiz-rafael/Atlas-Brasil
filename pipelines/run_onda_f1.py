#!/usr/bin/env python3
"""Onda F1 — coletores + silver + (opcional) perfis + gold merge SEMPRE por último."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
PY = sys.executable

# Gold F1 merge deve ser a ÚLTIMA etapa que grava KB.
STEPS = [
    ("ingest/tse_bens.py", "TSE bens"),
    ("ingest/tse_prestacao.py", "TSE prestacao"),
    ("ingest/pncp_api.py", "PNCP"),
    ("ingest/transferegov_api.py", "Transferegov"),
    ("ingest/camara_orgaos.py", "Camara orgaos"),
    ("transform/silver_f1.py", "Silver F1"),
]


def run(script: str, label: str) -> int:
    print(f"\n=== {label} ===")
    r = subprocess.run([PY, str(ROOT / script)], cwd=str(PROJECT), env=os.environ.copy())
    if r.returncode != 0:
        print(f"aviso: {label} code={r.returncode}", file=sys.stderr)
    return r.returncode


def main() -> int:
    codes = [run(s, lab) for s, lab in STEPS]

    # Reaplica perfis já coletados sem recoleta (seguro com F1).
    if os.getenv("F1_MERGE_PERFIS", "1") == "1":
        codes.append(run("transform/merge_perfis_gold.py", "Merge perfis → gold"))

    codes.append(run("transform/gold_f1_merge.py", "Gold F1 merge (final)"))
    codes.append(run("transform/er_casas_tse.py", "ER casas ↔ TSE bens"))

    sys.path.insert(0, str(PROJECT))
    from pipelines.common import write_json
    from pipelines.registry import coverage_report

    cov = coverage_report()
    write_json(ROOT / "reports" / "coverage_f1.json", cov)
    print("\nOnda F1 concluida. coverage -> pipelines/reports/coverage_f1.json")
    return 0 if any(c == 0 for c in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
