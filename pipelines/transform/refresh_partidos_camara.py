#!/usr/bin/env python3
"""
Atualiza partido/UF/nome dos deputados na gold a partir da lista ATUAL da Câmara.

Corrige base congelada em partidos históricos (ex.: DEM → MISSÃO) sem recoleta completa.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import http_get, utc_now, write_json, LAKE  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"
BASE = "https://dadosabertos.camara.leg.br/api/v2"
HEADERS = {"Accept": "application/json"}


def fetch_json(url: str) -> dict:
    r = http_get(url, headers=HEADERS, timeout=90.0)
    r.raise_for_status()
    return r.json()


def paginate_atuais() -> list[dict]:
    url = f"{BASE}/deputados?itens=100&ordem=ASC&ordenarPor=nome"
    rows: list[dict] = []
    while url:
        data = fetch_json(url)
        rows.extend(data.get("dados") or [])
        next_link = None
        for link in data.get("links") or []:
            if link.get("rel") == "next":
                next_link = link.get("href")
                break
        url = next_link
        print(f"  lista atual +{len(data.get('dados') or [])} (total {len(rows)})")
    return rows


def cam_id(e: dict) -> str | None:
    for s in e.get("source_ids") or []:
        if str(s).startswith("cam:"):
            return str(s)[4:]
    eid = e.get("id") or ""
    if eid.startswith("p_cam_"):
        return eid[6:]
    return None


def main() -> int:
    if not GOLD.exists():
        print("gold ausente", file=sys.stderr)
        return 1
    atuais = {str(d["id"]): d for d in paginate_atuais() if d.get("id") is not None}
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    changed = 0
    demoted = 0
    samples: list[str] = []
    for e in kb.get("entidades") or []:
        if e.get("tipo") != "pessoa":
            continue
        cid = cam_id(e)
        if not cid:
            continue
        if cid in atuais:
            d = atuais[cid]
            novo_partido = (d.get("siglaPartido") or "").strip()
            novo_uf = (d.get("siglaUf") or "").strip().upper()[:2] or None
            novo_nome = d.get("nome")
            old_p = e.get("partido")
            touched = False
            if novo_partido and novo_partido != old_p:
                e["partido"] = novo_partido
                tags = [t for t in (e.get("tags") or []) if not str(t).startswith("partido:")]
                tags.append(f"partido:{novo_partido}")
                e["tags"] = tags
                touched = True
                if len(samples) < 12:
                    samples.append(f"{e.get('nome')}: {old_p} → {novo_partido}")
            if novo_uf and novo_uf != e.get("uf"):
                e["uf"] = novo_uf
                touched = True
            if novo_nome and novo_nome != e.get("nome"):
                e["nome"] = novo_nome
                touched = True
            if d.get("email") and not e.get("email"):
                e["email"] = d.get("email")
                touched = True
            if d.get("urlFoto") and not e.get("foto_url"):
                e["foto_url"] = d.get("urlFoto")
                touched = True
            if not e.get("no_poder_2026"):
                e["no_poder_2026"] = True
                touched = True
            e["situacao_casa"] = "Exercício"
            if touched:
                e["perfil_atualizado_em"] = utc_now()
                changed += 1
        else:
            # Histórico / vacância: não marcar como no poder
            if e.get("no_poder_2026"):
                e["no_poder_2026"] = False
                e["situacao_casa"] = e.get("situacao_casa") or "Fora de exercício"
                e["perfil_atualizado_em"] = utc_now()
                demoted += 1
                changed += 1

    # Detalhe pontual: quem saiu recentemente e ainda tem partido antigo (amostra prioritária)
    # Eduardo Bolsonaro e similares — fetch detail se partido claramente legado
    legacy_parties = {"DEM", "PTB", "PFL", "PMDB", "PPS", "PR", "PRB", "PSC", "PP**", "PAN", "PTN", "PHS", "PRONA", "SDD"}
    detail_fixed = 0
    for e in kb.get("entidades") or []:
        if e.get("tipo") != "pessoa":
            continue
        cid = cam_id(e)
        if not cid or cid in atuais:
            continue
        partido = (e.get("partido") or "").upper()
        if partido not in legacy_parties and e.get("id") != "p_cam_92346":
            continue
        if detail_fixed >= 40 and e.get("id") != "p_cam_92346":
            continue
        try:
            det = fetch_json(f"{BASE}/deputados/{cid}").get("dados") or {}
        except Exception:
            continue
        ult = det.get("ultimoStatus") or {}
        novo = (ult.get("siglaPartido") or "").strip()
        if novo:
            e["partido"] = novo
            tags = [t for t in (e.get("tags") or []) if not str(t).startswith("partido:")]
            tags.append(f"partido:{novo}")
            e["tags"] = tags
        if ult.get("siglaUf"):
            e["uf"] = str(ult.get("siglaUf")).upper()[:2]
        if ult.get("situacao"):
            e["situacao_casa"] = ult.get("situacao")
        if det.get("nomeCivil"):
            e["nome_civil"] = det.get("nomeCivil")
        e["no_poder_2026"] = (ult.get("situacao") or "").lower() in {
            "exercício",
            "exercicio",
        }
        e["perfil_atualizado_em"] = utc_now()
        detail_fixed += 1
        if e.get("id") == "p_cam_92346":
            samples.append(
                f"Eduardo Bolsonaro detalhe: partido={e.get('partido')} situacao={e.get('situacao_casa')} no_poder={e.get('no_poder_2026')}"
            )

    kb.setdefault("meta", {})["refresh_partidos_camara"] = {
        "em": utc_now(),
        "deputados_api": len(atuais),
        "atualizados": changed,
        "rebaixados_fora_exercicio": demoted,
        "detalhes_legados": detail_fixed,
        "amostra": samples,
    }
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    print(f"OK refresh partidos: {changed} perfis atualizados / {len(atuais)} em exercício")
    print(f"  fora de exercício corrigidos: {demoted}; detalhes legados: {detail_fixed}")
    for s in samples:
        print(f"  {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
