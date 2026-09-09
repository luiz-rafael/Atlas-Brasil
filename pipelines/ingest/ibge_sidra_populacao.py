#!/usr/bin/env python3
"""
Ingest IBGE SIDRA — população residente estimada (tabela 6579, v=9324).

- n3 UF: série completa p/all
- n6 município: ano a ano (p/all estoura; alguns anos sem estimativa, ex. censitários)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, http_get, utc_now, write_json  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

TABELA = "6579"
VAR = "9324"


def fetch(nivel: str, periodo: str) -> list:
    url = (
        f"https://apisidra.ibge.gov.br/values/t/{TABELA}/"
        f"n{nivel}/all/v/{VAR}/p/{periodo}?formato=json"
    )
    print(f"  SIDRA pop n{nivel} p={periodo} …", flush=True)
    r = http_get(url, timeout=600.0)
    r.raise_for_status()
    return r.json()


def years_from(rows: list) -> list[int]:
    ys: set[int] = set()
    for row in rows[1:]:
        a = str(row.get("D3C") or "")[:4]
        if a.isdigit():
            ys.add(int(a))
    return sorted(ys)


def main() -> int:
    run = start_run("ibge", "ibge.sidra_populacao")
    out = bronze_dir("ibge")

    uf_rows = fetch("3", "all")
    write_json(out / "sidra_6579_populacao_uf.json", uf_rows)

    years = years_from(uf_rows) or list(range(2001, 2027))
    mun_all: list[dict] = []
    header: dict | None = None
    ok_anos: list[int] = []
    skip_anos: list[int] = []

    for y in years:
        try:
            chunk = fetch("6", str(y))
        except Exception as e:
            print(f"  fail mun {y}: {e}", file=sys.stderr)
            skip_anos.append(y)
            continue
        if len(chunk) <= 1:
            skip_anos.append(y)
            print(f"  skip mun {y}: sem dados", flush=True)
            continue
        if header is None:
            header = chunk[0]
            mun_all.append(header)
        mun_all.extend(chunk[1:])
        ok_anos.append(y)

    write_json(out / "sidra_6579_populacao_mun.json", mun_all)
    write_json(
        out / "sidra_6579_meta.json",
        {
            "em": utc_now(),
            "tabela": TABELA,
            "variavel": VAR,
            "uf_linhas": len(uf_rows),
            "mun_linhas": len(mun_all),
            "anos_mun_ok": ok_anos,
            "anos_mun_skip": skip_anos,
            "url_doc": "https://sidra.ibge.gov.br/tabela/6579",
            "ingestion_run_id": run["ingestion_run_id"],
        },
    )
    mark_ingested(
        "ibge",
        run_id=run["ingestion_run_id"],
        counts={
            "pop_uf": max(0, len(uf_rows) - 1),
            "pop_mun": max(0, len(mun_all) - 1),
            "anos_mun": len(ok_anos),
        },
        ok=len(uf_rows) > 1,
    )
    print(
        f"OK SIDRA população: uf={len(uf_rows)} mun={len(mun_all)} "
        f"anos_mun={len(ok_anos)} skip={skip_anos}"
    )
    return 0 if len(uf_rows) > 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
