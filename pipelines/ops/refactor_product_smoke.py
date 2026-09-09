#!/usr/bin/env python3
"""Smoke da refatoração produto — Fases A–E (+ empresas).

Uso:
  python -u pipelines/ops/refactor_product_smoke.py
  ATLAS_API_URL=http://localhost:8001 python -u pipelines/ops/refactor_product_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("ATLAS_API_URL", "http://localhost:8001").rstrip("/")


def get(path: str) -> tuple[int, dict | list | None]:
    url = f"{BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=180) as r:
            body = json.loads(r.read().decode("utf-8"))
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        print(f"FAIL {path}: {e}")
        return 0, None


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    code, live = get("/live")
    checks.append(("/live", code == 200, str(live)))

    code, pes = get("/v1/pessoas?escopo=governadores&limit=3")
    ok = code == 200 and isinstance(pes, dict) and (pes.get("total") or 0) > 0
    checks.append(("/v1/pessoas", ok, f"total={pes.get('total') if isinstance(pes, dict) else None}"))

    pid = None
    if isinstance(pes, dict) and pes.get("items"):
        pid = pes["items"][0]["id"]
        code, det = get(f"/v1/pessoas/{pid}")
        ok = code == 200 and isinstance(det, dict) and det.get("pessoa")
        checks.append((f"/v1/pessoas/{{id}}", ok, pid))

    code, adm = get("/v1/administrations?state_code=MG&year=2021")
    ok = code == 200 and isinstance(adm, dict) and (adm.get("total") or 0) >= 1
    checks.append(("/v1/administrations", ok, str((adm or {}).get("total"))))

    code, ctx = get("/v1/territorios/uf_MG/contexto?year=2021&indicators=ind_pop_estimada")
    adm_id = None
    if isinstance(ctx, dict):
        adm_obj = ctx.get("administration") or {}
        if isinstance(adm_obj, dict):
            adm_id = adm_obj.get("administration_id")
    ok = code == 200 and adm_id is not None
    checks.append(("/v1/territorios/.../contexto", ok, str(adm_id)))

    code, emp = get("/v1/empresas?limit=3")
    ok = code == 200 and isinstance(emp, dict)
    checks.append(("/v1/empresas", ok, f"total={emp.get('total') if isinstance(emp, dict) else None}"))

    code, din = get("/v1/dinheiro")
    ok = code == 200 and isinstance(din, dict) and din.get("counts") is not None
    checks.append(("/v1/dinheiro", ok, str((din or {}).get("counts"))))

    code, casos = get("/v1/casos?limit=3")
    ok = code == 200 and isinstance(casos, dict)
    checks.append(("/v1/casos", ok, f"total={casos.get('total') if isinstance(casos, dict) else None}"))

    # PERSON must be postgres after load
    if isinstance(pes, dict):
        checks.append(
            ("pessoas_source_postgres", pes.get("source") == "postgres", str(pes.get("source")))
        )

    failed = 0
    for name, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"{status}  {name}  {detail}")

    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
