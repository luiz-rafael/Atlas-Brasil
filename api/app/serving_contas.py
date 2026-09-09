"""Serving Contas do Brasil — consultas fiscais canônicas no Postgres.

O Atlas não acusa. O Atlas documenta.
Renúncia ≠ pagamento. Resultado fiscal ≠ arrecadação RFB − despesa inventada.
"""

from __future__ import annotations

from typing import Any

from app.db import get_conn

DISCLAIMER = (
    "O Atlas não acusa. O Atlas documenta. "
    "Indicadores fiscais durante um período/administração ≠ causalidade atribuída a pessoa. "
    "Renúncia fiscal não é pagamento. "
    "Não misturar DPF/DBGG/DLSP nem primário/nominal."
)

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(int(limit), MAX_LIMIT))


def _meta_envelope(
    *,
    value: Any,
    unit: str,
    period: str | None,
    source: str,
    methodology: str | None = None,
    coverage_status: str = "PARTIAL",
    retrieved_at: str | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    out = {
        "value": value,
        "unit": unit,
        "period": period,
        "source": source,
        "methodology": methodology,
        "coverage_status": coverage_status,
        "retrieved_at": retrieved_at,
        "disclaimer": DISCLAIMER,
    }
    if extra:
        out.update(extra)
    return out


def ping() -> bool:
    conn = get_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM fiscal_result_observation LIMIT 1")
            cur.fetchone()
        return True
    except Exception:
        return False


def resumo(year: int) -> dict[str, Any]:
    """Agregado anual canônico — não inventa déficit = RFB − despesa."""
    conn = get_conn()
    if not conn:
        return {"ok": False, "error": "postgres_unavailable", "disclaimer": DISCLAIMER}

    y = str(year)
    out: dict[str, Any] = {
        "year": year,
        "territory_id": "terr_br",
        "disclaimer": DISCLAIMER,
        "quanto_entrou": None,
        "quanto_saiu": None,
        "resultado_fiscal": None,
        "divida": None,
        "renuncia_fiscal": None,
        "pessoal": None,
        "carga_tributaria_pib": None,
    }

    with conn.cursor() as cur:
        # Receita RTN (soma mensal no ano) — millions
        cur.execute(
            """
            SELECT SUM(revenue_realized), MAX(retrieved_at)::text, MAX(methodology)
            FROM public_budget_execution
            WHERE territory_id = 'terr_br'
              AND dataset_id LIKE 'tesouro.revenue%%'
              AND reference_year = %s
              AND revenue_realized IS NOT NULL
            """,
            (year,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            out["quanto_entrou"] = _meta_envelope(
                value=float(row[0]),
                unit="BRL_millions",
                period=y,
                source="tesouro",
                methodology=row[2] or "RTN_RECEITA",
                retrieved_at=row[1],
                extra={"metric": "revenue_realized", "aggregation": "sum_months"},
            )

        cur.execute(
            """
            SELECT SUM(expense_paid), MAX(retrieved_at)::text, MAX(methodology)
            FROM public_budget_execution
            WHERE territory_id = 'terr_br'
              AND dataset_id LIKE 'tesouro.expenditure%%'
              AND reference_year = %s
              AND expense_paid IS NOT NULL
            """,
            (year,),
        )
        row = cur.fetchone()
        # expense may be in expense_liquidated/paid fields — check also revenue file pattern
        if row and row[0] is not None:
            out["quanto_saiu"] = _meta_envelope(
                value=float(row[0]),
                unit="BRL_millions",
                period=y,
                source="tesouro",
                methodology=row[2] or "RTN_DESPESA",
                retrieved_at=row[1],
                extra={"metric": "expense_paid", "aggregation": "sum_months"},
            )
        else:
            cur.execute(
                """
                SELECT SUM(COALESCE(expense_liquidated, expense_committed, expense_authorized)),
                       MAX(retrieved_at)::text, MAX(methodology)
                FROM public_budget_execution
                WHERE territory_id = 'terr_br'
                  AND dataset_id LIKE 'tesouro.expenditure%%'
                  AND reference_year = %s
                """,
                (year,),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                out["quanto_saiu"] = _meta_envelope(
                    value=float(row[0]),
                    unit="BRL_millions",
                    period=y,
                    source="tesouro",
                    methodology=row[2] or "RTN_DESPESA",
                    retrieved_at=row[1],
                    extra={
                        "metric": "expense_fallback_liquidated_committed_authorized",
                        "aggregation": "sum_months",
                        "nota": "Estágios preservados nas séries detalhadas; aqui fallback para resumo.",
                    },
                )

        # Resultado fiscal — último mês do ano disponível (não somar resultados mensais cegamente)
        cur.execute(
            """
            SELECT reference_period, primary_result, nominal_result, interest,
                   primary_revenue, primary_expense, methodology, retrieved_at::text, amount_scale
            FROM fiscal_result_observation
            WHERE territory_id = 'terr_br'
              AND reference_period LIKE %s
            ORDER BY reference_period DESC
            LIMIT 1
            """,
            (f"{year}-%",),
        )
        row = cur.fetchone()
        if row:
            out["resultado_fiscal"] = {
                "period": row[0],
                "primary_result": _meta_envelope(
                    value=row[1],
                    unit=f"BRL_{row[8] or 'millions'}",
                    period=row[0],
                    source="tesouro",
                    methodology=row[6],
                    retrieved_at=row[7],
                    extra={"metric": "primary_result"},
                ),
                "nominal_result": _meta_envelope(
                    value=row[2],
                    unit=f"BRL_{row[8] or 'millions'}",
                    period=row[0],
                    source="tesouro",
                    methodology=row[6],
                    retrieved_at=row[7],
                    extra={"metric": "nominal_result"},
                ),
                "interest": _meta_envelope(
                    value=row[3],
                    unit=f"BRL_{row[8] or 'millions'}",
                    period=row[0],
                    source="tesouro",
                    methodology=row[6],
                    retrieved_at=row[7],
                    extra={"metric": "interest"},
                ),
                "primary_revenue": row[4],
                "primary_expense": row[5],
                "nota": "Usar resultado canônico RTN; não calcular arrecadação RFB − despesa.",
            }

        # Dívida — estoque DPF último do ano
        cur.execute(
            """
            SELECT reference_period, debt_indicator, debt_type, stock, methodology,
                   retrieved_at::text, amount_scale
            FROM public_debt_observation
            WHERE debt_indicator = 'DPF_STOCK'
              AND reference_period LIKE %s
            ORDER BY reference_period DESC
            LIMIT 5
            """,
            (f"{year}-%",),
        )
        debts = []
        for r in cur.fetchall():
            debts.append(
                _meta_envelope(
                    value=r[3],
                    unit=f"BRL_{r[6] or 'units'}",
                    period=r[0],
                    source="tesouro",
                    methodology=r[4],
                    retrieved_at=r[5],
                    extra={
                        "debt_indicator": r[1],
                        "debt_type": r[2],
                        "nota": "DPF ≠ DBGG ≠ DLSP",
                    },
                )
            )
        if debts:
            out["divida"] = {"items": debts, "coverage_status": "PARTIAL"}

        # Renúncia agregada anual
        cur.execute(
            """
            SELECT valor, value_type, methodology, retrieved_at::text, meta
            FROM tax_expenditure
            WHERE year = %s AND tributo = 'AGGREGATE'
            LIMIT 1
            """,
            (year,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            out["renuncia_fiscal"] = _meta_envelope(
                value=float(row[0]),
                unit="BRL",
                period=y,
                source="receita_renuncias",
                methodology=row[2],
                retrieved_at=row[3],
                extra={
                    "value_type": row[1],
                    "nota": "Renúncia fiscal ≠ pagamento público",
                    "metric": "tax_expenditure_annual_sum",
                },
            )

        # Pessoal SICONFI — soma BRASIL se existir, senão soma UFs do ano
        cur.execute(
            """
            SELECT SUM(gross_amount), MAX(retrieved_at)::text
            FROM personnel_expenditure
            WHERE reference_period = %s OR reference_period LIKE %s
            """,
            (y, f"{year}%"),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            out["pessoal"] = _meta_envelope(
                value=float(row[0]),
                unit="BRL",
                period=y,
                source="siconfi",
                methodology="SICONFI_PERSONNEL_GROSS",
                retrieved_at=row[1],
                extra={"metric": "gross_amount", "aggregation": "sum_territories"},
            )

        cur.execute(
            """
            SELECT tax_to_gdp_ratio, amount, methodology, retrieved_at::text
            FROM tax_burden_observation
            WHERE year = %s AND territory_id = 'terr_br'
            LIMIT 1
            """,
            (year,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            out["carga_tributaria_pib"] = _meta_envelope(
                value=float(row[0]),
                unit="ratio",
                period=y,
                source="receita_carga_tributaria",
                methodology=row[2],
                retrieved_at=row[3],
                extra={
                    "amount_brl": float(row[1]) if row[1] is not None else None,
                    "nota": "≠ ind_arrecadacao_federal",
                },
            )

    return out


def _budget_filters(
    *,
    year: int | None,
    month: int | None,
    territory_id: str | None,
    territory_type: str | None,
    government_level: str | None,
    source: str | None,
    dataset_like: str | None,
) -> tuple[str, list[Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if year is not None:
        clauses.append("reference_year = %s")
        params.append(year)
    if month is not None:
        clauses.append("reference_month = %s")
        params.append(month)
    if territory_id:
        clauses.append("territory_id = %s")
        params.append(territory_id)
    if government_level:
        clauses.append("government_level = %s")
        params.append(government_level)
    if source:
        clauses.append("source_id = %s")
        params.append(source)
    if dataset_like:
        clauses.append("dataset_id LIKE %s")
        params.append(dataset_like)
    return " AND ".join(clauses), params


def list_receitas(
    *,
    year: int | None = None,
    month: int | None = None,
    territory_id: str | None = None,
    government_level: str | None = None,
    source: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    conn = get_conn()
    if not conn:
        return {"items": [], "error": "postgres_unavailable", "disclaimer": DISCLAIMER}
    lim = _clamp_limit(limit)
    where, params = _budget_filters(
        year=year,
        month=month,
        territory_id=territory_id,
        territory_type=None,
        government_level=government_level,
        source=source,
        dataset_like="%revenue%",
    )
    # also include rows with revenue_realized even if dataset name differs
    where2 = f"({where}) AND revenue_realized IS NOT NULL"
    sql = f"""
        SELECT id, source_id, dataset_id, territory_id, government_level,
               reference_year, reference_month, reference_period,
               revenue_forecast, revenue_realized, currency, amount_scale,
               methodology, retrieved_at::text, notes
        FROM public_budget_execution
        WHERE {where2}
        ORDER BY reference_period DESC, territory_id
        LIMIT %s OFFSET %s
    """
    params2 = params + [lim, offset]
    with conn.cursor() as cur:
        cur.execute(sql, params2)
        cols = [d[0] for d in cur.description]
        items = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute(
            f"SELECT COUNT(*) FROM public_budget_execution WHERE {where2}",
            params,
        )
        total = cur.fetchone()[0]
    return {
        "items": items,
        "total": total,
        "limit": lim,
        "offset": offset,
        "disclaimer": DISCLAIMER,
    }


def list_despesas(
    *,
    year: int | None = None,
    month: int | None = None,
    territory_id: str | None = None,
    government_level: str | None = None,
    source: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    conn = get_conn()
    if not conn:
        return {"items": [], "error": "postgres_unavailable", "disclaimer": DISCLAIMER}
    lim = _clamp_limit(limit)
    where, params = _budget_filters(
        year=year,
        month=month,
        territory_id=territory_id,
        territory_type=None,
        government_level=government_level,
        source=source,
        dataset_like=None,
    )
    where2 = (
        f"({where}) AND ("
        "expense_authorized IS NOT NULL OR expense_committed IS NOT NULL OR "
        "expense_liquidated IS NOT NULL OR expense_paid IS NOT NULL)"
    )
    sql = f"""
        SELECT id, source_id, dataset_id, territory_id, government_level,
               reference_year, reference_month, reference_period,
               expense_authorized, expense_committed, expense_liquidated, expense_paid,
               restos_a_pagar, function_code, function_name, agency_code, agency_name,
               currency, amount_scale, methodology, retrieved_at::text, notes
        FROM public_budget_execution
        WHERE {where2}
        ORDER BY reference_period DESC, territory_id
        LIMIT %s OFFSET %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + [lim, offset])
        cols = [d[0] for d in cur.description]
        items = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM public_budget_execution WHERE {where2}", params)
        total = cur.fetchone()[0]
    return {
        "items": items,
        "total": total,
        "limit": lim,
        "offset": offset,
        "nota": (
            "expense_authorized, expense_committed, expense_liquidated e expense_paid "
            "são métricas distintas — nunca colapsar em um único 'gasto'."
        ),
        "disclaimer": DISCLAIMER,
    }


def list_resultado_fiscal(
    *,
    year: int | None = None,
    territory_id: str | None = "terr_br",
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    conn = get_conn()
    if not conn:
        return {"items": [], "error": "postgres_unavailable", "disclaimer": DISCLAIMER}
    lim = _clamp_limit(limit)
    clauses = ["1=1"]
    params: list[Any] = []
    if territory_id:
        clauses.append("territory_id = %s")
        params.append(territory_id)
    if year is not None:
        clauses.append("reference_period LIKE %s")
        params.append(f"{year}-%")
    where = " AND ".join(clauses)
    sql = f"""
        SELECT id, source_id, dataset_id, territory_id, reference_period,
               primary_revenue, primary_expense, primary_result, nominal_result, interest,
               methodology, currency, amount_scale, retrieved_at::text, notes
        FROM fiscal_result_observation
        WHERE {where}
        ORDER BY reference_period DESC
        LIMIT %s OFFSET %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + [lim, offset])
        cols = [d[0] for d in cur.description]
        items = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM fiscal_result_observation WHERE {where}", params)
        total = cur.fetchone()[0]
    return {
        "items": items,
        "total": total,
        "limit": lim,
        "offset": offset,
        "nota": "primary_result ≠ nominal_result; juros separados.",
        "disclaimer": DISCLAIMER,
    }


def list_divida(
    *,
    year: int | None = None,
    debt_indicator: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    conn = get_conn()
    if not conn:
        return {"items": [], "error": "postgres_unavailable", "disclaimer": DISCLAIMER}
    lim = _clamp_limit(limit)
    clauses = ["1=1"]
    params: list[Any] = []
    if year is not None:
        clauses.append("reference_period LIKE %s")
        params.append(f"{year}-%")
    if debt_indicator:
        clauses.append("debt_indicator = %s")
        params.append(debt_indicator)
    where = " AND ".join(clauses)
    sql = f"""
        SELECT id, source_id, dataset_id, reference_period, debt_indicator, debt_type,
               stock, issuance, redemption, amortization, interest,
               average_cost, average_maturity, indexer, currency, amount_scale,
               methodology, retrieved_at::text, notes
        FROM public_debt_observation
        WHERE {where}
        ORDER BY reference_period DESC
        LIMIT %s OFFSET %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + [lim, offset])
        cols = [d[0] for d in cur.description]
        items = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM public_debt_observation WHERE {where}", params)
        total = cur.fetchone()[0]
    return {
        "items": items,
        "total": total,
        "limit": lim,
        "offset": offset,
        "nota": "Não misturar DPF, DBGG e DLSP.",
        "disclaimer": DISCLAIMER,
    }


def list_renuncias(
    *,
    year: int | None = None,
    limit: int | None = None,
    offset: int = 0,
    view: str = "aggregate",
) -> dict[str, Any]:
    conn = get_conn()
    if not conn:
        return {"items": [], "error": "postgres_unavailable", "disclaimer": DISCLAIMER}
    lim = _clamp_limit(limit)
    view_norm = (view or "aggregate").strip().lower()
    clauses = ["1=1"]
    params: list[Any] = []
    if year is not None:
        clauses.append("year = %s")
        params.append(year)
    if view_norm in ("beneficiarios", "beneficiaries", "ben"):
        clauses.append("beneficio = %s")
        params.append("RENUNCIA_BENEFICIARIO")
        order = "valor DESC NULLS LAST, razao_social ASC NULLS LAST"
        nota = (
            "Beneficiários do extrato RFB (CNPJ raiz / razão social). "
            "Renúncia ≠ pagamento. Sem CNPJ 14 completo não há company_id canônico."
        )
    else:
        clauses.append("beneficio = %s")
        params.append("RENUNCIA_TOTAL_ANUAL")
        order = "year DESC"
        nota = "value_type OBSERVED|ESTIMATED|PROJECTED. Renúncia ≠ pagamento. Agregado anual Brasil."
    where = " AND ".join(clauses)
    sql = f"""
        SELECT tax_expenditure_id, year, tributo, beneficio, regime, setor,
               valor, value_type, methodology, territory_id, source_id, dataset_id,
               cnpj, cnpj_raiz, company_id, razao_social,
               retrieved_at::text, meta
        FROM tax_expenditure
        WHERE {where}
        ORDER BY {order}
        LIMIT %s OFFSET %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + [lim, offset])
        cols = [d[0] for d in cur.description]
        items = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM tax_expenditure WHERE {where}", params)
        total = cur.fetchone()[0]
    return {
        "items": items,
        "total": total,
        "limit": lim,
        "offset": offset,
        "view": "beneficiarios" if view_norm in ("beneficiarios", "beneficiaries", "ben") else "aggregate",
        "nota": nota,
        "disclaimer": DISCLAIMER,
    }


def list_pessoal(
    *,
    year: int | None = None,
    territory_id: str | None = None,
    government_level: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    conn = get_conn()
    if not conn:
        return {"items": [], "error": "postgres_unavailable", "disclaimer": DISCLAIMER}
    lim = _clamp_limit(limit)
    clauses = ["1=1"]
    params: list[Any] = []
    if territory_id:
        clauses.append("territory_id = %s")
        params.append(territory_id)
    if government_level:
        clauses.append("government_level = %s")
        params.append(government_level)
    if year is not None:
        clauses.append("(reference_period = %s OR reference_period LIKE %s)")
        params.extend([str(year), f"{year}%"])
    where = " AND ".join(clauses)
    sql = f"""
        SELECT id, territory_id, government_level, agency_id, reference_period,
               active_personnel, retired_personnel, pensions, gross_amount,
               source_id, dataset_id, currency, retrieved_at::text, notes
        FROM personnel_expenditure
        WHERE {where}
        ORDER BY reference_period DESC, territory_id
        LIMIT %s OFFSET %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + [lim, offset])
        cols = [d[0] for d in cur.description]
        items = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM personnel_expenditure WHERE {where}", params)
        total = cur.fetchone()[0]
    return {
        "items": items,
        "total": total,
        "limit": lim,
        "offset": offset,
        "disclaimer": DISCLAIMER,
    }


def list_cno(
    *,
    uf: str | None = None,
    cnpj: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Cadastro Nacional de Obras — vínculo COMPANY só com CNPJ 14."""
    conn = get_conn()
    if not conn:
        return {"items": [], "error": "postgres_unavailable", "disclaimer": DISCLAIMER}
    lim = _clamp_limit(limit)
    clauses = ["1=1"]
    params: list[Any] = []
    if uf:
        clauses.append("uf = %s")
        params.append(uf.upper()[:2])
    if cnpj:
        digits = "".join(ch for ch in cnpj if ch.isdigit())
        if len(digits) == 14:
            clauses.append("cnpj = %s")
            params.append(digits)
    where = " AND ".join(clauses)
    sql = f"""
        SELECT cno_work_id, cno_id, cnpj, company_id, municipality, uf,
               source_id, dataset_id, retrieved_at::text, meta
        FROM cno_works
        WHERE {where}
        ORDER BY uf NULLS LAST, municipality NULLS LAST, cno_id
        LIMIT %s OFFSET %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + [lim, offset])
        cols = [d[0] for d in cur.description]
        items = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM cno_works WHERE {where}", params)
        total = cur.fetchone()[0]
    return {
        "items": items,
        "total": total,
        "limit": lim,
        "offset": offset,
        "nota": "CNO = obra cadastrada; company_id apenas com CNPJ 14. Não implica irregularidade.",
        "disclaimer": DISCLAIMER,
    }


def territorio(territory_id: str, year: int | None = None) -> dict[str, Any]:
    """SICONFI / budget por território canônico Atlas."""
    conn = get_conn()
    if not conn:
        return {"error": "postgres_unavailable", "disclaimer": DISCLAIMER}
    lim = 50
    clauses = ["territory_id = %s"]
    params: list[Any] = [territory_id]
    if year is not None:
        clauses.append("reference_year = %s")
        params.append(year)
    where = " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, source_id, dataset_id, government_level, reference_period,
                   revenue_realized, expense_authorized, expense_committed,
                   expense_liquidated, expense_paid, methodology, retrieved_at::text
            FROM public_budget_execution
            WHERE {where}
            ORDER BY reference_period DESC
            LIMIT %s
            """,
            params + [lim],
        )
        cols = [d[0] for d in cur.description]
        budget = [dict(zip(cols, r)) for r in cur.fetchall()]

        p_clauses = ["territory_id = %s"]
        p_params: list[Any] = [territory_id]
        if year is not None:
            p_clauses.append("(reference_period = %s OR reference_period LIKE %s)")
            p_params.extend([str(year), f"{year}%"])
        cur.execute(
            f"""
            SELECT id, government_level, reference_period, gross_amount,
                   source_id, dataset_id, retrieved_at::text
            FROM personnel_expenditure
            WHERE {' AND '.join(p_clauses)}
            ORDER BY reference_period DESC
            LIMIT %s
            """,
            p_params + [lim],
        )
        cols = [d[0] for d in cur.description]
        pessoal = [dict(zip(cols, r)) for r in cur.fetchall()]

    return {
        "territory_id": territory_id,
        "year": year,
        "budget": budget,
        "pessoal": pessoal,
        "disclaimer": DISCLAIMER,
    }

def list_carga_tributaria() -> dict[str, Any]:
    """Série anual CTB (carga tributária bruta / PIB) — Brasil."""
    conn = get_conn()
    if not conn:
        return {
            "ok": False,
            "error": "postgres_unavailable",
            "items": [],
            "disclaimer": DISCLAIMER,
            "nota": (
                "Carga tributaria (% PIB) != arrecadacao federal nominal. "
                "Estudo CTB / RFB (Uniao + estados + municipios)."
            ),
        }
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT year, tax_to_gdp_ratio, amount, methodology, retrieved_at::text
            FROM tax_burden_observation
            WHERE territory_id = 'terr_br'
            ORDER BY year
            """
        )
        items = []
        for y, ratio, amount, meth, retrieved in cur.fetchall():
            items.append(
                {
                    "year": int(y) if y is not None else None,
                    "tax_to_gdp_ratio": float(ratio) if ratio is not None else None,
                    "pct_pib": (
                        round(float(ratio) * 100, 2) if ratio is not None else None
                    ),
                    "amount_brl": float(amount) if amount is not None else None,
                    "methodology": meth,
                    "retrieved_at": retrieved,
                }
            )
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "source": "postgres",
        "disclaimer": DISCLAIMER,
        "nota": (
            "Serie CTB RFB: arrecadacao tributaria bruta / PIB. "
            "Nao e o imposto pessoal do holerite; cobre Uniao, estados e municipios. "
            "Quebras metodologicas (ex.: FGTS / Sistema S) podem afetar comparacao entre anos."
        ),
    }

