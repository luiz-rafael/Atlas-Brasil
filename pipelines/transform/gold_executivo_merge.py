#!/usr/bin/env python3
"""Merge pessoas do Executivo federal na gold (presidente/vice/ministro)."""

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
    base = LAKE / "bronze" / "executivo_federal"
    if not base.exists():
        return None
    days = [p for p in base.iterdir() if p.is_dir()]
    return max(days, key=lambda p: p.name) if days else None


def main() -> int:
    day = latest_day()
    if not day or not (day / "pessoas_executivo.jsonl").exists():
        print("bronze executivo ausente")
        return 0
    if not GOLD.exists():
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    n = 0
    for line in (day / "pessoas_executivo.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        eid = row["id"]
        cargo = row.get("cargo")
        cargo_label = row.get("cargo_label") or (
            f"Ministro(a) — {row['pasta']}" if row.get("pasta") else cargo
        )
        ents[eid] = {
            "id": eid,
            "tipo": "pessoa",
            "nome": row.get("nome"),
            "partido": row.get("partido"),
            "cargo_atual": cargo_label or cargo,
            "no_poder_2026": bool(row.get("no_poder")),
            "tags": list(row.get("tags") or ["executivo"]),
            "periodo_inicio": row.get("periodo_inicio"),
            "periodo_fim": row.get("periodo_fim"),
            "pagina_oficial": row.get("fonte_url"),
            "source_ids": [f"executivo:{eid}"],
            "perfil_atualizado_em": utc_now(),
        }
        if cargo and row.get("no_poder"):
            # instituição-cargo genérica + pasta quando houver
            cid = f"cargo_{cargo}"
            if cid not in ents:
                ents[cid] = {
                    "id": cid,
                    "tipo": "instituicao",
                    "nome": cargo.replace("_", " ").title(),
                    "tags": ["cargo", "executivo"],
                }
            rid = f"r_{eid}_{cid}_exerce"
            rels[rid] = {
                "id": rid,
                "origem": eid,
                "destino": cid,
                "tipo": "exerce_cargo",
                "periodo": row.get("periodo_inicio") or "",
                "contexto": row.get("pasta") or "Executivo federal",
                "justificativa_documental": f"Fonte: {row.get('fonte_url')}",
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [],
                "fontes": ["executivo_federal"],
            }
            if row.get("pasta"):
                pasta_id = "inst_planalto"
                if pasta_id not in ents:
                    ents[pasta_id] = {
                        "id": pasta_id,
                        "tipo": "instituicao",
                        "nome": "Presidência da República / Esplanada",
                        "tags": ["executivo", "governo_federal"],
                    }
                rid2 = f"r_{eid}_{pasta_id}_membro_gabinete"
                rels[rid2] = {
                    "id": rid2,
                    "origem": eid,
                    "destino": pasta_id,
                    "tipo": "membro_de",
                    "periodo": row.get("periodo_inicio") or "",
                    "contexto": f"Titular: {row.get('pasta')}",
                    "justificativa_documental": f"Gabinete federal — {row.get('fonte_url')}",
                    "grau_confirmacao": "fato_documentado",
                    "fonte_ids": [],
                    "fontes": ["executivo_federal"],
                }
        n += 1

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb.setdefault("meta", {})["executivo_federal"] = {"em": utc_now(), "pessoas": n}
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    print(f"OK gold executivo: {n} pessoas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
