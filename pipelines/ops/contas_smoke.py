#!/usr/bin/env python3
"""Smoke Contas: dual env + API resumo 2024 (host localhost:8001)."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    env_path = ROOT / ".env"
    env_txt = env_path.read_text(encoding="utf-8", errors="replace") if env_path.exists() else ""
    dual_ok = "ATLAS_STORAGE_BACKEND=dual" in env_txt and "ATLAS_MINIO_ENABLED=1" in env_txt

    api = os.getenv("ATLAS_API_URL", "http://localhost:8001").rstrip("/")
    url = f"{api}/v1/contas/resumo?year=2024"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode())
        api_ok = True
        err = None
    except Exception as e:
        data = {}
        api_ok = False
        err = str(e)

    entrou = (data.get("quanto_entrou") or {}).get("value")
    out = {
        "ok": dual_ok and api_ok and entrou is not None,
        "env_dual": dual_ok,
        "api_url": url,
        "api_ok": api_ok,
        "api_error": err,
        "year": data.get("year"),
        "quanto_entrou": entrou,
        "quanto_saiu": (data.get("quanto_saiu") or {}).get("value"),
        "resultado_primario": (
            (data.get("resultado_fiscal") or {}).get("primary_result") or {}
        ).get("value"),
        "renuncia": (data.get("renuncia_fiscal") or {}).get("value"),
        "hint": "Use localhost (nao 127.0.0.1) se houver uvicorn fantasma no Windows",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
