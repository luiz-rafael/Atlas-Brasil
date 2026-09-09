#!/usr/bin/env python3
"""
Ingest IBGE SIDRA — Valor Adicionado setorial (tabela 5938).

Variáveis (preços correntes, Mil Reais):
  513  VA agropecuária
  517  VA indústria
  6575 VA serviços (exclusive admin/defesa/educação/saúde públicas)

Também participaçoes no VA total (opcional, para shares):
  516, 520, 6574

Níveis: n3=UF (série completa), n6=município (ano a ano).
Nota: edições recentes do PIB Municipais podem omitir abertura setorial —
falhas por ano são registradas sem inventar valores.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, http_get, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

TABELA = "5938"
# valores absolutos (Mil Reais)
VARS_ABS = {
    "513": "va_agro",
    "517": "va_industria",
    "6575": "va_servicos",
}
# shares % no VA total
VARS_SHARE = {
    "516": "va_agro_share",
    "520": "va_industria_share",
    "6574": "va_servicos_share",
}
ALL_VARS = ",".join(list(VARS_ABS) + list(VARS_SHARE))

UF_CODE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


def fetch_sidra(nivel: str, periodo: str) -> list:
    url = (
        f"https://apisidra.ibge.gov.br/values/t/{TABELA}/"
        f"n{nivel}/all/v/{ALL_VARS}/p/{periodo}?formato=json"
    )
    print(f"  SIDRA VA n{nivel} p={periodo} …", flush=True)
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


def sidra_to_extract(rows: list, nivel: str) -> list[dict]:
    """Agrupa linhas SIDRA por território+ano com campos VA."""
    if not rows or len(rows) < 2:
        return []
    # D1 = território, D2 = variável, D3 = ano
    bucket: dict[tuple, dict] = {}
    now = utc_now()
    for row in rows[1:]:
        ter = str(row.get("D1C") or "").strip()
        var = str(row.get("D2C") or "").strip()
        year_s = str(row.get("D3C") or "")[:4]
        val_s = str(row.get("V") or "").strip()
        if not ter or not year_s.isdigit() or not val_s or val_s in ("-", "...", "X"):
            continue
        try:
            val = float(val_s.replace(",", "."))
        except ValueError:
            continue
        field = VARS_ABS.get(var) or VARS_SHARE.get(var)
        if not field:
            continue
        if nivel == "3":
            uf = UF_CODE.get(ter.zfill(2), "")
            if not uf:
                continue
            nivel_geo = "STATE"
            cod = uf
            tid = f"uf_{uf}"
        else:
            cod = ter[:7] if len(ter) >= 7 else ter
            tid = f"mun_{cod}"
            nivel_geo = "MUNICIPALITY"
        key = (nivel_geo, tid, int(year_s))
        rec = bucket.setdefault(
            key,
            {
                "nivel": nivel_geo,
                "territory_id": tid,
                "cod_ibge": cod,
                "ano": int(year_s),
                "retrieved_at": now,
                "fonte": "sidra_5938_va",
            },
        )
        rec[field] = val
    return list(bucket.values())


def main() -> int:
    run = start_run("ibge", "ibge.sidra_va_5938")
    out = bronze_dir("ibge_va")

    uf_rows = fetch_sidra("3", "all")
    write_json(out / "sidra_5938_va_uf.json", uf_rows)
    uf_extract = sidra_to_extract(uf_rows, "3")

    years = years_from_uf(uf_rows) or list(range(2002, 2022))
    mun_all: list[dict] = []
    header: dict | None = None
    fails = 0
    skip_mun = os.getenv("ATLAS_VA_UF_ONLY", "").strip().lower() in ("1", "true", "yes")
    if skip_mun:
        print("  ATLAS_VA_UF_ONLY=1 — pulando municípios", flush=True)
    else:
        for y in years:
            try:
                chunk = fetch_sidra("6", str(y))
            except Exception as e:
                print(f"  fail mun {y}: {e}", file=sys.stderr)
                fails += 1
                continue
            if not chunk:
                continue
            # se só header / sem valores setoriais
            if len(chunk) <= 1:
                fails += 1
                continue
            if header is None:
                header = chunk[0]
                mun_all.append(header)
            mun_all.extend(chunk[1:])

    write_json(out / "sidra_5938_va_mun.json", mun_all)
    mun_extract = sidra_to_extract(mun_all, "6")
    extract = uf_extract + mun_extract
    write_jsonl(out / "ibge_va_extract.jsonl", extract)

    meta = {
        "em": utc_now(),
        "tabela": TABELA,
        "variaveis_abs": VARS_ABS,
        "variaveis_share": VARS_SHARE,
        "unidade": "Mil Reais (abs) / percent (share)",
        "uf_linhas_raw": len(uf_rows),
        "mun_linhas_raw": len(mun_all),
        "extract_rows": len(extract),
        "anos_mun": years,
        "falhas_ano": fails,
        "url_doc": "https://sidra.ibge.gov.br/tabela/5938",
        "ingestion_run_id": run["ingestion_run_id"],
        "nota": (
            "VA setorial a preços correntes. Municípios ano a ano. "
            "Anos recentes podem não ter abertura setorial (API vazia/…)."
        ),
    }
    write_json(out / "sidra_5938_va_meta.json", meta)
    ok = len(extract) > 0
    mark_ingested(
        "ibge",
        run_id=run["ingestion_run_id"],
        counts={"extract": len(extract), "anos": len(years), "falhas_ano": fails},
        ok=ok,
        dataset_id="ibge.sidra_va_5938",
    )
    print(f"OK SIDRA VA: extract={len(extract)} anos={len(years)} falhas={fails}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
