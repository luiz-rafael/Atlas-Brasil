#!/usr/bin/env python3
"""
Lote completo de coleta indicadores (P0 + CAGED P1 + novos coletores) — arquitetura atual.

Roda ingestões com cobertura ampla, depois silver → gold → Iceberg → serving PG.
Respeita resume dos JSONL (SICONFI/CAGED já em curso podem continuar noutra shell).

Uso:
  python -u pipelines/ops/coleta_indicadores_full.py
  python -u pipelines/ops/coleta_indicadores_full.py --skip-ingest   # só transform/serving
  python -u pipelines/ops/coleta_indicadores_full.py --only-serving
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPELINES = ROOT / "pipelines"


def run(script: str, env: dict | None = None) -> int:
    e = os.environ.copy()
    e.setdefault("ATLAS_REPLACE_LEGACY_KB", "1")
    e.setdefault("ATLAS_PG_CONTROL", "1")
    e.setdefault(
        "DATABASE_URL",
        "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
    )
    if env:
        e.update(env)
    print(f"\n=== {script} ===", flush=True)
    return subprocess.run(
        [sys.executable, "-u", str(PIPELINES / script)],
        cwd=str(ROOT),
        env=e,
    ).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--only-serving", action="store_true")
    ap.add_argument("--skip-siconfi", action="store_true", help="SICONFI já a correr noutro processo")
    ap.add_argument("--skip-caged", action="store_true", help="CAGED já a correr noutro processo")
    args = ap.parse_args()

    fails = 0

    if args.only_serving:
        for s in (
            "transform/iceberg_indicadores.py",
            "lake_polars.py",
            "load/serving_to_postgres.py",
        ):
            if run(s) != 0:
                fails += 1
                break
        print(f"\nOK only-serving falhas={fails}")
        return 1 if fails else 0

    if not args.skip_ingest:
        # —— IBGE base ——
        for s, env in (
            ("ingest/ibge_territorios.py", None),
            ("ingest/ibge_sidra_populacao.py", None),
            ("ingest/ibge_sidra_pib.py", None),
            ("ingest/ibge_sidra_va.py", None),
            ("ingest/inep_ideb.py", None),
        ):
            if run(s, env) != 0:
                fails += 1
                print(f"FALHA {s}", flush=True)

        # —— DATASUS SIM/SINASC (FTP) ——
        if (
            run(
                "ingest/datasus_sim_sinasc.py",
                {
                    "ATLAS_DATASUS_YEAR_START": "2015",
                    "ATLAS_DATASUS_YEAR_END": "2023",
                },
            )
            != 0
        ):
            fails += 1

        # —— DATASUS homicídios ——
        if (
            run(
                "ingest/datasus_sim_homicidios.py",
                {
                    "ATLAS_HOMICIDIOS_YEAR_START": "2015",
                    "ATLAS_HOMICIDIOS_YEAR_END": "2022",
                },
            )
            != 0
        ):
            fails += 1

        # —— SICONFI mun anos restantes (UF já existe; resume JSONL) ——
        if not args.skip_siconfi:
            if (
                run(
                    "ingest/siconfi_dca.py",
                    {
                        "ATLAS_SICONFI_SKIP_UF": "1",
                        "ATLAS_SICONFI_MUN_YEARS": "2014,2015,2016,2017,2018,2019,2020,2021,2022,2023,2024",
                        "ATLAS_HTTP_RPS": os.getenv("ATLAS_HTTP_RPS", "3"),
                    },
                )
                != 0
            ):
                fails += 1

        # —— CAGED fluxo UF ——
        if not args.skip_caged:
            if (
                run(
                    "ingest/caged_mov.py",
                    {"ATLAS_CAGED_YEARS": "2020,2021,2022,2023,2024,2025"},
                )
                != 0
            ):
                fails += 1
            # município (extract separado; anos curtos por padrão do script)
            if (
                run(
                    "ingest/caged_mov_mun.py",
                    {"ATLAS_CAGED_YEARS": os.getenv("ATLAS_CAGED_YEARS", "2024,2025")},
                )
                != 0
            ):
                fails += 1

        # —— SNIS / RAIS / IDHM + novos coletores (fail-soft individual; exit 0 = skip) ——
        for s, env in (
            ("ingest/snis_ae.py", None),
            ("ingest/rais_estoque.py", None),
            ("ingest/idhm_atlas.py", None),
            ("ingest/inep_saeb.py", None),
            ("ingest/inep_censo_escolar.py", None),
            (
                "ingest/datasus_sih.py",
                {
                    "ATLAS_SIH_YEAR_START": os.getenv("ATLAS_SIH_YEAR_START", "2021"),
                    "ATLAS_SIH_YEAR_END": os.getenv("ATLAS_SIH_YEAR_END", "2022"),
                },
            ),
            (
                "ingest/datasus_sinan.py",
                {
                    "ATLAS_SINAN_YEAR_START": os.getenv("ATLAS_SINAN_YEAR_START", "2019"),
                    "ATLAS_SINAN_YEAR_END": os.getenv("ATLAS_SINAN_YEAR_END", "2023"),
                },
            ),
            ("ingest/cadunico.py", None),
            ("ingest/ana_agua.py", None),
            ("ingest/sinesp_cvli.py", None),
            ("ingest/fogo_cruzado.py", None),
        ):
            if run(s, env) != 0:
                fails += 1
                print(f"FALHA {s}", flush=True)

    # —— Silver / gold ——
    for s in (
        "transform/silver_indicadores.py",
        "transform/silver_ideb.py",
        "transform/silver_siconfi.py",
        "transform/silver_datasus.py",
        "transform/silver_datasus_homicidios.py",
        "transform/silver_caged.py",
        "transform/silver_snis.py",
        "transform/silver_rais.py",
        "transform/silver_idhm.py",
        "transform/silver_ibge_va.py",
        "transform/silver_inep_saeb.py",
        "transform/silver_inep_censo.py",
        "transform/silver_datasus_sih.py",
        "transform/silver_datasus_sinan.py",
        "transform/silver_cadunico.py",
        "transform/silver_ana.py",
        "transform/silver_sinesp_cvli.py",
        "transform/silver_fogo_cruzado.py",
        "transform/gold_indicadores_merge.py",
        "transform/iceberg_indicadores.py",
        "lake_polars.py",
        "load/serving_to_postgres.py",
        "load/export_kb_web.py",
    ):
        if run(s) != 0:
            fails += 1
            print(f"FALHA {s}", flush=True)
            break

    print(f"\nOK coleta_indicadores_full: falhas={fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
