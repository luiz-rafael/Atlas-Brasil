#!/usr/bin/env python3
"""
ER leve: cruza pessoas Câmara/Senado com candidatos TSE que têm bens.
Match por nome normalizado + UF (único). Não funde IDs — copia bens e cria same_as.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import utc_now, write_json  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"


def norm_name(s: str | None) -> str:
    s = (s or "").upper()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def names_of(e: dict) -> list[str]:
    out = []
    for n in [e.get("nome"), e.get("nome_civil"), *(e.get("aliases") or [])]:
        nn = norm_name(n)
        if nn and nn not in out:
            out.append(nn)
    return out


def main() -> int:
    if not GOLD.exists():
        print("gold ausente", file=sys.stderr)
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}

    tse_bens = [
        e
        for e in ents.values()
        if e["id"].startswith("p_tse_") and e.get("bens_declarados")
    ]
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in tse_bens:
        uf = (e.get("uf") or "").upper()
        for n in names_of(e):
            by_key[(n, uf)].append(e)

    matched = 0
    skipped_ambig = 0
    casas = [
        e
        for e in ents.values()
        if e["id"].startswith(("p_cam_", "p_sen_")) and e.get("tipo") == "pessoa"
    ]

    for casa in casas:
        uf = (casa.get("uf") or "").upper()
        hits: dict[str, dict] = {}
        for n in names_of(casa):
            for h in by_key.get((n, uf)) or []:
                hits[h["id"]] = h
        if len(hits) > 1:
            skipped_ambig += 1
            continue
        if len(hits) != 1:
            continue
        tse = next(iter(hits.values()))
        # copia bens (não sobrescreve se já tiver)
        if not casa.get("bens_declarados"):
            casa["bens_declarados"] = {
                **tse["bens_declarados"],
                "er_via": tse["id"],
                "er_metodo": "nome_uf",
            }
        # same_as
        rid = f"r_{casa['id']}_{tse['id']}_same_as"
        if rid not in rels:
            rels[rid] = {
                "id": rid,
                "origem": casa["id"],
                "destino": tse["id"],
                "tipo": "same_as",
                "periodo": "er",
                "contexto": "Mesma pessoa (nome+UF) — IDs não fundidos",
                "justificativa_documental": (
                    f"Resolução de entidade por nome normalizado e UF "
                    f"entre {casa['id']} e {tse['id']}"
                ),
                "grau_confirmacao": "hipotese_forte",
                "fonte_ids": [],
                "fontes": ["er_casas_tse"],
            }
        # link tse id em source_ids
        sids = list(casa.get("source_ids") or [])
        tse_sid = f"tse:{tse['id'].replace('p_tse_', '', 1)}"
        if tse_sid not in sids:
            sids.append(tse_sid)
        casa["source_ids"] = sids
        tags = list(casa.get("tags") or [])
        if "er_tse_bens" not in tags:
            tags.append("er_tse_bens")
        casa["tags"] = tags
        matched += 1

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb.setdefault("meta", {})["er_casas_tse"] = {
        "em": utc_now(),
        "matched": matched,
        "ambig_skipped": skipped_ambig,
        "tse_com_bens": len(tse_bens),
    }

    write_json(GOLD, kb)
    write_json(ROOT / "data" / "lake" / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)

    print(f"OK ER casas↔TSE bens: matched={matched} ambig={skipped_ambig}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
