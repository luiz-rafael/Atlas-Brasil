"""Contexto território + ano — Fase C.

Retorna administração vigente + indicadores observados no território/ano.
Não atribui causalidade pessoa↔indicador.
"""

from __future__ import annotations

from typing import Any

from app import serving_administrations as serving_adm
from app import serving_indicadores as serving_ind

DISCLAIMER = (
    "O Atlas não acusa. O Atlas documenta. "
    "Indicadores durante uma administração ≠ efeito causal do titular. "
    "Join é temporal/territorial, não acusatório."
)

DEFAULT_INDICATORS = (
    "ind_pop_estimada",
    "ind_pib_corrente",
    "ind_pib_per_capita",
    "ind_ideb_anos_iniciais",
    "ind_receita_bruta",
    "ind_despesa_total",
    "ind_caged_saldo",
)


def _normalize_territory_id(territory_id: str) -> str:
    t = (territory_id or "").strip()
    if len(t) == 2 and t.isalpha():
        return f"uf_{t.upper()}"
    if t.upper().startswith("UF_") and not t.startswith("uf_"):
        return f"uf_{t[3:].upper()}"
    return t


def territory_year_context(
    territory_id: str,
    year: int,
    *,
    indicator_ids: list[str] | None = None,
) -> dict[str, Any]:
    tid = _normalize_territory_id(territory_id)
    terr = serving_ind.get_territory(tid)
    admin = serving_adm.administration_at(tid, year)

    inds = indicator_ids or list(DEFAULT_INDICATORS)
    observations: list[dict[str, Any]] = []
    for iid in inds:
        rows = serving_ind.observations(
            indicator_id=iid,
            year=year,
            territory_id=tid,
            limit=5,
        )
        for r in rows:
            observations.append(r)

    return {
        "ok": True,
        "territory_id": tid,
        "year": year,
        "territory": terr,
        "administration": admin,
        "indicators": observations,
        "indicator_ids_requested": inds,
        "disclaimer": DISCLAIMER,
        "note": (
            "Administração e indicadores são joinados por território+ano. "
            "Não implica responsabilidade pessoal pelos valores observados."
        ),
    }
