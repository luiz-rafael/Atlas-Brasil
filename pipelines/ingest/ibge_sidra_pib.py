#!/usr/bin/env python3
"""
Ingest IBGE SIDRA — PIB a preços correntes (tabela 5938, variável 37).

Níveis:
  n3 = Unidade da Federação (série completa p/all)
  n6 = Município (ano a ano — p/all estoura limite da API)

Unidade oficial: Mil Reais (preços correntes — nominal).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, http_get, utc_now, write_json  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

TABELA = "5938"
VAR = "37"


def fetch_sidra(nivel: str, periodo: str) -> list:
    url = (
        f"https://apisidra.ibge.gov.br/values/t/{TABELA}/"
        f"n{nivel}/all/v/{VAR}/p/{periodo}?formato=json"
    )
    print(f"  SIDRA n{nivel} p={periodo} …", flush=True)
    r = http_get(url, timeout=600.0)
    r.raise_for_status()
    return r.json()


def years_from_uf(rows: list) -> list[int]:
    ys: set[int] = set()
    for row in rows[1:]:
        a = str(row.get("D3C") or "")[:4]
        if a.isdigit():
            ys.add(int(a))
    return sorted(ys)


def main() -> int:
    run = start_run("ibge", "ibge.sidra_pib_5938")
    out = bronze_dir("ibge")

    uf_rows = fetch_sidra("3", "all")
    write_json(out / "sidra_5938_pib_uf.json", uf_rows)

    years = years_from_uf(uf_rows)
    if not years:
        # fallback série moderna PIB mun
        years = list(range(2002, 2024))

    mun_all: list[dict] = []
    header: dict | None = None
    fails = 0
    for y in years:
        try:
            chunk = fetch_sidra("6", str(y))
        except Exception as e:
            print(f"  fail mun {y}: {e}", file=sys.stderr)
            fails += 1
            continue
        if not chunk:
            continue
        if header is None:
            header = chunk[0]
            mun_all.append(header)
        mun_all.extend(chunk[1:])

    write_json(out / "sidra_5938_pib_mun.json", mun_all)

    meta = {
        "em": utc_now(),
        "tabela": TABELA,
        "variavel": VAR,
        "variavel_nome": "Produto Interno Bruto a preços correntes",
        "unidade": "Mil Reais",
        "uf_linhas": len(uf_rows),
        "mun_linhas": len(mun_all),
        "anos_mun": years,
        "falhas_ano": fails,
        "url_doc": "https://sidra.ibge.gov.br/tabela/5938",
        "ingestion_run_id": run["ingestion_run_id"],
        "nota": (
            "Valores nominais (preços correntes). "
            "Municípios baixados ano a ano (API rejeita p/all em n6)."
        ),
    }
    write_json(out / "sidra_5938_meta.json", meta)
    ok = len(uf_rows) > 1 and len(mun_all) > 1
    mark_ingested(
        "ibge",
        run_id=run["ingestion_run_id"],
        counts={
            "pib_uf": max(0, len(uf_rows) - 1),
            "pib_mun": max(0, len(mun_all) - 1),
            "anos": len(years),
        },
        ok=ok,
    )
    print(f"OK SIDRA PIB: uf={len(uf_rows)} mun={len(mun_all)} anos={len(years)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
