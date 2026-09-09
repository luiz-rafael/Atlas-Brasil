"""Serving magistrados — remuneração CNJ (transparência). Remuneração ≠ culpa."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db import get_conn

DISCLAIMER = (
    "O Atlas não acusa. O Atlas documenta. "
    "Remuneração pública de magistrado ≠ culpa, corrupção ou irregularidade. "
    "gross_total ≠ subsídio; null ≠ zero."
)

ROOT = Path(__file__).resolve().parents[2]
GOLD_MAG = ROOT / "data" / "lake" / "gold" / "cnj_compensation" / "latest" / "magistrates.jsonl"
GOLD_COMP = (
    ROOT
    / "data"
    / "lake"
    / "gold"
    / "cnj_compensation"
    / "latest"
    / "compensation_current.jsonl"
)
if not GOLD_COMP.is_file():
    GOLD_COMP = (
        ROOT
        / "data"
        / "lake"
        / "gold"
        / "cnj_compensation"
        / "latest"
        / "compensations.jsonl"
    )


def _from_jsonl(path: Path, limit: int = 500) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
        if len(rows) >= limit:
            break
    return rows


def list_magistrados(
    *,
    q: str | None = None,
    court_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    conn = get_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM magistrates")
                total = cur.fetchone()[0]
                if total:
                    limit = max(1, min(int(limit), 500))
                    offset = max(0, int(offset))
                    clauses = []
                    params: list[Any] = []
                    if q:
                        clauses.append(
                            "(display_name ILIKE %s OR normalized_name ILIKE %s)"
                        )
                        params.extend([f"%{q}%", f"%{q}%"])
                    if court_id:
                        clauses.append("court_id = %s")
                        params.append(court_id)
                    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                    cur.execute(
                        f"""
                        SELECT magistrate_id, display_name, normalized_name, court_id,
                               position, resolution_confidence
                        FROM magistrates
                        {where}
                        ORDER BY display_name NULLS LAST, normalized_name
                        LIMIT %s OFFSET %s
                        """,
                        (*params, limit, offset),
                    )
                    cols = [d[0] for d in cur.description]
                    items = [dict(zip(cols, r)) for r in cur.fetchall()]
                    return {
                        "ok": True,
                        "total": total if not clauses else len(items),
                        "items": items,
                        "source": "postgres",
                        "disclaimer": DISCLAIMER,
                    }
        except Exception:
            pass

    rows = _from_jsonl(GOLD_MAG, limit=5000)
    qn = (q or "").strip().lower()
    if qn:
        rows = [
            r
            for r in rows
            if qn in (r.get("display_name") or "").lower()
            or qn in (r.get("normalized_name") or "").lower()
        ]
    if court_id:
        rows = [r for r in rows if r.get("court_id") == court_id]
    total = len(rows)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    return {
        "ok": True,
        "total": total,
        "items": rows[offset : offset + limit],
        "source": "gold_jsonl",
        "disclaimer": DISCLAIMER,
    }


def get_magistrado(magistrate_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT magistrate_id, display_name, normalized_name, court_id,
                           position, source_id, resolution_confidence
                    FROM magistrates WHERE magistrate_id = %s
                    """,
                    (magistrate_id,),
                )
                row = cur.fetchone()
                if row:
                    cols = [d[0] for d in cur.description]
                    mag = dict(zip(cols, row))
                    cur.execute(
                        """
                        SELECT id, reference_year, reference_month, reference_period,
                               base_subsidy, gross_total, net_total, discounts,
                               personal_advantages, eventual_advantages, indemnities
                        FROM magistrate_compensation
                        WHERE magistrate_id = %s
                        ORDER BY reference_year DESC NULLS LAST, reference_month DESC NULLS LAST
                        LIMIT 24
                        """,
                        (magistrate_id,),
                    )
                    ccols = [d[0] for d in cur.description]
                    comps = [dict(zip(ccols, r)) for r in cur.fetchall()]
                    for c in comps:
                        for k, v in list(c.items()):
                            if hasattr(v, "as_tuple"):  # Decimal
                                c[k] = float(v) if v is not None else None
                    return {
                        "ok": True,
                        "magistrado": mag,
                        "compensations": comps,
                        "source": "postgres",
                        "disclaimer": DISCLAIMER,
                    }
        except Exception:
            pass

    for r in _from_jsonl(GOLD_MAG, limit=20000):
        if r.get("magistrate_id") == magistrate_id:
            comps = [
                c
                for c in _from_jsonl(GOLD_COMP, limit=50000)
                if c.get("magistrate_id") == magistrate_id
            ][:24]
            return {
                "ok": True,
                "magistrado": r,
                "compensations": comps,
                "source": "gold_jsonl",
                "disclaimer": DISCLAIMER,
            }
    return None


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stats_magistrados(
    *,
    court_id: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Agregados de remuneração (macro) — não é orçamento total do Judiciário."""
    conn = get_conn()
    if not conn:
        return {
            "ok": False,
            "error": "postgres_unavailable",
            "disclaimer": DISCLAIMER,
            "coverage_note": (
                "Cobertura atual do gold/serving: tribunais carregados no Postgres "
                "(hoje tipicamente TRT7 + TJES). Remuneração ≠ orçamento da Justiça."
            ),
        }

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT court_id, COUNT(*) AS n
                FROM magistrates
                GROUP BY court_id
                ORDER BY n DESC
                """
            )
            courts = [
                {"court_id": r[0], "magistrates": int(r[1])} for r in cur.fetchall()
            ]

            clauses = ["gross_total IS NOT NULL"]
            params: list[Any] = []
            if court_id:
                clauses.append("court_id = %s")
                params.append(court_id)
            if year is not None:
                clauses.append("reference_year = %s")
                params.append(int(year))
            where = " AND ".join(clauses)

            cur.execute(
                f"""
                SELECT reference_year, reference_month,
                       COUNT(*) AS n_rows,
                       COUNT(DISTINCT magistrate_id) AS n_magistrates,
                       SUM(gross_total) AS sum_gross,
                       AVG(gross_total) AS avg_gross,
                       SUM(net_total) AS sum_net,
                       AVG(net_total) AS avg_net,
                       SUM(base_subsidy) AS sum_subsidy,
                       AVG(base_subsidy) AS avg_subsidy
                FROM magistrate_compensation
                WHERE {where}
                GROUP BY reference_year, reference_month
                ORDER BY reference_year, reference_month
                """,
                params,
            )
            timeline = []
            for r in cur.fetchall():
                y, m = r[0], r[1]
                timeline.append(
                    {
                        "year": y,
                        "month": m,
                        "period": f"{y}-{int(m):02d}" if y and m else str(y or ""),
                        "n_rows": int(r[2] or 0),
                        "n_magistrates": int(r[3] or 0),
                        "sum_gross": _num(r[4]),
                        "avg_gross": _num(r[5]),
                        "sum_net": _num(r[6]),
                        "avg_net": _num(r[7]),
                        "sum_subsidy": _num(r[8]),
                        "avg_subsidy": _num(r[9]),
                    }
                )

            cur.execute(
                f"""
                SELECT court_id,
                       COUNT(*) AS n_rows,
                       COUNT(DISTINCT magistrate_id) AS n_magistrates,
                       SUM(gross_total) AS sum_gross,
                       AVG(gross_total) AS avg_gross,
                       SUM(net_total) AS sum_net,
                       AVG(base_subsidy) AS avg_subsidy
                FROM magistrate_compensation
                WHERE {where}
                GROUP BY court_id
                ORDER BY SUM(gross_total) DESC NULLS LAST
                """,
                params,
            )
            by_court = []
            for r in cur.fetchall():
                by_court.append(
                    {
                        "court_id": r[0],
                        "n_rows": int(r[1] or 0),
                        "n_magistrates": int(r[2] or 0),
                        "sum_gross": _num(r[3]),
                        "avg_gross": _num(r[4]),
                        "sum_net": _num(r[5]),
                        "avg_subsidy": _num(r[6]),
                    }
                )

            # Último período com dados (macro snapshot)
            latest = timeline[-1] if timeline else None
            years = sorted({t["year"] for t in timeline if t.get("year")})

            # Top remuneração no último ano disponível (amostra editorial)
            top_year = year or (years[-1] if years else None)
            top: list[dict[str, Any]] = []
            if top_year:
                top_params: list[Any] = [top_year]
                top_court = ""
                if court_id:
                    top_court = "AND c.court_id = %s"
                    top_params.append(court_id)
                cur.execute(
                    f"""
                    SELECT c.magistrate_id, m.display_name, c.court_id,
                           AVG(c.gross_total) AS avg_gross,
                           AVG(c.net_total) AS avg_net,
                           AVG(c.base_subsidy) AS avg_subsidy,
                           COUNT(*) AS n_months
                    FROM magistrate_compensation c
                    JOIN magistrates m ON m.magistrate_id = c.magistrate_id
                    WHERE c.reference_year = %s
                      AND c.gross_total IS NOT NULL
                      {top_court}
                    GROUP BY c.magistrate_id, m.display_name, c.court_id
                    ORDER BY AVG(c.gross_total) DESC NULLS LAST
                    LIMIT 15
                    """,
                    top_params,
                )
                for r in cur.fetchall():
                    top.append(
                        {
                            "magistrate_id": r[0],
                            "display_name": r[1],
                            "court_id": r[2],
                            "avg_gross": _num(r[3]),
                            "avg_net": _num(r[4]),
                            "avg_subsidy": _num(r[5]),
                            "n_months": int(r[6] or 0),
                        }
                    )

            return {
                "ok": True,
                "source": "postgres",
                "disclaimer": DISCLAIMER,
                "coverage_note": (
                    "Série = soma das remunerações publicadas (CNJ/tribunais) "
                    "nas competências carregadas. Não é o orçamento total do "
                    "Judiciário nem custo por processo. Cobertura parcial por tribunal."
                ),
                "courts": courts,
                "years": years,
                "filter": {"court_id": court_id, "year": year},
                "latest_period": latest,
                "timeline": timeline,
                "by_court": by_court,
                "top_avg_gross": top,
                "top_year": top_year,
            }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "disclaimer": DISCLAIMER,
        }
