#!/usr/bin/env python3
"""Smoke Fase C: PG counts + endpoints serving (HTTP opcional)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "api"))

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
)
API = os.getenv("ATLAS_API_URL", "http://localhost:8000").rstrip("/")


def main() -> int:
    import psycopg

    out: dict = {"ok": False, "dsn": DSN.split("@")[-1]}
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            for table in (
                "territories",
                "indicators",
                "observations",
                "documentos",
                "gold_indicadores_uf_latest",
            ):
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                out[table] = cur.fetchone()[0]

    ok_pg = (
        out.get("territories", 0) > 0
        and out.get("indicators", 0) > 0
        and out.get("observations", 0) > 0
    )

    http: dict = {}
    try:
        import httpx

        with httpx.Client(timeout=30.0) as client:
            for path in (
                "/v1/indicadores/meta",
                "/v1/indicadores/years?indicator_id=ind_pop_estimada",
                "/v1/indicadores/choropleth?year=2024&indicator_id=ind_pop_estimada",
                "/v1/fontes",
            ):
                r = client.get(f"{API}{path}")
                http[path] = {"status": r.status_code, "ok": r.status_code == 200}
                if path.endswith("/meta") and r.status_code == 200:
                    http["meta_body"] = r.json()
                if "choropleth" in path and r.status_code == 200:
                    vals = (r.json() or {}).get("values") or {}
                    http["choropleth_n"] = len(vals)
    except Exception as e:
        http["error"] = str(e)

    out["http"] = http
    out["ok"] = ok_pg and (
        not http
        or http.get("error")
        or all(
            v.get("ok")
            for k, v in http.items()
            if isinstance(v, dict) and "status" in v
        )
        or True  # PG ok basta se API off
    )
    # critério mínimo: PG populado
    out["ok"] = ok_pg
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok_pg else 1


if __name__ == "__main__":
    raise SystemExit(main())
