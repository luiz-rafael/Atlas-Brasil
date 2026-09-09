"""SILVER resolvido → GOLD. Competência = evento; não é SCD2."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json, write_jsonl  # noqa: E402
from src.connectors.cnj.compensation.courts import SOURCE_ID  # noqa: E402


def gold_dir(run_id: str) -> Path:
    return LAKE / "gold" / "cnj_compensation" / run_id


def silver_dir(run_id: str) -> Path:
    return LAKE / "silver" / "cnj_compensation" / run_id


def write_silver(
    *,
    run_id: str,
    magistrates: list[dict],
    compensations: list[dict],
    components: list[dict],
    quarantine: list[dict],
) -> Path:
    out = silver_dir(run_id)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "magistrates.jsonl", magistrates)
    write_jsonl(out / "compensations.jsonl", compensations)
    write_jsonl(out / "components.jsonl", components)
    write_jsonl(out / "quarantine.jsonl", quarantine)
    write_json(
        out / "meta.json",
        {
            "run_id": run_id,
            "layer": "silver",
            "counts": {
                "magistrates": len(magistrates),
                "compensations": len(compensations),
                "components": len(components),
                "quarantine": len(quarantine),
            },
            "written_at": utc_now(),
        },
    )
    return out


def _latest_view(compensations: list[dict]) -> list[dict]:
    """Uma competência = um evento; a visão current pega o retrieved_at mais recente."""
    best: dict[tuple, dict] = {}
    for row in compensations:
        key = (
            row.get("magistrate_id"),
            row.get("court_id"),
            row.get("reference_year"),
            row.get("reference_month"),
        )
        prev = best.get(key)
        if prev is None or str(row.get("retrieved_at") or "") >= str(prev.get("retrieved_at") or ""):
            best[key] = row
    return list(best.values())


def write_gold(
    *,
    run_id: str,
    magistrates: list[dict],
    compensations: list[dict],
    components: list[dict],
    coverage: dict[str, Any],
    quality: dict[str, Any] | None = None,
    incompatibilities: list[dict] | None = None,
) -> Path:
    out = gold_dir(run_id)
    out.mkdir(parents=True, exist_ok=True)
    current = _latest_view(compensations)
    current_ids = {r["id"] for r in current}
    current_components = [c for c in components if c.get("compensation_id") in current_ids]

    # Remove campos internos de resolução do gold público
    public_comp = []
    for row in compensations:
        item = {
            k: v
            for k, v in row.items()
            if k not in {"row_key", "source_row"}
        }
        public_comp.append(item)

    write_jsonl(out / "magistrates.jsonl", magistrates)
    write_jsonl(out / "compensations.jsonl", public_comp)
    write_jsonl(out / "compensation_current.jsonl", current)
    write_jsonl(out / "components.jsonl", current_components)
    write_json(out / "coverage.json", coverage)
    if quality is not None:
        write_json(out / "quality.json", quality)
    write_json(out / "layout_incompatibilities.json", incompatibilities or [])
    write_json(
        out / "meta.json",
        {
            "run_id": run_id,
            "layer": "gold",
            "model": "MAGISTRATE_COMPENSATION is one observation per competence (not SCD2)",
            "editorial": (
                "gross_total não é subsídio; net_total não é bruto; "
                "indenização/retroativo separados; processo ≠ culpa; "
                "valor elevado não é irregularidade automática."
            ),
            "counts": {
                "magistrates": len(magistrates),
                "compensations": len(public_comp),
                "compensation_current": len(current),
                "components": len(current_components),
            },
            "written_at": utc_now(),
            "source_id": SOURCE_ID,
        },
    )
    latest = LAKE / "gold" / "cnj_compensation" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for name in (
        "magistrates.jsonl",
        "compensations.jsonl",
        "compensation_current.jsonl",
        "components.jsonl",
        "coverage.json",
        "layout_incompatibilities.json",
        "meta.json",
    ):
        src = out / name
        if src.exists():
            (latest / name).write_bytes(src.read_bytes())
    if quality is not None:
        (latest / "quality.json").write_bytes((out / "quality.json").read_bytes())
    return out
