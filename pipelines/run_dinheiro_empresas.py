#!/usr/bin/env python3
"""
Onda Dinheiro / Empresas — FASE 3–4 do doc adição funcionaidades.md

Ordem:
1) despesas parlamentares (Câmara) com fornecedores
2) CGU emendas (autores no poder primeiro)
3) silver CGU
4) merge gold: perfis → F1 → CGU

Não regenera onda1/legislativo (preserva o que já está no gold).
"""

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
    env.setdefault("PERFIL_DESPESA_ANOS", "2024,2025")
    env.setdefault("DESPESA_MAX_PAGES", "5")
    env.setdefault("PERFIL_SKIP_GOLD", "1")  # gold só no merge_perfis
    env.setdefault("PERFIL_REFRESH_EMPTY_DESPESAS", "1")
    env.setdefault("PERFIL_LIMIT", "120")  # ativos primeiro; 0 = todos
    env.setdefault("CGU_EMENDA_AUTOR_LIMIT", "600")
    env.setdefault("CGU_EMENDA_MAX_PAGES", "4")
    env.setdefault("CGU_EMENDA_ANOS", "2023,2024,2025,2026")

    steps = [
        ("ingest/camara_despesas_bulk.py", "Cota parlamentar Câmara (CSV anual)"),
        ("ingest/senado_despesas_ceaps.py", "CEAPS Senado (CSV anual)"),
        ("ingest/enrich_perfis.py", "Despesas / perfis Câmara (API complemento)"),
        ("ingest/cgu_portal.py", "CGU emendas + sanções"),
        ("transform/silver_cgu.py", "Silver CGU"),
        ("transform/merge_perfis_gold.py", "Gold: despesas + fornecedores"),
        ("transform/gold_f1_merge.py", "Gold: contratos / empresas PNCP"),
        ("transform/gold_cgu_merge.py", "Gold: emendas → políticos"),
    ]

    codes = []
    for script, label in steps:
        print(f"\n=== {label} ===", flush=True)
        r = subprocess.run([PY, "-u", str(ROOT / script)], cwd=str(PROJECT), env=env)
        codes.append(r.returncode)
        if r.returncode != 0:
            print(f"FALHA {label} code={r.returncode}", file=sys.stderr)
            # continua: merges posteriores ainda ajudam parcialmente

    bad = sum(1 for c in codes if c != 0)
    print(f"\nOK run_dinheiro_empresas: steps={len(steps)} falhas={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
