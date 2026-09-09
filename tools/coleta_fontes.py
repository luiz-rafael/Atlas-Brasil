#!/usr/bin/env python3
"""Auditoria de coleta de fontes — gaps de URL, fonte_ids e nível 4 solo."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "atlas-brasil-kb-v2.json"


def is_https(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def main() -> int:
    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))
    docs = {d["id"]: d for d in kb.get("documentos", [])}
    gaps_url = []
    for d in docs.values():
        url = d.get("url") or d.get("url_ref") or ""
        if not is_https(str(url)):
            gaps_url.append(d["id"])

    gaps_fid = []
    nivel4_solo = []
    for r in kb.get("relacoes", []):
        fids = r.get("fonte_ids") or []
        if not fids:
            gaps_fid.append(r["id"])
            continue
        niveis = []
        for fid in fids:
            doc = docs.get(fid)
            if doc:
                niveis.append(doc.get("nivel_fonte") or "")
        if niveis and all(n.startswith("4") for n in niveis):
            nivel4_solo.append(r["id"])

    linked = set()
    for r in kb.get("relacoes", []):
        linked.add(r["origem"])
        linked.add(r["destino"])
    for rpc in kb.get("registros_pessoa_caso", []):
        linked.add(rpc["pessoa_id"])
        linked.add(rpc["caso_id"])
    orphans = [
        e["id"]
        for e in kb.get("entidades", [])
        if e["id"] not in linked and not e.get("isolada")
    ]

    print("=== COLETA FONTES — relatório ===")
    print(f"documentos={len(docs)} sem_url_https={len(gaps_url)}")
    for x in gaps_url[:20]:
        print(f"  URL gap: {x}")
    print(f"arestas sem fonte_ids={len(gaps_fid)}")
    for x in gaps_fid[:20]:
        print(f"  FID gap: {x}")
    print(f"arestas só nível 4={len(nivel4_solo)}")
    for x in nivel4_solo[:20]:
        print(f"  N4 solo: {x}")
    print(f"entidades órfãs (sem isolada)={len(orphans)}")
    for x in orphans[:20]:
        print(f"  orphan: {x}")

    report = {
        "sem_url_https": gaps_url,
        "sem_fonte_ids": gaps_fid,
        "nivel4_solo": nivel4_solo,
        "orphans": orphans,
    }
    out = ROOT / "data" / "coleta-fontes-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"escrito {out}")

    # não falha o CI por URL pendente no MVP — só por órfão sem flag
    if orphans:
        print("FALHOU: órfãos sem flag isolada")
        return 1
    print("OK (órfãos limpos; revisar gaps de URL manualmente)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
