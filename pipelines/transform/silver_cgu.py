#!/usr/bin/env python3
"""Silver a partir do bronze CGU (CEIS, CNEP, emendas, contratos)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_jsonl  # noqa: E402


def only_digits(s: str | None) -> str | None:
    if not s:
        return None
    d = re.sub(r"\D", "", str(s))
    return d if len(d) >= 8 else None


def _brl(s) -> float | None:
    if s is None or s == "":
        return None
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except Exception:
        try:
            return float(s)
        except Exception:
            return None


def latest_day(fonte: str) -> Path | None:
    base = LAKE / "bronze" / fonte
    if not base.exists():
        return None
    days = [p for p in base.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == "-"]
    return max(days, key=lambda p: p.name) if days else None


def load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def silver_emendas_from_bronze(day: Path) -> list[dict]:
    # preferir jsonl focado
    jl = day / "emendas_politicos.jsonl"
    rows_raw = []
    if jl.exists():
        for line in jl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows_raw.append(json.loads(line))
    else:
        rows_raw = load_json_list(day / "emendas.json")
    emendas = []
    for row in rows_raw:
        emendas.append(
            {
                "id_externo": f"cgu_emenda:{row.get('codigoEmenda')}",
                "fonte": "cgu_portal",
                "codigo": row.get("codigoEmenda"),
                "ano": row.get("ano"),
                "autor": row.get("nomeAutor") or row.get("autor"),
                "tipo": row.get("tipoEmenda"),
                "localidade": row.get("localidadeDoGasto"),
                "funcao": row.get("funcao") or row.get("nomeFuncao"),
                "valor_empenhado": _brl(row.get("valorEmpenhado")),
                "valor_pago": _brl(row.get("valorPago")),
                "person_id": row.get("_atlas_person_id"),
                "fetched_at": utc_now(),
            }
        )
    return emendas


def main() -> int:
    day = latest_day("cgu_portal")
    if not day:
        print("bronze cgu_portal ausente")
        return 0

    sancoes = []
    for fname, cadastro in (("ceis.json", "CEIS"), ("cnep.json", "CNEP")):
        for row in load_json_list(day / fname):
            pes = row.get("pessoa") or {}
            san = row.get("sancionado") or {}
            tip = row.get("tipoSancao") or {}
            cnpj = only_digits(
                row.get("_atlas_cnpj")
                or pes.get("cnpjFormatado")
                or san.get("codigoFormatado")
            )
            cad = row.get("_atlas_cadastro") or cadastro
            sancoes.append(
                {
                    "id_externo": f"cgu_{str(cad).lower()}:{row.get('id')}",
                    "cadastro": cad,
                    "fonte": "cgu_portal",
                    "nome": pes.get("nome") or san.get("nome"),
                    "cnpj": cnpj,
                    "tipo_sancao": tip.get("descricaoResumida") or tip.get("descricaoPortal"),
                    "inicio": row.get("dataInicioSancao"),
                    "fim": row.get("dataFimSancao"),
                    "orgao": (row.get("orgaoSancionador") or {}).get("nome"),
                    "uf": (row.get("orgaoSancionador") or {}).get("siglaUf"),
                    "processo": row.get("numeroProcesso"),
                    "fetched_at": utc_now(),
                }
            )

    emendas = silver_emendas_from_bronze(day)

    out_s = LAKE / "silver" / "sancoes"
    out_e = LAKE / "silver" / "emendas"
    out_s.mkdir(parents=True, exist_ok=True)
    out_e.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    write_jsonl(out_s / f"sancoes_{stamp}.jsonl", sancoes)
    write_jsonl(out_s / "sancoes_latest.jsonl", sancoes)
    write_jsonl(out_e / f"emendas_{stamp}.jsonl", emendas)
    write_jsonl(out_e / "emendas_latest.jsonl", emendas)

    print(f"OK silver CGU: sancoes={len(sancoes)} emendas={len(emendas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
