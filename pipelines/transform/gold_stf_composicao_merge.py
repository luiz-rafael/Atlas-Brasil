#!/usr/bin/env python3
"""Merge composição STF (pessoas + instituição + exerce_cargo) na gold KB."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"


def latest_day() -> Path | None:
    base = LAKE / "bronze" / "stf_composicao"
    if not base.exists():
        return None
    days = [p for p in base.iterdir() if p.is_dir()]
    return max(days, key=lambda p: p.name) if days else None


def main() -> int:
    day = latest_day()
    if not day or not (day / "pessoas_stf.jsonl").exists():
        print("bronze stf_composicao ausente")
        return 0
    if not GOLD.exists():
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}

    inst_path = day / "instituicao.json"
    if inst_path.exists():
        inst = json.loads(inst_path.read_text(encoding="utf-8"))
        iid = inst["id"]
        ents[iid] = {
            "id": iid,
            "tipo": "instituicao",
            "nome": inst.get("nome") or "Supremo Tribunal Federal",
            "tags": list(inst.get("tags") or ["judiciario", "stf"]),
            "pagina_oficial": inst.get("fonte_url"),
            "perfil_atualizado_em": utc_now(),
        }

    n = 0
    for line in (day / "pessoas_stf.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        eid = row["id"]
        ents[eid] = {
            "id": eid,
            "tipo": "pessoa",
            "nome": row.get("nome"),
            "partido": row.get("partido"),
            "cargo_atual": row.get("cargo_label") or row.get("cargo_atual") or "Ministro do STF",
            "no_poder_2026": bool(row.get("no_poder")),
            "tags": list(row.get("tags") or ["judiciario", "ministro_stf"]),
            "pagina_oficial": row.get("fonte_url"),
            "source_ids": [f"stf:{eid}"],
            "perfil_atualizado_em": utc_now(),
        }
        rid = f"r_{eid}_inst_stf_exerce"
        rels[rid] = {
            "id": rid,
            "origem": eid,
            "destino": "inst_stf",
            "tipo": "exerce_cargo",
            "periodo": "",
            "contexto": "Ministro(a) do Supremo Tribunal Federal",
            "justificativa_documental": f"Composição STF — {row.get('fonte_url')}",
            "grau_confirmacao": "fato_documentado",
            "fonte_ids": [],
            "fontes": ["stf_composicao"],
        }
        n += 1

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb.setdefault("meta", {})["stf_composicao"] = {
        "em": utc_now(),
        "ministros": n,
        "vagas_abertas": 1,
    }
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    print(f"OK gold stf_composicao: {n} ministros")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
