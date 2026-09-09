"""Parser da planilha-padrão CNJ (Portaria 63/2017 / Resolução 215/2015)."""

from __future__ import annotations

import hashlib
from typing import Any

from src.models.compensation.money import decimal_to_float, parse_amount
from src.models.compensation.names import normalize_person_name, slug_header
from src.pipelines.cnj.compensation.parsers.detect import canonical_header
from src.pipelines.cnj.compensation.parsers.totals import is_total_row

CONTRACHEQUE_TOTALS = {
    "subsidio": "base_subsidy",
    "direitos_pessoais": "personal_advantages",
    "indenizacoes": "indemnities",
    "direitos_eventuais": "eventual_advantages",
    "pagamentos_retroativos": "retroactive_payments",
    "total_de_rendimentos": "gross_total",
    "total_de_descontos": "discounts",
    "rendimento_liquido": "net_total",
}

DISCOUNT_PARTS = {
    "descontos_previdencia_publica": "Previdência pública",
    "imposto_de_renda": "Imposto de renda",
    "descontos_diversos": "Descontos diversos",
    "retencao_por_teto_constitucional": "Retenção por teto constitucional",
}

SHEET_CATEGORY = {
    "contracheque": None,
    "personal_advantages": "personal_advantages",
    "indemnities": "indemnities",
    "eventual_advantages": "eventual_advantages",
    "cadastro": None,
}

SKIP_COMPONENT_KEYS = {
    "cpf",
    "nome",
    "cargo",
    "lotacao",
    "matricula",
    "mes",
    "ano",
    "competencia",
    "total",
    "total_de_rendimentos",
    "total_de_descontos",
    "rendimento_liquido",
    "subsidio",
    "col_0",
}


def _ident(row: dict) -> dict[str, Any]:
    cpf = row.get("cpf")
    matricula = row.get("matricula")
    nome = row.get("nome")
    ident = None
    if cpf not in (None, ""):
        ident = str(cpf).strip()
    elif matricula not in (None, ""):
        ident = f"mat:{str(matricula).strip()}"
    return {
        "display_name": str(nome).strip() if nome not in (None, "") else None,
        "normalized_name": normalize_person_name(str(nome) if nome else ""),
        "position": str(row["cargo"]).strip() if row.get("cargo") not in (None, "") else None,
        "lotacao": str(row["lotacao"]).strip() if row.get("lotacao") not in (None, "") else None,
        "source_person_identifier": ident,
        "cpf_raw": str(cpf).strip() if cpf not in (None, "") else None,
    }


def _row_key(ident: dict, court_id: str | None, year: int | None, month: int | None) -> str:
    basis = "|".join(
        [
            court_id or "",
            ident.get("source_person_identifier") or "",
            ident.get("normalized_name") or "",
            str(year or ""),
            str(month or ""),
        ]
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def parse_contracheque_row(
    row: dict[str, Any],
    *,
    court_id: str | None,
    year: int | None,
    month: int | None,
    raw_record_id: str | None,
    layout_id: str,
) -> dict[str, Any] | None:
    ident = _ident(row)
    if is_total_row({**row, **ident, "nome": ident.get("display_name")}):
        return None
    if not ident.get("normalized_name") and not ident.get("source_person_identifier"):
        return None

    totals: dict[str, float | None] = {}
    for src, dest in CONTRACHEQUE_TOTALS.items():
        totals[dest] = decimal_to_float(parse_amount(row.get(src)))
    # Anexo VIII: paradigma e coluna de subsídio/função podem coexistir
    if totals.get("base_subsidy") in (None, 0.0):
        alt = decimal_to_float(parse_amount(row.get("remuneracao_paradigma")))
        if alt is not None:
            totals["base_subsidy"] = alt
    elif row.get("remuneracao_paradigma") not in (None, ""):
        # mantém paradigma como componente se ambos existem
        pass

    components: list[dict[str, Any]] = []
    for src, label in DISCOUNT_PARTS.items():
        amount = decimal_to_float(parse_amount(row.get(src)))
        if amount is None:
            continue
        components.append(
            {
                "component_code": src,
                "component_name": label,
                "component_category": "discounts",
                "amount": amount,
                "source_column": src,
            }
        )
    for extra in ("diarias", "remuneracao_do_orgao_de_origem"):
        amount = decimal_to_float(parse_amount(row.get(extra)))
        if amount is None:
            continue
        category = "indemnities" if extra == "diarias" else "other_components"
        components.append(
            {
                "component_code": extra,
                "component_name": extra.replace("_", " "),
                "component_category": category,
                "amount": amount,
                "source_column": extra,
            }
        )

    year = year or _as_int(row.get("ano"))
    month = month or _as_month(row.get("mes") or row.get("competencia"))

    return {
        "row_key": _row_key(ident, court_id, year, month),
        "court_id": court_id,
        "reference_year": year,
        "reference_month": month,
        "layout_id": layout_id,
        "raw_record_id": raw_record_id,
        **ident,
        **totals,
        "components": components,
        "source_row": {k: _safe(v) for k, v in row.items() if not str(k).startswith("col_")},
    }


def parse_rubrica_row(
    row: dict[str, Any],
    *,
    category: str,
    court_id: str | None,
    year: int | None,
    month: int | None,
    raw_record_id: str | None,
    layout_id: str,
) -> dict[str, Any] | None:
    ident = _ident(row)
    if is_total_row({**row, "nome": ident.get("display_name")}):
        return None
    if not ident.get("normalized_name") and not ident.get("source_person_identifier"):
        return None
    components: list[dict[str, Any]] = []
    pending_name: str | None = None
    for key, value in row.items():
        canon = canonical_header(key)
        if canon in SKIP_COMPONENT_KEYS or canon.startswith("col_"):
            continue
        slug = slug_header(key)
        if slug.startswith("detalhe"):
            if pending_name and value not in (None, ""):
                pending_name = f"{pending_name} ({value})"
            continue
        if slug.startswith("outra") and not _is_numberish(value):
            pending_name = str(value).strip() if value not in (None, "") else None
            continue
        amount = parse_amount(value)
        if amount is None:
            continue
        name = pending_name or key
        pending_name = None
        comp_cat = category
        if "retroativ" in slug:
            comp_cat = "retroactive_payments"
        components.append(
            {
                "component_code": slug,
                "component_name": str(name).strip(),
                "component_category": comp_cat,
                "amount": decimal_to_float(amount),
                "source_column": key,
            }
        )
    year = year or _as_int(row.get("ano"))
    month = month or _as_month(row.get("mes") or row.get("competencia"))
    summed = _sum_category(components, category)
    retro = _sum_category(components, "retroactive_payments")
    payload = {
        "row_key": _row_key(ident, court_id, year, month),
        "court_id": court_id,
        "reference_year": year,
        "reference_month": month,
        "layout_id": layout_id,
        "raw_record_id": raw_record_id,
        **ident,
        "components": components,
    }
    if category == "personal_advantages":
        payload["personal_advantages"] = summed
    elif category == "indemnities":
        payload["indemnities"] = summed
    elif category == "eventual_advantages":
        payload["eventual_advantages"] = summed
    if retro is not None:
        payload["retroactive_payments"] = retro
    return payload


def _sum_category(components: list[dict], category: str) -> float | None:
    vals = [c["amount"] for c in components if c.get("component_category") == category and c.get("amount") is not None]
    if not vals:
        return None
    return float(sum(vals))


def _is_numberish(value: Any) -> bool:
    return parse_amount(value) is not None and not isinstance(value, bool)


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _as_month(value: Any) -> int | None:
    n = _as_int(value)
    if n is None:
        text = slug_header(str(value or ""))
        months = {
            "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
            "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
        }
        return months.get(text)
    if 1 <= n <= 12:
        return n
    if n > 200001:
        return n % 100
    return None


def _safe(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
