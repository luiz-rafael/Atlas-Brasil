"""Cliente compartilhado — API Séries Temporais RTN (Tesouro)."""

from __future__ import annotations

from typing import Any

import httpx

from pipelines.common import throttle
from pipelines.fiscal.concepts import SERIES_RTN

RTN_BASE = "https://apiapex.tesouro.gov.br/aria/v1/series-temporais/custom"
UA = "ATLAS-BRASIL-Ingestor/5.2 (+pesquisa documental oficial Tesouro RTN)"

# códigos usados na camada fiscal
WANTED_CODES = {v["codigo_serie"] for v in SERIES_RTN.values()}
CODE_TO_FIELD = {
    SERIES_RTN["receita_total"]["codigo_serie"]: "primary_revenue",
    SERIES_RTN["despesa_total"]["codigo_serie"]: "primary_expense",
    SERIES_RTN["resultado_primario_gc"]["codigo_serie"]: "primary_result_above",
    SERIES_RTN["resultado_primario_abaixo_linha"]["codigo_serie"]: "primary_result_below",
    SERIES_RTN["juros_nominais"]["codigo_serie"]: "interest",
    SERIES_RTN["resultado_nominal_gc"]["codigo_serie"]: "nominal_result",
}


def _fix_next(url: str | None) -> str | None:
    if not url:
        return None
    return url.replace("aria//", "aria/")


def fetch_resultado_fiscal(
    *,
    tema: str = "10",
    data_inicio: str | None = None,
    data_fim: str | None = None,
    codigo_da_serie: str | None = None,
    max_pages: int = 200,
) -> list[dict[str, Any]]:
    """Pagina GET /resultado-fiscal (valores mensais em R$ milhões)."""
    params: dict[str, str] = {"tema": tema, "pageSize": "1000"}
    if data_inicio:
        params["data_inicio"] = data_inicio
    if data_fim:
        params["data_fim"] = data_fim
    if codigo_da_serie:
        params["codigo_da_serie"] = codigo_da_serie

    out: list[dict[str, Any]] = []
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url: str | None = f"{RTN_BASE}/resultado-fiscal?{qs}"
    pages = 0
    with httpx.Client(headers={"User-Agent": UA, "Accept": "application/json"}, timeout=120.0) as client:
        while url and pages < max_pages:
            throttle()
            r = client.get(url, follow_redirects=True)
            r.raise_for_status()
            data = r.json()
            out.extend(data.get("registros") or [])
            url = _fix_next(data.get("next"))
            pages += 1
    return out


def fetch_wanted_series(
    *,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> list[dict[str, Any]]:
    """Busca só as séries RTN mapeadas (mais rápido que o tema inteiro)."""
    out: list[dict[str, Any]] = []
    for code in sorted(WANTED_CODES):
        out.extend(
            fetch_resultado_fiscal(
                tema="10",
                data_inicio=data_inicio,
                data_fim=data_fim,
                codigo_da_serie=code,
                max_pages=50,
            )
        )
    return out


def parse_period(iso_or_date: str) -> tuple[int, int, str]:
    """Retorna (year, month, YYYY-MM) a partir de data ISO da API."""
    # 2024-03-01T00:00:00.000Z
    y = int(iso_or_date[0:4])
    m = int(iso_or_date[5:7])
    return y, m, f"{y:04d}-{m:02d}"


def pivot_wanted_series(registros: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """
    Agrupa por período → campos canônicos.
    primary_result_above / below ficam separados; o caller escolhe methodology.
    """
    by_period: dict[str, dict[str, float]] = {}
    for reg in registros:
        code = str(reg.get("codigoSerie") or "")
        if code not in WANTED_CODES:
            continue
        data = reg.get("data")
        if not data:
            continue
        _, _, period = parse_period(str(data))
        field = CODE_TO_FIELD.get(code)
        if not field:
            continue
        try:
            val = float(reg.get("valor"))
        except (TypeError, ValueError):
            continue
        bucket = by_period.setdefault(period, {})
        bucket[field] = val
    return by_period
