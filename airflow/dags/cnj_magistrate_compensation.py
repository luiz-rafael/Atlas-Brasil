"""DAG dedicada: remuneração de magistrados (CNJ). Airflow só orquestra."""

from __future__ import annotations

import os
import sys
from datetime import datetime

from airflow import DAG

ATLAS_ROOT = os.getenv("ATLAS_ROOT", "/opt/atlas")
sys.path.insert(0, ATLAS_ROOT)

from atlas_common import (  # noqa: E402
    DEFAULT_ARGS,
    bash_check_update,
    bash_commit_hash,
    bash_pipeline,
    short_circuit_on_hash,
)

DATASET = "cnj_magistrate_compensation"
SOURCE = "cnj_magistrate_compensation"
MODULE = "src.pipelines.cnj.compensation.run"

dag = DAG(
    dag_id="cnj_magistrate_compensation",
    description="CNJ — remuneração de magistrados (transparência de pessoal, não DataJud)",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 1, 1),
    schedule="0 8 2 * *",
    catchup=False,
    tags=["atlas", "pessoal", "cnj", "magistrados", "remuneracao"],
    max_active_runs=1,
)

with dag:
    check = bash_check_update(DATASET)
    gate = short_circuit_on_hash(DATASET)
    discover = bash_pipeline(
        "discover_files",
        f"-m {MODULE} --stage discover",
        env_exports=f"ATLAS_DATASET_ID={DATASET} ATLAS_CATALOG_SOURCE_ID={SOURCE}",
    )
    download = bash_pipeline("download_raw", f"-m {MODULE} --stage download")
    bronze = bash_pipeline("validate_bronze", f"-m {MODULE} --stage bronze")
    gold = bash_pipeline("normalize_resolve_gold", f"-m {MODULE} --stage gold")
    commit = bash_commit_hash(DATASET, SOURCE)
    check >> gate >> discover >> download >> bronze >> gold >> commit
