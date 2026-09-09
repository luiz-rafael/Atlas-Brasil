#!/usr/bin/env python3
"""
Silver campanhas TSE — despesas contratadas de candidatos → fornecedores.

Estratégia:
  - Processa CSVs despesas_contratadas_candidatos_*.csv
  - Mantém cargos federais (Deputado Federal / Senador) por padrão
  - Guarda NM_CANDIDATO + UF para ER no gold (SQ da gold costuma ser de outra eleição)

Saída: data/lake/silver/campanhas/
"""

from __future__ import annotations

import csv
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, write_json, write_jsonl  # noqa: E402

CARGOS_OK = {
    "DEPUTADO FEDERAL",
    "SENADOR",
    "1º SUPLENTE",
    "2º SUPLENTE",
    "1o SUPLENTE",
    "2o SUPLENTE",
}


def only_digits(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def money(s: str | None) -> float:
    if s is None or s == "":
        return 0.0
    t = str(s).strip()
    if "," in t and t.rfind(",") > t.rfind("."):
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def norm_name(s: str | None) -> str:
    s = (s or "").upper()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def latest_csv_dir() -> Path | None:
    base = LAKE / "bronze" / "tse_prestacao"
    if not base.exists():
        return None
    # prioriza pastas com csv_candidatos por mtime
    cands = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        c = d / "csv_candidatos"
        if c.is_dir() and any(c.glob("despesas_contratadas_candidatos*.csv")):
            cands.append(c)
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def cargo_ok(cargo: str) -> bool:
    c = norm_name(cargo)
    if not c:
        return False
    if os.getenv("CAMPANHA_TODOS_CARGOS", "0") == "1":
        return True
    return any(x in c for x in ("DEPUTADO FEDERAL", "SENADOR"))


def main() -> int:
    csv_dir = latest_csv_dir()
    if not csv_dir:
        print("sem csv_candidatos — rode tse_prestacao.py", file=sys.stderr)
        return 1

    files = sorted(csv_dir.glob("despesas_contratadas_candidatos*.csv"))
    # se SP ainda não foi extraído, avisa
    if not any("sp.csv" in p.name.lower() for p in files):
        print(
            "aviso: SP ausente — rode tse_prestacao com TSE_PRESTACAO_MAX_CSV_MB>=200",
            file=sys.stderr,
        )

    by_sq: dict[str, dict] = {}
    n_rows = 0
    n_kept = 0
    for fp in files:
        print(f"lendo {fp.name} …", flush=True)
        with fp.open("r", encoding="latin-1", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                n_rows += 1
                cargo = (row.get("DS_CARGO") or "").strip()
                if not cargo_ok(cargo):
                    continue
                sq = only_digits(row.get("SQ_CANDIDATO"))
                if not sq:
                    continue
                n_kept += 1
                cnpj = only_digits(row.get("NR_CPF_CNPJ_FORNECEDOR"))
                nome_f = (
                    row.get("NM_FORNECEDOR_RFB") or row.get("NM_FORNECEDOR") or ""
                ).strip()
                valor = money(row.get("VR_DESPESA_CONTRATADA"))
                ano = only_digits(row.get("ANO_ELEICAO") or row.get("AA_ELEICAO") or "")[:4]
                uf = (row.get("SG_UF") or "").strip().upper()[:2]
                nome_c = (row.get("NM_CANDIDATO") or "").strip()
                slot = by_sq.setdefault(
                    sq,
                    {
                        "sq_candidato": sq,
                        "person_id": f"p_tse_{sq}",
                        "nome": nome_c,
                        "nome_norm": norm_name(nome_c),
                        "ano": int(ano) if ano.isdigit() else None,
                        "uf": uf or None,
                        "cargo": cargo or None,
                        "total_despesas": 0.0,
                        "qtd_despesas": 0,
                        "por_forn": {},
                    },
                )
                if nome_c and not slot.get("nome"):
                    slot["nome"] = nome_c
                    slot["nome_norm"] = norm_name(nome_c)
                if not slot.get("ano") and ano.isdigit():
                    slot["ano"] = int(ano)
                slot["total_despesas"] += valor
                slot["qtd_despesas"] += 1
                if len(cnpj) >= 11 or nome_f:
                    key = cnpj if len(cnpj) >= 11 else f"nome:{nome_f.upper()}"
                    forn = slot["por_forn"].setdefault(
                        key,
                        {
                            "cnpj": cnpj if len(cnpj) in (11, 14) else None,
                            "nome": nome_f or None,
                            "valor": 0.0,
                            "qtd": 0,
                        },
                    )
                    if nome_f and not forn.get("nome"):
                        forn["nome"] = nome_f
                    forn["valor"] += valor
                    forn["qtd"] += 1

    limit_sq = int(os.getenv("CAMPANHA_SQ_LIMIT", "0") or "0")
    items = list(by_sq.values())
    if limit_sq > 0:
        items = sorted(items, key=lambda x: -x["total_despesas"])[:limit_sq]

    resumo_rows = []
    despesas_rows = []
    for it in items:
        top = sorted(it["por_forn"].values(), key=lambda x: -x["valor"])[:15]
        for f in top:
            f["valor"] = round(f["valor"], 2)
        resumo = {
            "person_id": it["person_id"],
            "sq_candidato": it["sq_candidato"],
            "nome": it.get("nome"),
            "nome_norm": it.get("nome_norm"),
            "ano": it.get("ano"),
            "uf": it.get("uf"),
            "cargo": it.get("cargo"),
            "total_despesas": round(it["total_despesas"], 2),
            "qtd_despesas": it["qtd_despesas"],
            "fornecedores": top,
            "fonte": "tse_prestacao",
            "fonte_url": "https://dadosabertos.tse.jus.br/",
        }
        resumo_rows.append(resumo)
        for f in top:
            despesas_rows.append(
                {
                    "person_id": it["person_id"],
                    "sq_candidato": it["sq_candidato"],
                    "nome": it.get("nome"),
                    "ano": it.get("ano"),
                    "cnpj": f.get("cnpj"),
                    "nome_fornecedor": f.get("nome"),
                    "valor": f.get("valor"),
                    "qtd": f.get("qtd"),
                    "fonte": "tse_prestacao",
                }
            )

    out = LAKE / "silver" / "campanhas"
    out.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    write_jsonl(out / f"resumo_{stamp}.jsonl", resumo_rows)
    write_jsonl(out / "resumo_latest.jsonl", resumo_rows)
    write_jsonl(out / f"despesas_fornecedor_{stamp}.jsonl", despesas_rows)
    write_jsonl(out / "despesas_fornecedor_latest.jsonl", despesas_rows)
    write_json(
        out / "meta.json",
        {
            "csv_dir": str(csv_dir),
            "arquivos": [p.name for p in files],
            "linhas_lidas": n_rows,
            "linhas_kept": n_kept,
            "candidatos": len(resumo_rows),
        },
    )
    print(
        f"OK silver campanhas: candidatos={len(resumo_rows)} "
        f"rows_kept={n_kept}/{n_rows}"
    )
    return 0 if resumo_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
