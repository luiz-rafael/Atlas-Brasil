"""Queries Postgres para serving de indicadores (Fase C)."""

from __future__ import annotations

import os
from typing import Any

from app.db import get_conn


def _fontes_from_pg_enabled() -> bool:
    raw = os.getenv("ATLAS_FONTES_FROM_PG", "1").lower()
    return raw in ("1", "true", "yes")


def pg_ready() -> bool:
    conn = get_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM observations LIMIT 1")
            return cur.fetchone() is not None
    except Exception:
        return False


def meta() -> dict[str, Any]:
    conn = get_conn()
    if not conn:
        raise RuntimeError("Postgres indisponível")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM territories")
        n_t = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM indicators")
        n_i = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM observations")
        n_o = cur.fetchone()[0]
        cur.execute(
            "SELECT valor FROM meta_sistema WHERE chave='serving_indicadores'"
        )
        row = cur.fetchone()
        sync = row[0] if row else None
    return {
        "territories": n_t,
        "indicators": n_i,
        "observations": n_o,
        "sync": sync,
        "source": "postgres",
    }


def list_indicators() -> list[dict[str, Any]]:
    conn = get_conn()
    if not conn:
        raise RuntimeError("Postgres indisponível")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indicator_id, name, display_name, description, category,
                   subcategory, unit, source_id, dataset_id,
                   minimum_geographic_level, methodology_url, notes
            FROM indicators
            ORDER BY indicator_id
            """
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_territories(
    *,
    territory_type: str | None = None,
    state_code: str | None = None,
    limit: int = 10000,
) -> list[dict[str, Any]]:
    conn = get_conn()
    if not conn:
        raise RuntimeError("Postgres indisponível")
    clauses: list[str] = []
    params: list[Any] = []
    if territory_type:
        clauses.append("territory_type = %s")
        params.append(territory_type)
    if state_code:
        clauses.append("state_code = %s")
        params.append(state_code.upper())
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT territory_id, ibge_code, name, territory_type,
                   state_code, state_name, region_code, region_name, fonte
            FROM territories
            {where}
            ORDER BY territory_id
            LIMIT %s
            """,
            params,
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_territory(territory_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    if not conn:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT territory_id, ibge_code, name, territory_type,
                   state_code, state_name, region_code, region_name, fonte
            FROM territories WHERE territory_id = %s
            """,
            (territory_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def years_for_indicator(indicator_id: str) -> list[int]:
    conn = get_conn()
    if not conn:
        raise RuntimeError("Postgres indisponível")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT reference_year
            FROM observations
            WHERE indicator_id = %s
            ORDER BY reference_year
            """,
            (indicator_id,),
        )
        return [int(r[0]) for r in cur.fetchall()]


def observations(
    *,
    indicator_id: str,
    year: int | None = None,
    level: str | None = None,
    uf: str | None = None,
    territory_id: str | None = None,
    limit: int = 20000,
) -> list[dict[str, Any]]:
    conn = get_conn()
    if not conn:
        raise RuntimeError("Postgres indisponível")
    clauses = ["o.indicator_id = %s"]
    params: list[Any] = [indicator_id]
    if year is not None:
        clauses.append("o.reference_year = %s")
        params.append(year)
    if territory_id:
        clauses.append("o.territory_id = %s")
        params.append(territory_id)
    if level == "STATE":
        clauses.append("left(o.territory_id, 3) = 'uf_'")
    elif level == "MUNICIPALITY":
        clauses.append("left(o.territory_id, 4) = 'mun_'")
        if uf:
            clauses.append("t.state_code = %s")
            params.append(uf.upper())
    where = " AND ".join(clauses)
    join = "LEFT JOIN territories t ON t.territory_id = o.territory_id" if uf and level == "MUNICIPALITY" else ""
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT o.observation_id, o.indicator_id, o.territory_id,
                   o.reference_year, o.value, o.unit, o.source_id, o.geographic_level
            FROM observations o
            {join}
            WHERE {where}
            ORDER BY o.territory_id, o.reference_year
            LIMIT %s
            """,
            params,
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def series(territory_id: str, indicator_id: str) -> list[dict[str, Any]]:
    return observations(
        indicator_id=indicator_id,
        territory_id=territory_id,
        limit=500,
    )


def choropleth(year: int, indicator_id: str) -> dict[str, float]:
    rows = observations(
        indicator_id=indicator_id,
        year=year,
        level="STATE",
        limit=100,
    )
    out: dict[str, float] = {}
    for o in rows:
        tid = o["territory_id"] or ""
        if tid.startswith("uf_") and len(tid) == 5 and o["value"] is not None:
            out[tid[3:]] = float(o["value"])
    return out


def list_documentos(
    *,
    nivel: str | None = None,
    orgao: str | None = None,
    limit: int = 50000,
) -> list[dict[str, Any]] | None:
    """Retorna docs do PG ou None se flag off / tabela vazia (caller usa KB)."""
    if not _fontes_from_pg_enabled():
        return None
    conn = get_conn()
    if not conn:
        return None
    try:
        clauses: list[str] = []
        params: list[Any] = []
        if nivel:
            clauses.append("nivel_fonte = %s")
            params.append(nivel)
        if orgao:
            clauses.append("LOWER(orgao) = LOWER(%s)")
            params.append(orgao)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documentos")
            if (cur.fetchone() or [0])[0] == 0:
                return None
            cur.execute(
                f"""
                SELECT id, tipo, titulo, data, nivel_fonte, orgao, url,
                       url_pendente, casos, nota, fonte, source_system
                FROM documentos
                {where}
                ORDER BY titulo
                LIMIT %s
                """,
                params,
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception:
        return None
