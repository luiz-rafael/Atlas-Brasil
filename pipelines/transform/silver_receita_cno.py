#!/usr/bin/env python3
"""Silver CNO → cno_works_latest.jsonl (company_id só com CNPJ 14)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "receita_cno"
    if not base.exists():
        return None
    for d in sorted([p for p in base.iterdir() if p.is_dir()], reverse=True):
        if (d / "meta.json").exists():
            return d
    return None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("SKIPPED silver_receita_cno: bronze ausente", flush=True)
        return 0

    meta = json.loads((bronze / "meta.json").read_text(encoding="utf-8"))
    rows = read_jsonl(bronze / "cno_extract.jsonl")
    if meta.get("status") == "SKIPPED" and not rows:
        print(f"SKIPPED silver_receita_cno: {meta.get('reason') or 'sem dados'}", flush=True)
        return 0

    now = utc_now()
    silver = []
    with_co = 0
    for r in rows:
        cnpj = r.get("cnpj")
        company_id = r.get("company_id") if cnpj else None
        if company_id:
            with_co += 1
        silver.append(
            {
                **r,
                "cnpj": cnpj,
                "company_id": company_id,
                "retrieved_at": now,
                "semantic": "CNO_WORK",
            }
        )

    sil = LAKE / "silver" / "fiscal"
    sil.mkdir(parents=True, exist_ok=True)
    write_jsonl(sil / "cno_works_latest.jsonl", silver)
    write_jsonl(sil / f"cno_works_{day_stamp()}.jsonl", silver)
    write_json(
        sil / "cno_works_meta.json",
        {
            "rows": len(silver),
            "with_company_id": with_co,
            "stats": meta.get("stats"),
            "updated_at": now,
        },
    )
    print(f"OK silver_receita_cno rows={len(silver)} with_company={with_co} -> {sil}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
