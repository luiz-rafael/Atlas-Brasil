#!/usr/bin/env python3
"""
Pacote P3 estadual — segurança / saúde / educação / saneamento em nível UF.

NÃO usa Fogo Cruzado (API instável). Fontes nacionais agregadas a STATE:

  segurança  → IPEA AVIOL12_THOMIC → ind_cvli_per_100k (+ SIM já no silver)
  saúde      → SIH annual UF → ind_internacoes (+ SINAN/SIM já)
  educação   → Censo/matrículas UF (+ IDEB já)
  saneamento → SNIS mun → UF ponderado (+ ANA file opcional)

Uso:
  python -u pipelines/ops/p3_estadual.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

STEPS = [
    # (label, cmd_env, argv)
    ("CVLI IPEA", {}, [sys.executable, "-u", "pipelines/ingest/sinesp_cvli.py"]),
    ("silver CVLI", {}, [sys.executable, "-u", "pipelines/transform/silver_sinesp_cvli.py"]),
    ("SNIS silver UF", {}, [sys.executable, "-u", "pipelines/transform/silver_snis.py"]),
    (
        "SIH UF 2021-2023",
        {"ATLAS_SIH_YEAR_START": "2021", "ATLAS_SIH_YEAR_END": "2023"},
        [sys.executable, "-u", "pipelines/ingest/datasus_sih.py"],
    ),
    ("silver SIH", {}, [sys.executable, "-u", "pipelines/transform/silver_datasus_sih.py"]),
    ("Censo matrículas", {}, [sys.executable, "-u", "pipelines/ingest/inep_censo_escolar.py"]),
    ("silver Censo", {}, [sys.executable, "-u", "pipelines/transform/silver_inep_censo.py"]),
    (
        "SINAN dengue 2019-2023",
        {"ATLAS_SINAN_YEAR_START": "2019", "ATLAS_SINAN_YEAR_END": "2023"},
        [sys.executable, "-u", "pipelines/ingest/datasus_sinan.py"],
    ),
    ("silver SINAN", {}, [sys.executable, "-u", "pipelines/transform/silver_datasus_sinan.py"]),
]


def run_step(label: str, env_extra: dict, argv: list[str]) -> int:
    print(f"\n=== P3: {label} ===", flush=True)
    env = os.environ.copy()
    env.update(env_extra)
    # Fogo Cruzado explicitamente fora do P3
    env["ATLAS_SKIP_FOGO_CRUZADO"] = "1"
    p = subprocess.run(argv, cwd=str(ROOT), env=env)
    print(f"--- {label}: exit={p.returncode}", flush=True)
    return p.returncode


def main() -> int:
    print("P3 estadual — sem Fogo Cruzado", flush=True)
    codes = []
    for label, env_extra, argv in STEPS:
        codes.append(run_step(label, env_extra, argv))
    failed = sum(1 for c in codes if c not in (0,))
    print(f"\nP3 done: steps={len(codes)} non_zero={failed}", flush=True)
    # fail-soft: não derruba lote se algum SKIPPED retornou 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
