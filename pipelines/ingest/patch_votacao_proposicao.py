#!/usr/bin/env python3
"""
Patch: baixa só votacoesProposicoes e religa votos já no bronze Câmara.
Útil sem rebaixar proposicoes/votos inteiros.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, http_get, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.config.escopo import anos_periodo  # noqa: E402

BASE = "https://dadosabertos.camara.leg.br/arquivos"


def anos() -> list[int]:
    raw = os.getenv("LEG_ANOS", "").strip()
    if raw:
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]
    # default: o que já coletamos recentemente, senão período Atlas
    return [2022, 2023, 2024, 2025, 2026]


def iter_csv_rows(raw: bytes):
    text = raw.decode("utf-8-sig", errors="replace")
    if text.startswith("Lista") or text.startswith("\ufeffLista"):
        text = "\n".join(text.splitlines()[1:])
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for row in reader:
        yield {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}


def latest_cam_day() -> Path | None:
    base = LAKE / "bronze" / "camara_legislativo"
    if not base.exists():
        return None
    days = [p for p in base.iterdir() if p.is_dir() and (p / "votos.jsonl").exists()]
    days = [p for p in days if len(p.name) == 10 and p.name[4] == "-"] or days
    return max(days, key=lambda p: p.name) if days else None


def main() -> int:
    day = latest_cam_day()
    if not day:
        print("bronze camara_legislativo ausente", file=sys.stderr)
        return 1
    voto_prop: dict[str, dict] = {}
    for ano in anos():
        url = f"{BASE}/votacoesProposicoes/csv/votacoesProposicoes-{ano}.csv"
        print(f"  baixando {ano}…", flush=True)
        r = http_get(url, timeout=300.0)
        if r.status_code != 200:
            print(f"  fail {ano} HTTP {r.status_code}", file=sys.stderr)
            continue
        (day / f"votacoesProposicoes-{ano}.csv").write_bytes(r.content)
        for row in iter_csv_rows(r.content):
            vid = str(row.get("idVotacao") or "").strip()
            if not vid:
                continue
            voto_prop[vid] = {
                "id_proposicao": str(row.get("proposicao_id") or "").strip(),
                "proposicao_titulo": row.get("proposicao_titulo"),
                "proposicao_ementa": (row.get("proposicao_ementa") or "")[:400],
                "proposicao_sigla": row.get("proposicao_siglaTipo"),
                "proposicao_numero": row.get("proposicao_numero"),
                "proposicao_ano": row.get("proposicao_ano"),
                "votacao_descricao": (row.get("descricao") or "")[:300],
                "votacao_data": row.get("data"),
            }

    votos_path = day / "votos.jsonl"
    votos = [
        json.loads(l) for l in votos_path.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    linked = 0
    for v in votos:
        vid = str(v.get("id_votacao") or "")
        meta = voto_prop.get(vid) or {}
        if meta.get("id_proposicao"):
            v.update(
                {
                    "id_proposicao": meta.get("id_proposicao"),
                    "proposicao_titulo": meta.get("proposicao_titulo"),
                    "proposicao_sigla": meta.get("proposicao_sigla"),
                    "proposicao_numero": meta.get("proposicao_numero"),
                    "proposicao_ano": meta.get("proposicao_ano"),
                    "proposicao_ementa": meta.get("proposicao_ementa"),
                }
            )
            linked += 1
    write_jsonl(votos_path, votos)
    write_jsonl(
        day / "votacao_proposicao.jsonl",
        [{"id_votacao": k, **v} for k, v in voto_prop.items()],
    )
    resumo = {}
    if (day / "resumo.json").exists():
        resumo = json.loads((day / "resumo.json").read_text(encoding="utf-8"))
    resumo.update(
        {
            "patched_votacao_proposicao_em": utc_now(),
            "votacao_proposicao": len(voto_prop),
            "votos_com_proposicao": linked,
        }
    )
    write_json(day / "resumo.json", resumo)
    print(f"OK patch: {linked}/{len(votos)} votos ligados a proposição · mapa={len(voto_prop)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
