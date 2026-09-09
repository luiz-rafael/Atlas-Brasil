#!/usr/bin/env python3
"""Carrega mandates + administrations a partir do silver governadores.

Uso:
  python -u pipelines/ops/load_administrations.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from app.serving_administrations import (  # noqa: E402
    administration_from_mandate,
    clear_admin_cache,
    load_mandatos_silver,
    mandate_from_silver,
)

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
)


def main() -> int:
    import psycopg

    rows = load_mandatos_silver()
    if not rows:
        print("FAIL: silver mandatos vazio")
        return 1

    mandatos = [mandate_from_silver(r) for r in rows]
    admins = [administration_from_mandate(m) for m in mandatos]
    # dedupe admins
    adm_map = {a["administration_id"]: a for a in admins}

    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            for m in mandatos:
                cur.execute(
                    """
                    INSERT INTO mandates (
                      mandate_id, person_id, person_stub, person_name, office,
                      territory_id, state_code, start_date, end_date,
                      election_year, party_at_start, source, source_url, evidence_degree
                    ) VALUES (
                      %(mandate_id)s, %(person_id)s, %(person_stub)s, %(person_name)s, %(office)s,
                      %(territory_id)s, %(state_code)s, %(start_date)s, %(end_date)s,
                      %(election_year)s, %(party_at_start)s, %(source)s, %(source_url)s, %(evidence_degree)s
                    )
                    ON CONFLICT (mandate_id) DO UPDATE SET
                      person_id = EXCLUDED.person_id,
                      person_name = EXCLUDED.person_name,
                      start_date = EXCLUDED.start_date,
                      end_date = EXCLUDED.end_date,
                      party_at_start = EXCLUDED.party_at_start,
                      updated_at = NOW()
                    """,
                    m,
                )
            for a in adm_map.values():
                cur.execute(
                    """
                    INSERT INTO administrations (
                      administration_id, territory_id, state_code, administration_type,
                      executive_person_id, executive_person_name, start_date, end_date,
                      party_at_start, mandate_id, election_year, source, source_url
                    ) VALUES (
                      %(administration_id)s, %(territory_id)s, %(state_code)s, %(administration_type)s,
                      %(executive_person_id)s, %(executive_person_name)s, %(start_date)s, %(end_date)s,
                      %(party_at_start)s, %(mandate_id)s, %(election_year)s, %(source)s, %(source_url)s
                    )
                    ON CONFLICT (administration_id) DO UPDATE SET
                      executive_person_id = EXCLUDED.executive_person_id,
                      executive_person_name = EXCLUDED.executive_person_name,
                      start_date = EXCLUDED.start_date,
                      end_date = EXCLUDED.end_date,
                      updated_at = NOW()
                    """,
                    a,
                )
        conn.commit()

    clear_admin_cache()
    print(f"OK mandates={len(mandatos)} administrations={len(adm_map)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
