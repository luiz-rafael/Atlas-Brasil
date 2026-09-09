"""Helpers compartilhados dos DAGs ATLAS (Airflow só orquestra)."""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from airflow.operators.bash import BashOperator
from airflow.operators.python import ShortCircuitOperator

ATLAS_ROOT = os.getenv("ATLAS_ROOT", "/opt/atlas")
PYTHON = os.getenv("ATLAS_PYTHON", "python")

DEFAULT_ARGS = {
    "owner": "atlas",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=6),
}


def bash_pipeline(task_id: str, script: str, env_exports: str = "") -> BashOperator:
    cmd = f"cd {ATLAS_ROOT} && {env_exports} {PYTHON} -u {script}".strip()
    return BashOperator(task_id=task_id, bash_command=cmd, cwd=ATLAS_ROOT)


def bash_check_update(dataset_id: str) -> BashOperator:
    """Roda check_source_update (exit 2 = probe fail → retry)."""
    script = "pipelines/ops/check_source_update.py"
    cmd = f"cd {ATLAS_ROOT} && {PYTHON} -u {script} --dataset {dataset_id}"
    return BashOperator(
        task_id=f"check_{dataset_id}",
        bash_command=cmd,
        cwd=ATLAS_ROOT,
    )


def should_run_extract(dataset_id: str, **context: Any) -> bool:
    """ShortCircuit: True se RUN ou force; False se SKIPPED."""
    if os.getenv("ATLAS_FORCE_UPDATE", "").lower() in ("1", "true", "yes"):
        return True
    env_path = os.path.join(
        ATLAS_ROOT, "data", "lake", "meta", f"update_{dataset_id}.env"
    )
    log_hint = f"/tmp/atlas_check_{dataset_id}.log"
    # lê env file gerado pelo check
    if os.path.isfile(env_path):
        text = open(env_path, encoding="utf-8").read()
        if "ATLAS_UPDATE=RUN" in text:
            return True
        if "ATLAS_UPDATE=SKIPPED" in text:
            return False
    if os.path.isfile(log_hint):
        text = open(log_hint, encoding="utf-8").read()
        if "ATLAS_UPDATE=SKIPPED" in text:
            return False
        if "ATLAS_UPDATE=RUN" in text:
            return True
    # se check não rodou / sem arquivo → não extrai (seguro)
    return False


def short_circuit_on_hash(dataset_id: str) -> ShortCircuitOperator:
    return ShortCircuitOperator(
        task_id=f"gate_{dataset_id}",
        python_callable=should_run_extract,
        op_kwargs={"dataset_id": dataset_id},
        ignore_downstream_trigger_rules=True,
    )


def bash_commit_hash(dataset_id: str, source_id: str) -> BashOperator:
    """Após extract OK: grava last_hash do pending."""
    cmd = (
        f"cd {ATLAS_ROOT} && {PYTHON} -u -c \""
        f"from pipelines.registry import commit_pending_hash; "
        f"commit_pending_hash('{source_id}', '{dataset_id}')\""
    )
    return BashOperator(task_id=f"commit_hash_{dataset_id}", bash_command=cmd, cwd=ATLAS_ROOT)
