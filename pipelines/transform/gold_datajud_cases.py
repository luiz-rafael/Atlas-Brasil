#!/usr/bin/env python3
"""
Gold DataJud: materializa LEGAL_CASE na KB sem arestas acusatórias automáticas.

Se seed_entity_id existir → mentioned_in (documental) APENAS, com nota de que
a ligação pessoa↔NPU veio da seed_source, não do DataJud como descoberta de PF.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    sil = LAKE / "silver" / "legal"
    cases = read_jsonl(sil / "legal_cases_latest.jsonl")
    if not cases:
        print("SKIPPED gold_datajud: sem legal_cases", flush=True)
        return 0
    if not GOLD.exists():
        print("gold KB ausente", file=sys.stderr)
        return 1

    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    casos = {c["id"]: c for c in kb.get("casos") or []}
    now = utc_now()
    n_case = 0
    n_rel = 0

    for c in cases:
        cid = c.get("case_id")
        if not cid:
            continue
        nome = f"Processo {c.get('process_number')}"
        casos[cid] = {
            "id": cid,
            "nome": nome,
            "periodo": str((c.get("retrieved_at") or "")[:4] or ""),
            "eixos": ["judiciario"],
            "tags": ["datajud", "legal_case", "metadados"],
            "cnj_number": c.get("process_number"),
            "court": c.get("court"),
            "source": "cnj_datajud",
        }
        ents[cid] = {
            "id": cid,
            "tipo": "caso",
            "nome": nome,
            "tags": ["datajud", "legal_case", "metadados_only"],
            "source_ids": ["cnj_datajud"],
            "attrs": {
                "process_number": c.get("process_number"),
                "court": c.get("court"),
                "grau": c.get("jurisdiction_degree"),
                "classe": c.get("procedural_class"),
                "last_checked_at": now,
            },
        }
        n_case += 1

        ent = c.get("seed_entity_id")
        if ent and ent in ents:
            rid = f"r_{ent}_{cid}_mentioned"
            rels[rid] = {
                "id": rid,
                "origem": ent,
                "destino": cid,
                "tipo": "mentioned_in",
                "periodo": "",
                "contexto": "NPU enriquecida via DataJud; ligação seed≠descoberta por nome no DataJud",
                "justificativa_documental": (
                    f"Processo {c.get('process_number')} enriquecido no DataJud. "
                    f"Seed: {c.get('seed_source_id') or 'queue'}. "
                    "Portaria 374/2026: não assumir polo PF público."
                ),
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": ["cnj_datajud", c.get("seed_source_id") or "seed_queue"],
                "fontes": ["cnj_datajud"],
                "nota": "MENTIONED_IN apenas. Sem CONVICTED/ACCUSED automático.",
            }
            n_rel += 1

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["casos"] = list(casos.values())
    write_json(GOLD, kb)
    write_json(ACTIVE, kb)
    # artefato separado de movimentos (não vai todo para grafo)
    movs = read_jsonl(sil / "case_movements_latest.jsonl")
    write_json(
        ROOT / "data" / "atlas-brasil-legal-movements.json",
        {"em": now, "cases": n_case, "movements": len(movs), "mentioned_links": n_rel},
    )
    print(f"OK gold DataJud: cases={n_case} mentioned_in={n_rel} movs_file={len(movs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
