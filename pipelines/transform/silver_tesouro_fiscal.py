#!/usr/bin/env python3
"""
Silver Tesouro — consolida bronze fiscal → silver/fiscal/.

Lê o diretório bronze/tesouro/{day} mais recente e copia/normaliza
FISCAL_RESULT e PUBLIC_DEBT (+ revenue/expenditure).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402

FILES = [
    "fiscal_result_observation.jsonl",
    "public_debt_observation.jsonl",
    "public_debt_cost.jsonl",
    "public_budget_execution_revenue.jsonl",
    "public_budget_execution_expenditure.jsonl",
]


def latest_tesouro_day() -> Path | None:
    base = LAKE / "bronze" / "tesouro"
    if not base.exists():
        return None
    # prefer YYYY-MM-DD over run_ids
    days = sorted(
        [p for p in base.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == "-"],
        reverse=True,
    )
    return days[0] if days else None


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> int:
    bronze = latest_tesouro_day()
    if not bronze:
        print("bronze tesouro (day) ausente — rode ingestors primeiro", file=sys.stderr)
        return 1

    out = LAKE / "silver" / "fiscal"
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name in FILES:
        rows = load_jsonl(bronze / name)
        if not rows:
            continue
        dest = out / name
        # merge com existentes do mesmo arquivo (idempotente por id)
        existing = {r.get("id"): r for r in load_jsonl(dest) if r.get("id")}
        for r in rows:
            if r.get("id"):
                existing[r["id"]] = r
        merged = list(existing.values())
        write_jsonl(dest, merged)
        counts[name] = len(rows)

    write_json(
        out / "meta_tesouro_fiscal.json",
        {
            "em": utc_now(),
            "day": day_stamp(),
            "bronze": str(bronze),
            "counts": counts,
        },
    )
    print(f"OK silver_tesouro_fiscal: {counts}")
    return 0 if counts else 1


if __name__ == "__main__":
    raise SystemExit(main())
