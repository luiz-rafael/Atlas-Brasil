#!/usr/bin/env python3
"""
CLI do pipeline CNJ remuneração de magistrados.

CHECK SOURCE → DISCOVER FILES → DOWNLOAD → RAW → VALIDATE → BRONZE
→ NORMALIZE → SILVER → RESOLVE MAGISTRATE → GOLD → QUALITY CHECK → PUBLISH

Uso:
  python -m src.pipelines.cnj.compensation.run --stage all
  python -m src.pipelines.cnj.compensation.run --stage discover
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402
from src.connectors.cnj.compensation.courts import DATASET_ID, SOURCE_ID  # noqa: E402
from src.connectors.cnj.compensation.discover import discover_sources  # noqa: E402
from src.connectors.cnj.compensation.download import download_discovered  # noqa: E402
from src.pipelines.cnj.compensation.bronze import bronze_dir, build_bronze  # noqa: E402
from src.pipelines.cnj.compensation.gold import write_gold, write_silver  # noqa: E402
from src.pipelines.cnj.compensation.normalize import normalize_rows  # noqa: E402
from src.pipelines.cnj.compensation.quality import build_coverage, run_quality  # noqa: E402
from src.pipelines.cnj.compensation.quarantine import persist_quarantine  # noqa: E402
from src.pipelines.cnj.compensation.resolve import resolve_magistrates  # noqa: E402

STAGES = (
    "discover",
    "download",
    "bronze",
    "silver",
    "resolve",
    "gold",
    "quality",
    "publish",
    "all",
)


def _run_dir(run_id: str) -> Path:
    d = bronze_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_run_id() -> str | None:
    base = LAKE / "bronze" / SOURCE_ID
    if not base.exists():
        return None
    runs = sorted([p.name for p in base.iterdir() if p.is_dir()], reverse=True)
    for name in runs:
        if (base / name / "discovery.json").exists() or (base / name / "bronze_rows.jsonl").exists():
            return name
    return runs[0] if runs else None


def stage_discover(run_id: str) -> dict:
    discovery = discover_sources()
    out = _run_dir(run_id)
    write_json(out / "discovery.json", discovery)
    write_json(out / "layout_incompatibilities.json", discovery.get("incompatibilities") or [])
    print(
        json.dumps(
            {
                "stage": "discover",
                "listing_hash": discovery.get("listing_hash"),
                "counts": discovery.get("counts"),
                "incompatibilities": len(discovery.get("incompatibilities") or []),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return discovery


def stage_download(run_id: str, discovery: dict | None = None) -> dict:
    if discovery is None:
        discovery = _load_json(_run_dir(run_id) / "discovery.json")
    result = download_discovered(discovery, run_id=run_id)
    write_json(_run_dir(run_id) / "download.json", result)
    print(json.dumps({"stage": "download", "counts": result.get("counts")}, ensure_ascii=False), flush=True)
    return result


def stage_bronze(run_id: str, download: dict | None = None) -> dict:
    if download is None:
        download = _load_json(_run_dir(run_id) / "download.json")
    result = build_bronze(download, run_id=run_id)
    print(json.dumps({"stage": "bronze", "counts": result.get("counts")}, ensure_ascii=False), flush=True)
    return result


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def stage_silver_resolve_gold(run_id: str, bronze: dict | None = None) -> dict:
    out = _run_dir(run_id)
    if bronze is None:
        bronze = {
            "rows": _read_jsonl(out / "bronze_rows.jsonl"),
            "quarantine": _read_jsonl(out / "quarantine.jsonl"),
            "layouts": (_load_json(out / "bronze_meta.json").get("layouts") if (out / "bronze_meta.json").exists() else []),
        }
    retrieved_at = utc_now()
    normalized = normalize_rows(bronze.get("rows") or [], retrieved_at=retrieved_at, dataset_id=DATASET_ID)
    resolved = resolve_magistrates(normalized["compensations"])
    quarantine = list(bronze.get("quarantine") or []) + normalized["quarantine"] + resolved["quarantine"]
    persist_quarantine(quarantine, run_id=run_id)

    discovery = _load_json(out / "discovery.json") if (out / "discovery.json").exists() else {}
    download = _load_json(out / "download.json") if (out / "download.json").exists() else {}

    quality = run_quality(
        magistrates=resolved["magistrates"],
        compensations=resolved["compensations"],
        components=normalized["components"],
        quarantine=quarantine,
        layouts=bronze.get("layouts") or [],
        discovery=discovery,
    )
    coverage = build_coverage(
        discovery=discovery,
        download=download,
        quality=quality,
        magistrates=resolved["magistrates"],
        compensations=resolved["compensations"],
    )
    write_silver(
        run_id=run_id,
        magistrates=resolved["magistrates"],
        compensations=resolved["compensations"],
        components=normalized["components"],
        quarantine=quarantine,
    )
    write_gold(
        run_id=run_id,
        magistrates=resolved["magistrates"],
        compensations=resolved["compensations"],
        components=normalized["components"],
        coverage=coverage,
        quality=quality,
        incompatibilities=list(discovery.get("incompatibilities") or [])
        + [
            {
                "code": "LAYOUT",
                "layout_id": k,
                "sheets": v,
            }
            for k, v in (quality.get("coverage") or {}).get("layouts", {}).items()
        ],
    )
    write_json(out / "quality.json", quality)
    write_json(out / "coverage.json", coverage)
    print(
        json.dumps(
            {
                "stage": "gold",
                "quality_ok": quality.get("ok"),
                "coverage": {
                    "courts": coverage.get("courts_found"),
                    "periods": coverage.get("periods_found"),
                    "status": coverage.get("coverage_status"),
                },
                "counts": {
                    "magistrates": len(resolved["magistrates"]),
                    "compensations": len(resolved["compensations"]),
                    "components": len(normalized["components"]),
                    "quarantine": len(quarantine),
                },
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return {
        "quality": quality,
        "coverage": coverage,
        "counts": {
            "magistrates": len(resolved["magistrates"]),
            "compensations": len(resolved["compensations"]),
            "components": len(normalized["components"]),
            "quarantine": len(quarantine),
        },
        "listing_hash": discovery.get("listing_hash"),
    }


def run_all(run: dict) -> dict:
    run_id = run["ingestion_run_id"]
    discovery = stage_discover(run_id)
    download = stage_download(run_id, discovery)
    bronze = stage_bronze(run_id, download)
    result = stage_silver_resolve_gold(run_id, bronze)
    ok = bool(result["quality"].get("ok"))
    mark_ingested(
        SOURCE_ID,
        run_id=run_id,
        counts={
            **(result.get("counts") or {}),
            "found": (discovery.get("counts") or {}).get("files"),
            "processed": (result.get("counts") or {}).get("compensations"),
            "quarantined": (result.get("counts") or {}).get("quarantine"),
            "ok": (result.get("counts") or {}).get("compensations"),
        },
        ok=ok,
        dataset_id=DATASET_ID,
        last_hash=discovery.get("listing_hash"),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline CNJ remuneração de magistrados")
    parser.add_argument("--stage", choices=STAGES, default="all")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)

    if args.stage == "all":
        run = start_run(SOURCE_ID, DATASET_ID)
        run_all(run)
        return 0

    run_id = args.run_id or _latest_run_id()
    if not run_id:
        run = start_run(SOURCE_ID, DATASET_ID)
        run_id = run["ingestion_run_id"]
        write_json(_run_dir(run_id) / "run.json", run)

    if args.stage == "discover":
        stage_discover(run_id)
    elif args.stage == "download":
        stage_download(run_id)
    elif args.stage == "bronze":
        stage_bronze(run_id)
    elif args.stage in {"silver", "resolve", "gold", "quality", "publish"}:
        stage_silver_resolve_gold(run_id)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
