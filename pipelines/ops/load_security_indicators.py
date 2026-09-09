#!/usr/bin/env python3
"""Upsert indicadores de segurança (SIM/CVLI) no Postgres — foco UF para o Atlas mapa."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE  # noqa: E402

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
)

SEC_IDS = {
    "ind_homicidios",
    "ind_homicidios_per_100k",
    "ind_mortes_causas_externas",
    "ind_cvli_per_100k",
}

STATE_ONLY = os.getenv("ATLAS_SEC_STATE_ONLY", "1") in ("1", "true", "yes")


def main() -> int:
    import psycopg

    sil = LAKE / "silver" / "indicadores"
    ind_path = sil / "indicators_latest.json"
    if not ind_path.exists():
        # fallback stamped
        cands = sorted(sil.glob("indicators_*.json"), reverse=True)
        ind_path = cands[0] if cands else ind_path
    obs_path = sil / "observations_latest.jsonl"
    if not ind_path.exists() or not obs_path.exists():
        print("silver indicadores ausente", file=sys.stderr)
        return 1

    indicators = json.loads(ind_path.read_text(encoding="utf-8"))
    sec_defs = [i for i in indicators if i.get("indicator_id") in SEC_IDS]
    if not sec_defs:
        # try stamped indicators file
        for p in sorted(sil.glob("indicators_*.json"), reverse=True):
            indicators = json.loads(p.read_text(encoding="utf-8"))
            sec_defs = [i for i in indicators if i.get("indicator_id") in SEC_IDS]
            if sec_defs:
                break
    print(f"defs={len(sec_defs)} scanning {obs_path} ...", flush=True)

    rows: list[tuple] = []
    seen: set[str] = set()
    with obs_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            o = json.loads(line)
            iid = o.get("indicator_id")
            if iid not in SEC_IDS:
                continue
            tid = o.get("territory_id") or ""
            if STATE_ONLY and not tid.startswith("uf_"):
                continue
            oid = o.get("observation_id")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            try:
                year = int(o["reference_year"])
                value = float(o["value"])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append(
                (
                    oid,
                    iid,
                    tid,
                    year,
                    value,
                    o.get("unit"),
                    o.get("source_id"),
                    o.get("geographic_level")
                    or ("STATE" if tid.startswith("uf_") else "MUNICIPALITY"),
                )
            )

    print(f"rows={len(rows)} loading postgres...", flush=True)
    conn = psycopg.connect(DSN)
    with conn:
        with conn.cursor() as cur:
            for i in sec_defs:
                cur.execute(
                    """
                    INSERT INTO indicators (
                      indicator_id, name, display_name, description, category,
                      unit, source_id, dataset_id, minimum_geographic_level,
                      methodology_url, notes
                    ) VALUES (
                      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT (indicator_id) DO UPDATE SET
                      display_name = EXCLUDED.display_name,
                      description = EXCLUDED.description,
                      category = EXCLUDED.category,
                      unit = EXCLUDED.unit,
                      notes = EXCLUDED.notes
                    """,
                    (
                        i.get("indicator_id"),
                        i.get("name"),
                        i.get("display_name"),
                        i.get("description"),
                        i.get("category"),
                        i.get("unit"),
                        i.get("source_id"),
                        i.get("dataset_id"),
                        i.get("minimum_geographic_level"),
                        i.get("methodology_url"),
                        i.get("notes"),
                    ),
                )

            # replace security observations (state) to avoid stale dupes
            cur.execute(
                "DELETE FROM observations WHERE indicator_id = ANY(%s)",
                (list(SEC_IDS),),
            )

            from io import StringIO

            buf = StringIO()
            for r in rows:
                parts = []
                for v in r:
                    if v is None:
                        parts.append("\\N")
                    else:
                        s = (
                            str(v)
                            .replace("\\", "\\\\")
                            .replace("\t", " ")
                            .replace("\n", " ")
                            .replace("\r", " ")
                        )
                        parts.append(s)
                buf.write("\t".join(parts) + "\n")
            buf.seek(0)
            with cur.copy(
                """
                COPY observations (
                  observation_id, indicator_id, territory_id, reference_year,
                  value, unit, source_id, geographic_level
                ) FROM STDIN
                """
            ) as copy:
                copy.write(buf.read())

            cur.execute(
                """
                SELECT indicator_id, COUNT(*)
                FROM observations
                WHERE indicator_id = ANY(%s)
                GROUP BY 1 ORDER BY 1
                """,
                (list(SEC_IDS),),
            )
            print("loaded", cur.fetchall(), flush=True)
    conn.close()
    print("OK load_security_indicators", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
