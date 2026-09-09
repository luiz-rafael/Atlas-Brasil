#!/usr/bin/env python3
"""Silver transações tributárias — eventos administrativos (não LEGAL_CASE)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "receita_transacao_tributaria"
    if not base.exists():
        return None
    for d in sorted([p for p in base.iterdir() if p.is_dir()], reverse=True):
        if (d / "tax_transaction_extract.jsonl").exists():
            return d
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
        print("SKIPPED silver_receita_transacao: bronze ausente", flush=True)
        return 0

    extract = bronze / "tax_transaction_extract.jsonl"
    rows = read_jsonl(extract) if extract.exists() else []
    meta_path = bronze / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    if meta.get("status") == "SKIPPED" and not rows:
        print(
            f"SKIPPED silver_receita_transacao: {meta.get('reason') or 'sem dados estruturados'}",
            flush=True,
        )
        return 0

    now = utc_now()
    silver = [{**r, "retrieved_at": now, "semantic": "ADMINISTRATIVE_TAX_SETTLEMENT"} for r in rows]
    sil = LAKE / "silver" / "fiscal"
    sil.mkdir(parents=True, exist_ok=True)
    write_jsonl(sil / "tax_transaction_latest.jsonl", silver)
    write_jsonl(sil / f"tax_transaction_{day_stamp()}.jsonl", silver)
    write_json(
        sil / "tax_transaction_meta.json",
        {"rows": len(silver), "updated_at": now, "nota": "Não é LEGAL_CASE"},
    )
    print(f"OK silver_receita_transacao rows={len(silver)} -> {sil}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
