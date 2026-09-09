#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

import psycopg
from app import serving_contas as sc

conn = psycopg.connect("postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil")
cur = conn.cursor()
print("fro", cur.execute("SELECT COUNT(*) FROM fiscal_result_observation") or cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM serving_load_runs WHERE status=%s", ("OK",))
print("runs_ok", cur.fetchone()[0])
r = sc.resumo(2024)
assert r.get("resultado_fiscal"), "resultado fiscal 2024 ausente"
assert r.get("renuncia_fiscal"), "renuncia 2024 ausente"
assert r.get("quanto_entrou"), "receita 2024 ausente"
print("resumo_ok")
for name, fn in [
    ("receitas", lambda: sc.list_receitas(year=2024, limit=2)),
    ("despesas", lambda: sc.list_despesas(year=2024, limit=2)),
    ("resultado", lambda: sc.list_resultado_fiscal(year=2024, limit=2)),
    ("divida", lambda: sc.list_divida(year=2024, limit=2)),
    ("renuncias", lambda: sc.list_renuncias(year=2024, limit=2)),
]:
    d = fn()
    print(name, d.get("total"))
try:
    import urllib.request

    with urllib.request.urlopen("http://127.0.0.1:8000/v1/contas/resumo?year=2024", timeout=15) as resp:
        body = resp.read()
        print("HTTP", resp.status, body[:180])
except Exception as e:
    print("HTTP_SKIP", type(e).__name__, e)
print("DEMO_DONE")
