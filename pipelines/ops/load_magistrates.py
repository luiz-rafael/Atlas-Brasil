#!/usr/bin/env python3
"""Carrega magistrates + compensation do gold CNJ → Postgres.

Uso:
  python -u pipelines/ops/load_magistrates.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LATEST = ROOT / "data" / "lake" / "gold" / "cnj_compensation" / "latest"
DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
)


def _iter(path: Path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def main() -> int:
    import psycopg

    mag_path = LATEST / "magistrates.jsonl"
    # arquivo real: compensations.jsonl (plural) ou compensation_current.jsonl
    comp_path = LATEST / "compensation_current.jsonl"
    if not comp_path.is_file():
        comp_path = LATEST / "compensations.jsonl"
    if not mag_path.is_file():
        # fallback dated folder
        parent = LATEST.parent
        dirs = sorted(parent.glob("20*"), reverse=True)
        if dirs:
            mag_path = dirs[0] / "magistrates.jsonl"
            cand = dirs[0] / "compensation_current.jsonl"
            comp_path = cand if cand.is_file() else dirs[0] / "compensations.jsonl"
    if not mag_path.is_file():
        print("FAIL: magistrates.jsonl ausente")
        return 1

    print(f"mag={mag_path.name} comp={comp_path.name if comp_path.is_file() else 'ABSENT'}")

    n_m = n_c = 0
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            mag_ids: set[str] = set()
            for r in _iter(mag_path):
                mid = r.get("magistrate_id")
                if not mid:
                    continue
                mag_ids.add(mid)
                cur.execute(
                    """
                    INSERT INTO magistrates (
                      magistrate_id, normalized_name, court_id, position, source_id,
                      source_person_identifier, display_name, resolution_method,
                      resolution_confidence
                    ) VALUES (
                      %(magistrate_id)s, %(normalized_name)s, %(court_id)s, %(position)s,
                      %(source_id)s, %(source_person_identifier)s, %(display_name)s,
                      %(resolution_method)s, %(resolution_confidence)s
                    )
                    ON CONFLICT (magistrate_id) DO UPDATE SET
                      display_name = EXCLUDED.display_name,
                      position = EXCLUDED.position,
                      updated_at = NOW()
                    """,
                    {
                        "magistrate_id": mid,
                        "normalized_name": r.get("normalized_name") or mid,
                        "court_id": r.get("court_id") or "unknown",
                        "position": r.get("position"),
                        "source_id": r.get("source_id") or "cnj_magistrate_compensation",
                        "source_person_identifier": r.get("source_person_identifier"),
                        "display_name": r.get("display_name") or r.get("normalized_name"),
                        "resolution_method": r.get("resolution_method"),
                        "resolution_confidence": r.get("resolution_confidence"),
                    },
                )
                n_m += 1
                if n_m % 500 == 0:
                    conn.commit()
                    print(f"  mag {n_m}")

            skipped = 0
            if comp_path.is_file():
                for r in _iter(comp_path):
                    cid = r.get("id") or r.get("compensation_id")
                    mid = r.get("magistrate_id")
                    if not cid or not mid:
                        continue
                    if mid not in mag_ids:
                        skipped += 1
                        continue
                    cur.execute(
                        """
                        INSERT INTO magistrate_compensation (
                          id, magistrate_id, court_id, reference_year, reference_month,
                          reference_period, base_subsidy, personal_advantages,
                          eventual_advantages, indemnities, retroactive_payments,
                          other_components, gross_total, discounts, net_total,
                          source_id, dataset_id, position
                        ) VALUES (
                          %(id)s, %(magistrate_id)s, %(court_id)s, %(reference_year)s,
                          %(reference_month)s, %(reference_period)s, %(base_subsidy)s,
                          %(personal_advantages)s, %(eventual_advantages)s, %(indemnities)s,
                          %(retroactive_payments)s, %(other_components)s, %(gross_total)s,
                          %(discounts)s, %(net_total)s, %(source_id)s, %(dataset_id)s,
                          %(position)s
                        )
                        ON CONFLICT (id) DO UPDATE SET
                          gross_total = EXCLUDED.gross_total,
                          net_total = EXCLUDED.net_total,
                          updated_at = NOW()
                        """,
                        {
                            "id": cid,
                            "magistrate_id": mid,
                            "court_id": r.get("court_id") or "unknown",
                            "reference_year": r.get("reference_year"),
                            "reference_month": r.get("reference_month"),
                            "reference_period": r.get("reference_period"),
                            "base_subsidy": r.get("base_subsidy"),
                            "personal_advantages": r.get("personal_advantages"),
                            "eventual_advantages": r.get("eventual_advantages"),
                            "indemnities": r.get("indemnities"),
                            "retroactive_payments": r.get("retroactive_payments"),
                            "other_components": r.get("other_components"),
                            "gross_total": r.get("gross_total"),
                            "discounts": r.get("discounts"),
                            "net_total": r.get("net_total"),
                            "source_id": r.get("source_id") or "cnj_magistrate_compensation",
                            "dataset_id": r.get("dataset_id"),
                            "position": r.get("position"),
                        },
                    )
                    n_c += 1
                    if n_c % 1000 == 0:
                        conn.commit()
                        print(f"  comp {n_c}")
        conn.commit()
    print(f"OK magistrates={n_m} compensations={n_c} skipped_orphan={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
