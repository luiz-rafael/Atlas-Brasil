"""
Factory: gera 1 DAG por dataset do catálogo + meta-DAGs de domínio.

Catálogo: /opt/atlas/pipelines/catalog/datasets.yaml (repo montado).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

ATLAS_ROOT = os.getenv("ATLAS_ROOT", "/opt/atlas")
sys.path.insert(0, ATLAS_ROOT)

from atlas_common import (  # noqa: E402
    DEFAULT_ARGS,
    bash_commit_hash,
    bash_pipeline,
    short_circuit_on_hash,
)
from atlas_common import bash_check_update  # noqa: E402

# carrega catálogo
_catalog = None


def _load():
    global _catalog
    if _catalog is not None:
        return _catalog
    # preferir loader do repo
    try:
        from pipelines.catalog import load_catalog

        _catalog = load_catalog(Path(ATLAS_ROOT) / "pipelines" / "catalog" / "datasets.yaml")
    except Exception:
        import yaml

        path = Path(ATLAS_ROOT) / "pipelines" / "catalog" / "datasets.yaml"
        _catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _catalog


def _make_dataset_dag(ds: dict) -> DAG:
    dag_id = ds["dag_id"]
    dataset_id = ds["id"]
    source_id = ds["source_id"]
    schedule = ds.get("schedule")
    tags = list(ds.get("tags") or [])
    tags.append("atlas-catalog")

    dag = DAG(
        dag_id=dag_id,
        description=f"Atlas dataset {dataset_id} ({source_id})",
        default_args=DEFAULT_ARGS,
        start_date=datetime(2026, 1, 1),
        schedule=schedule,
        catchup=False,
        tags=tags,
        max_active_runs=1,
    )
    with dag:
        check = bash_check_update(dataset_id)
        gate = short_circuit_on_hash(dataset_id)
        extract = bash_pipeline(
            f"extract_{dataset_id}",
            ds["ingest"],
            env_exports=(
                f"ATLAS_DATASET_ID={dataset_id} "
                f"ATLAS_CATALOG_SOURCE_ID={source_id}"
            ),
        )
        commit = bash_commit_hash(dataset_id, source_id)
        check >> gate >> extract >> commit

        prev = commit
        for i, script in enumerate(ds.get("downstream") or []):
            tid = f"down_{i}_{Path(script).stem}"
            t = bash_pipeline(tid, script, env_exports="ATLAS_REPLACE_LEGACY_KB=1")
            prev >> t
            prev = t
    return dag


def _make_domain_dag(domain_key: str, spec: dict) -> DAG:
    dag_id = spec["dag_id"]
    children = spec.get("children") or []
    # Domínios críticos (ex. indicadores): wait=True → barreira real entre filhos
    wait = bool(spec.get("wait_for_completion", False))
    poke = int(spec.get("poke_interval", 60) or 60)
    dag = DAG(
        dag_id=dag_id,
        description=f"Meta-DAG domínio {domain_key}"
        + (" (wait filhos)" if wait else ""),
        default_args=DEFAULT_ARGS,
        start_date=datetime(2026, 1, 1),
        schedule=spec.get("schedule"),
        catchup=False,
        tags=["atlas", "domain", domain_key]
        + (["wait-children"] if wait else []),
        max_active_runs=1,
    )
    with dag:
        prev = None
        for child in children:
            t = TriggerDagRunOperator(
                task_id=f"trigger_{child}",
                trigger_dag_id=child,
                wait_for_completion=wait,
                poke_interval=poke,
                reset_dag_run=True,
                conf={"triggered_by": dag_id},
            )
            if prev:
                prev >> t
            prev = t
    return dag


# Materializa DAGs no módulo (Airflow discovery)
_cat = _load()
for _ds in _cat.get("datasets") or []:
    if not _ds.get("dag_id"):
        continue
    if _ds.get("dedicated_dag"):
        continue
    globals()[_ds["dag_id"]] = _make_dataset_dag(_ds)

for _dom, _spec in (_cat.get("domains") or {}).items():
    if not _spec.get("dag_id"):
        continue
    globals()[_spec["dag_id"]] = _make_domain_dag(_dom, _spec)
