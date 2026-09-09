"""Serving Dinheiro — categorias separadas (não misturar Contas).

Contrato ≠ emenda ≠ campanha ≠ transferência ≠ sanção.
Nunca classificar automaticamente como ilegal.
"""

from __future__ import annotations

from typing import Any

from app.cache import cache_get, cache_set
from app.kb_loader import load_kb

DISCLAIMER = (
    "O Atlas não acusa. O Atlas documenta. "
    "Contrato, emenda, transferência ou sanção ≠ ilegalidade automática. "
    "Não misturar com Contas do Brasil (resultado fiscal / dívida)."
)

TABS = (
    "contratos",
    "licitacoes",
    "emendas",
    "transferencias",
    "sancoes",
    "empresas",
    "fluxos",
    "caminhos",
)


def _bundle() -> dict[str, Any]:
    hit = cache_get("dinheiro:bundle:v1")
    if hit:
        return hit
    kb = load_kb()
    ents = kb.get("entidades") or []
    contratos = sorted(
        [e for e in ents if e.get("tipo") == "contrato"],
        key=lambda e: e.get("valor") or 0,
        reverse=True,
    )[:200]
    licitacoes = [e for e in ents if e.get("tipo") == "licitacao"][:80]
    emendas = sorted(
        [e for e in ents if e.get("tipo") == "emenda"],
        key=lambda e: e.get("valor") or 0,
        reverse=True,
    )[:80]
    transferencias = [e for e in ents if e.get("tipo") == "transferencia"][:80]
    sancoes = [e for e in ents if e.get("tipo") == "sancao"][:60]
    empresas = sorted(
        [
            e
            for e in ents
            if e.get("tipo") == "empresa"
            and (
                e.get("contratos_count")
                or e.get("valor_contratos")
                or "sancionada" in (e.get("tags") or [])
            )
        ],
        key=lambda e: e.get("valor_contratos") or 0,
        reverse=True,
    )[:40]
    fluxos = kb.get("fluxos_financeiros") or []
    caminhos = (
        (
            (kb.get("meta") or {})
            .get("cruzamento_f6", {})
            .get("amostra")
        )
        or [
            {
                "empresa_id": e.get("id"),
                "cnpj": e.get("cnpj"),
                "nome": e.get("nome"),
                "emendas": (e.get("cruzamento") or {}).get("emendas"),
                "contratos": (e.get("cruzamento") or {}).get("contratos"),
            }
            for e in ents
            if "cruzamento_emenda_contrato" in (e.get("tags") or [])
        ]
    )
    out = {
        "contratos": [_card(e) for e in contratos],
        "licitacoes": [_card(e) for e in licitacoes],
        "emendas": [_card(e) for e in emendas],
        "transferencias": [_card(e) for e in transferencias],
        "sancoes": [_card(e) for e in sancoes],
        "empresas": [_card(e) for e in empresas],
        "fluxos": fluxos[:100],
        "caminhos": caminhos[:80] if isinstance(caminhos, list) else [],
        "counts": {
            "contratos": len(contratos),
            "licitacoes": len(licitacoes),
            "emendas": len(emendas),
            "transferencias": len(transferencias),
            "sancoes": len(sancoes),
            "empresas": len(empresas),
            "fluxos": min(100, len(fluxos)),
            "caminhos": len(caminhos) if isinstance(caminhos, list) else 0,
        },
    }
    cache_set("dinheiro:bundle:v1", out, 300)
    return out


def _card(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": e.get("id"),
        "nome": e.get("nome") or e.get("titulo") or e.get("id"),
        "tipo": e.get("tipo"),
        "valor": e.get("valor") or e.get("valor_contratos"),
        "cnpj": e.get("cnpj"),
        "uf": e.get("uf"),
        "tags": e.get("tags") or [],
        "periodo": e.get("periodo"),
        "orgao": e.get("orgao"),
        "caso_id": e.get("caso_id"),
    }


def dinheiro_resumo() -> dict[str, Any]:
    b = _bundle()
    return {
        "ok": True,
        "counts": b["counts"],
        "disclaimer": DISCLAIMER,
        "note": (
            "Categorias são separadas semanticamente. "
            "Contas do Brasil ficam em /v1/contas — não somar aqui."
        ),
        "source": "kb_gateway_cached",
    }


def dinheiro_categoria(
    tab: str,
    *,
    caso_id: str | None = None,
    uf: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    t = (tab or "contratos").lower()
    if t not in TABS:
        t = "contratos"
    b = _bundle()
    items = list(b.get(t) or [])
    if caso_id and t == "fluxos":
        items = [f for f in items if f.get("caso_id") == caso_id]
    elif caso_id:
        items = [i for i in items if i.get("caso_id") == caso_id]
    uf_n = (uf or "").strip().upper()
    if uf_n:
        items = [i for i in items if (i.get("uf") or "").upper() == uf_n]
    qn = (q or "").strip().lower()
    if qn:
        items = [
            i
            for i in items
            if qn
            in " ".join(
                [
                    str(i.get("nome") or ""),
                    str(i.get("cnpj") or ""),
                    str(i.get("orgao") or ""),
                    str(i.get("tipo") or ""),
                ]
            ).lower()
        ]
    # ranking por valor (maior primeiro); nulos no fim
    items.sort(
        key=lambda i: (
            0 if i.get("valor") is not None else 1,
            -(float(i["valor"]) if i.get("valor") is not None else 0.0),
        )
    )
    limit = max(1, min(int(limit), 500))
    return {
        "ok": True,
        "tab": t,
        "total": len(items),
        "items": items[:limit],
        "counts": b["counts"],
        "disclaimer": DISCLAIMER,
        "source": "kb_gateway_cached",
        "filters": {"uf": uf_n or None, "q": qn or None},
    }
