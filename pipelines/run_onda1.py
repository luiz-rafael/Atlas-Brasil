#!/usr/bin/env python3
"""Orquestra Onda 1: ingestão oficiais -> silver -> gold -> load."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # pipelines/
PROJECT = ROOT.parent
PY = sys.executable

STEPS = [
    ("ingest/camara_api.py", "Camara API"),
    ("ingest/senado_api.py", "Senado API"),
    ("ingest/tse_bulk.py", "TSE bulk"),
    ("transform/silver_politicos.py", "Silver"),
    ("transform/gold_kb.py", "Gold"),
    ("load/export_kb_json.py", "Export KB JSON"),
    ("load/to_postgres.py", "Postgres"),
    ("load/to_neo4j.py", "Neo4j"),
    ("ingest/enrich_perfis.py", "Enriquecer perfis"),
]


def run(script: str, label: str) -> int:
    path = ROOT / script
    print(f"\n=== {label} ({script}) ===")
    env = os.environ.copy()
    # defaults rapidos para MVP se nao setados
    env.setdefault("CAMARA_DETAIL_LIMIT", "0")
    env.setdefault("SENADO_DETAIL_LIMIT", "0")
    env.setdefault("TSE_MAX_RESOURCES", "2")
    env.setdefault("ATLAS_REPLACE_LEGACY_KB", "1")
    env.setdefault("NEO4J_SKIP", "0")
    r = subprocess.run([PY, str(path)], cwd=str(PROJECT), env=env)
    return r.returncode


def main() -> int:
    skip = {s.strip() for s in os.getenv("ONDA1_SKIP", "").split(",") if s.strip()}
    only = {s.strip() for s in os.getenv("ONDA1_ONLY", "").split(",") if s.strip()}
    codes = []
    for script, label in STEPS:
        key = script.split("/")[-1].replace(".py", "")
        if key in skip or script in skip:
            print(f"skip {label}")
            continue
        if only and key not in only and script not in only:
            continue
        code = run(script, label)
        codes.append(code)
        # TSE pode falhar por rede; nao abortar o resto se Casas ok
        if code != 0 and key in ("camara_api", "senado_api", "silver_politicos", "gold_kb"):
            print(f"ABORT em {label} (code={code})", file=sys.stderr)
            return code
    # index opensearch se existir
    idx = ROOT / "index_opensearch.py"
    if idx.exists() and os.getenv("ONDA1_OPENSEARCH", "0") == "1":
        subprocess.run([PY, str(idx)], cwd=str(PROJECT))
    print("\nOnda 1 concluida.")
    return 0 if all(c == 0 for c in codes if c is not None) else 1


if __name__ == "__main__":
    raise SystemExit(main())
