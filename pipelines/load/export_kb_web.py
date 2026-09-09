#!/usr/bin/env python3
"""
Exporta KB enxuta para o Next.js (< ~200MB).

A gold completa (~580MB) estoura o limite de string do Node/webpack.
Mantém políticos de Casa, emendas, empresas ligadas e relações relevantes;
remove stubs TSE órfãos e nós proposicao (já resumidos no perfil).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import write_json  # noqa: E402

SRC = ROOT / "data" / "atlas-brasil-kb-v2.json"
OUT = ROOT / "data" / "atlas-brasil-kb-web.json"


def slim_pessoa(e: dict) -> dict:
    out = dict(e)
    leg = out.get("legislativo_resumo")
    if isinstance(leg, dict):
        lista = leg.get("proposicoes_lista") or []
        out["legislativo_resumo"] = {
            **leg,
            "proposicao_ids": None,
            "proposicoes_lista": lista[:80],
            "proposicoes_sample": (leg.get("proposicoes_sample") or lista)[:12],
            "votos_por_proposicao": (leg.get("votos_por_proposicao") or [])[:30],
            "votos_projetos": (leg.get("votos_projetos") or [])[:24],
        }
    if out.get("despesas_campanha"):
        out["despesas_campanha"] = out["despesas_campanha"][:12]
    if out.get("despesas_resumo") and isinstance(out["despesas_resumo"], list):
        for bloco in out["despesas_resumo"]:
            if isinstance(bloco, dict) and bloco.get("fornecedores"):
                bloco["fornecedores"] = bloco["fornecedores"][:12]
    if out.get("emendas_resumo") and isinstance(out["emendas_resumo"], list):
        out["emendas_resumo"] = out["emendas_resumo"][:40]
    return out


def keep_pessoa(e: dict) -> bool:
    """Casa + governadores (mandato TSE)."""
    eid = e.get("id") or ""
    if eid.startswith(("p_cam_", "p_sen_")):
        return True
    tags = set(e.get("tags") or [])
    if tags & {"tem_mandato_governador", "governador", "fase7"}:
        return True
    cargo = (e.get("cargo_atual") or "").lower()
    if "governador" in cargo:
        return True
    return False


def main() -> int:
    if not SRC.exists():
        print(f"fonte ausente: {SRC}", file=sys.stderr)
        return 1
    print(f"lendo {SRC} …", flush=True)
    kb = json.loads(SRC.read_text(encoding="utf-8"))

    keep_ids: set[str] = set()
    pessoas: list[dict] = []
    outros: list[dict] = []

    for e in kb.get("entidades") or []:
        t = e.get("tipo")
        eid = e.get("id") or ""
        if t == "pessoa":
            if keep_pessoa(e):
                pessoas.append(slim_pessoa(e))
                keep_ids.add(eid)
        elif t == "proposicao":
            continue  # só no resumo legislativo
        elif t in (
            "emenda",
            "partido",
            "instituicao",
            "sancao",
            "contrato",
            "licitacao",
            "transferencia",
            "caso",
            "estado",
            "mandato",
            "regiao",
            "pais",
        ):
            outros.append(e)
            keep_ids.add(eid)
        elif t == "empresa":
            outros.append(e)  # filtramos depois pelas relações
        else:
            outros.append(e)
            keep_ids.add(eid)

    # relações: pessoa Casa + cadeia de emenda + contratos PNCP
    pessoa_ids = {e["id"] for e in pessoas}
    emenda_ids = {
        e["id"] for e in outros if e.get("tipo") == "emenda"
    }
    # emendas ligadas a políticos mantidos
    emendas_de_pessoa: set[str] = set()
    for r in kb.get("relacoes") or []:
        if r.get("tipo") != "autor_de_emenda":
            continue
        if r.get("origem") in pessoa_ids and r.get("destino"):
            emendas_de_pessoa.add(r["destino"])

    rels_keep: list[dict] = []
    empresa_ids: set[str] = set()
    contrato_ids: set[str] = set()
    for r in kb.get("relacoes") or []:
        o, d = r.get("origem"), r.get("destino")
        tipo = r.get("tipo") or ""
        keep = False
        if o in pessoa_ids or d in pessoa_ids:
            keep = True
        elif tipo == "emenda_beneficiou" and o in emendas_de_pessoa:
            keep = True
        elif tipo == "fornecido_por" and str(o).startswith("ctr_"):
            keep = True
        elif tipo in (
            "licitacao_gerou_contrato",
            "orgao_contratou",
            "orgao_abriu_licitacao",
            "compartilha_fornecedor_cnpj",
        ):
            keep = True
        if not keep:
            continue
        rels_keep.append(r)
        for x in (o, d):
            if not x:
                continue
            keep_ids.add(x)
            if str(x).startswith("e_"):
                empresa_ids.add(x)
            if str(x).startswith("em_"):
                emenda_ids.add(x)
            if str(x).startswith("ctr_"):
                contrato_ids.add(x)
            if str(x).startswith("lic_"):
                keep_ids.add(x)

    empresas = [e for e in outros if e.get("tipo") == "empresa" and e.get("id") in empresa_ids]
    contratos = [e for e in outros if e.get("tipo") == "contrato" and e.get("id") in contrato_ids]
    # se não há rel filtro, ainda inclui amostra de contratos recentes
    if not contratos:
        contratos = [e for e in outros if e.get("tipo") == "contrato"][:500]
        for e in contratos:
            keep_ids.add(e["id"])
    resto = [
        e
        for e in outros
        if e.get("tipo") not in ("empresa", "contrato") and e.get("id") in keep_ids
    ]

    web = {
        **{k: v for k, v in kb.items() if k not in ("entidades", "relacoes")},
        "entidades": pessoas + resto + empresas + contratos,
        "relacoes": rels_keep,
        "meta": {
            **(kb.get("meta") or {}),
            "web_export": {
                "fonte": str(SRC.name),
                "pessoas": len(pessoas),
                "empresas": len(empresas),
                "contratos": len(contratos),
                "rels": len(rels_keep),
                "omitiu_proposicoes": True,
                "omitiu_stubs_tse": True,
            },
        },
    }
    write_json(OUT, web)
    mb = OUT.stat().st_size / 1e6
    print(
        f"OK web KB: {mb:.1f} MB · pessoas={len(pessoas)} "
        f"empresas={len(empresas)} contratos={len(contratos)} "
        f"rels={len(rels_keep)} → {OUT.name}"
    )
    if mb > 450:
        print("aviso: ainda grande para Node string limit", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
