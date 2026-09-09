#!/usr/bin/env python3
"""
Onda F2 — CGU (se chave) + PNCP/TG + silver/gold.
DataJud: enriquecimento por NPU (fila). Pula se ONDA2_SKIP_DATAJUD=1 ou sem chave/fila.
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
    """Carrega .env da raiz do projeto (não sobrescreve env já setada)."""
    path = PROJECT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    load_dotenv()
    env = os.environ.copy()
    env.setdefault("PNCP_DIAS", "14")
    env.setdefault("PNCP_MAX_PAGES", "3")
    env.setdefault("PNCP_PAGE_SIZE", "50")
    env.setdefault("ATLAS_REPLACE_LEGACY_KB", "1")
    env.setdefault("ONDA2_SKIP_DATAJUD", "1")

    steps = [
        ("ingest/cgu_portal.py", "CGU Portal"),
        ("ingest/cnpj_rfb.py", "CNPJ RFB manifesto"),
    ]
    if env.get("ONDA2_SKIP_DATAJUD", "1") != "1":
        steps.append(("ingest/datajud_cnj.py", "DataJud"))
    else:
        print("\n=== DataJud ===\npulado (ONDA2_SKIP_DATAJUD=1)")

    steps += [
        ("ingest/pncp_api.py", "PNCP ampliado"),
        ("ingest/transferegov_api.py", "Transferegov"),
        ("ingest/tse_prestacao.py", "TSE prestacao"),
        ("ingest/cgu_legal.py", "CGU legal (leniência filtrada)"),
        ("transform/silver_f1.py", "Silver F1/F2"),
        ("transform/silver_empresas.py", "Silver empresas CNPJ"),
        ("transform/silver_cgu.py", "Silver CGU"),
        ("transform/merge_perfis_gold.py", "Merge perfis"),
        ("transform/gold_f1_merge.py", "Gold F1 merge"),
        ("transform/gold_cgu_merge.py", "Gold CGU merge"),
        ("transform/gold_legal_cases.py", "Gold LEGAL_CASE mentioned_in"),
        ("transform/er_casas_tse.py", "ER casas ↔ TSE bens"),
    ]

    codes = []
    for script, label in steps:
        print(f"\n=== {label} ===")
        r = subprocess.run([PY, str(ROOT / script)], cwd=str(PROJECT), env=env)
        codes.append(r.returncode)
        if r.returncode != 0:
            print(f"aviso: {label} code={r.returncode}", file=sys.stderr)

    sys.path.insert(0, str(PROJECT))
    from pipelines.common import write_json
    from pipelines.registry import coverage_report

    cov = coverage_report()
    write_json(ROOT / "reports" / "coverage_f2.json", cov)
    write_json(ROOT / "reports" / "coverage_f1.json", cov)
    print("\nOnda F2 concluida. coverage -> pipelines/reports/coverage_f2.json")
    return 0 if any(c == 0 for c in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
