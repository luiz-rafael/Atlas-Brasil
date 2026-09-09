#!/usr/bin/env python3
"""
Silver FASE 7 — candidaturas / mandatos de Governador (TSE consulta_cand).

Lê bronze tse_ckan/**/consulta_cand_*.csv
Mantém GOVERNADOR (e VICE se GOV_INCLUIR_VICE=1).
ELEITO → mandato (office_tenure) com UF.
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

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402


def norm_name(s: str | None) -> str:
    s = (s or "").upper()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def only_digits(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def is_eleito(sit: str) -> bool:
    s = (sit or "").upper()
    if "NÃO" in s or "NAO" in s:
        return False
    return "ELEITO" in s


def find_cand_csvs() -> list[Path]:
    """Só consulta_cand_{ano}_BRASIL.csv (evita complementar/UF sem situação final)."""
    base = LAKE / "bronze" / "tse_ckan"
    if not base.exists():
        return []
    out: list[Path] = []
    for p in base.rglob("consulta_cand_*.csv"):
        name = p.name.lower()
        if "complementar" in name:
            continue
        if "brasil" not in name:
            continue
        out.append(p)
    out.sort(key=lambda p: -p.stat().st_mtime)
    return out


def tenure_dates(ano_eleicao: int | None) -> tuple[str, str]:
    """Mandato estadual típico: 1º jan ano+1 → 1º jan ano+5."""
    if not ano_eleicao:
        return "", ""
    ini = f"{ano_eleicao + 1}-01-01"
    fim = f"{ano_eleicao + 5}-01-01"
    return ini, fim


def main() -> int:
    csvs = find_cand_csvs()
    if not csvs:
        print("sem consulta_cand no bronze tse_ckan", file=sys.stderr)
        return 1

    include_vice = os.getenv("GOV_INCLUIR_VICE", "1") == "1"
    cargos_ok = {"GOVERNADOR"}
    if include_vice:
        cargos_ok.add("VICE-GOVERNADOR")

    by_sq: dict[str, dict] = {}
    seen_files: set[str] = set()

    for fp in csvs:
        # um BRASIL por ano basta
        key = fp.name.lower()
        if key in seen_files:
            continue
        if "brasil" in key:
            seen_files.add(key)
        print(f"lendo {fp.relative_to(LAKE)} …", flush=True)
        with fp.open("r", encoding="latin-1", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                cargo = (
                    row.get("DS_CARGO") or row.get("DESCRICAO_CARGO") or ""
                ).upper().strip()
                if cargo not in cargos_ok:
                    continue
                sq = only_digits(row.get("SQ_CANDIDATO") or row.get("SEQUENCIAL_CANDIDATO"))
                if not sq:
                    continue
                ano = only_digits(row.get("ANO_ELEICAO") or "")[:4]
                ano_i = int(ano) if ano.isdigit() else None
                sit = (
                    row.get("DS_SIT_TOT_TURNO") or row.get("DESC_SIT_TOT_TURNO") or ""
                ).strip()
                eleito = is_eleito(sit)
                nome = (row.get("NM_CANDIDATO") or row.get("NOME_CANDIDATO") or "").strip()
                urna = (
                    row.get("NM_URNA_CANDIDATO") or row.get("NOME_URNA_CANDIDATO") or ""
                ).strip()
                uf = (row.get("SG_UF") or row.get("SIGLA_UF") or "").strip().upper()[:2]
                partido = (
                    row.get("SG_PARTIDO") or row.get("SIGLA_PARTIDO") or ""
                ).strip().upper()
                cpf = only_digits(row.get("NR_CPF_CANDIDATO") or row.get("CPF_CANDIDATO"))
                rec = {
                    "sq_candidato": sq,
                    "person_id": f"p_tse_{sq}",
                    "nome": nome,
                    "nome_urna": urna or None,
                    "nome_norm": norm_name(urna or nome),
                    "cargo": cargo.title().replace("Vice-Governador", "Vice-governador"),
                    "uf": uf or None,
                    "partido": partido or None,
                    "ano_eleicao": ano_i,
                    "situacao": sit,
                    "eleito": eleito,
                    "cpf": cpf if len(cpf) == 11 else None,
                    "fonte": "tse_ckan",
                    "fonte_url": "https://dadosabertos.tse.jus.br/",
                }
                # Chave ano+SQ (SQ pode repetir entre eleições em layouts antigos)
                key_sq = f"{ano_i or 'x'}:{sq}"
                # Preferir ELEITO sobre 2º TURNO (mesmo SQ aparece duas vezes no CSV)
                prev = by_sq.get(key_sq)
                if prev is None or (eleito and not prev.get("eleito")):
                    by_sq[key_sq] = rec

    candidaturas = list(by_sq.values())
    mandatos: list[dict] = []
    for rec in candidaturas:
        cargo_u = (rec.get("cargo") or "").upper().replace("VICE-GOVERNADOR", "VICE")
        if not (rec.get("eleito") and cargo_u == "GOVERNADOR" and rec.get("uf")):
            continue
        uf = str(rec["uf"])
        ano_i = rec.get("ano_eleicao")
        ini, fim = tenure_dates(ano_i if isinstance(ano_i, int) else None)
        mandatos.append(
            {
                "id": f"tenure_gov_{uf}_{ano_i or 'x'}_{rec['sq_candidato']}",
                "person_id": rec["person_id"],
                "sq_candidato": rec["sq_candidato"],
                "cargo": "Governador",
                "uf": uf,
                "partido": rec.get("partido"),
                "ano_eleicao": ano_i,
                "inicio": ini,
                "fim": fim,
                "nome": rec.get("nome"),
                "nome_urna": rec.get("nome_urna"),
                "nome_norm": rec.get("nome_norm"),
                "cpf": rec.get("cpf"),
                "fonte": "tse_ckan",
                "fonte_url": rec.get("fonte_url"),
                "grau_confirmacao": "fato_documentado",
            }
        )

    out = LAKE / "silver" / "governadores"
    out.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    write_jsonl(out / f"candidaturas_{stamp}.jsonl", candidaturas)
    write_jsonl(out / "candidaturas_latest.jsonl", candidaturas)
    write_jsonl(out / f"mandatos_{stamp}.jsonl", mandatos)
    write_jsonl(out / "mandatos_latest.jsonl", mandatos)
    write_json(
        out / "meta.json",
        {
            "em": utc_now(),
            "candidaturas": len(candidaturas),
            "mandatos": len(mandatos),
            "arquivos": [str(p) for p in csvs[:20]],
        },
    )
    print(
        f"OK silver governadores: candidaturas={len(candidaturas)} "
        f"mandatos_eleitos={len(mandatos)}"
    )
    return 0 if mandatos or candidaturas else 1


if __name__ == "__main__":
    raise SystemExit(main())
