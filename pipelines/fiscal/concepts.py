"""
Conceitos fiscais que NÃO podem ser tratados como equivalentes.

Regra AGENT_B: nunca reduzir a «impostos − gastos = déficit».
Preferir valores oficiais de resultado quando existirem.
"""

from __future__ import annotations

NON_EQUIVALENT = {
    "receita": [
        "arrecadacao_tributaria_rf",
        "receita_orcamentaria",
        "receita_primaria_rtn",
        "receita_bruta_dca",
        "rcl_rgf",
    ],
    "despesa": [
        "despesa_autorizada",
        "despesa_empenhada",
        "despesa_liquidada",
        "despesa_paga",
        "despesa_primaria_rtn",
    ],
    "resultado": [
        "resultado_primario_acima_da_linha",
        "resultado_primario_abaixo_da_linha",
        "resultado_nominal",
    ],
    "divida": [
        "dpf_estoque",
        "dbgg",
        "dlsp",
        "divida_consolidada_ente",
    ],
}

SERIES_RTN = {
    "receita_total": {
        "codigo_serie": "10.01.1",
        "nome": "Receita Total",
        "maps_to": "primary_revenue",
        "note": "RTN tema 10 — fluxo acima da linha; ≠ arrecadação RFB.",
    },
    "despesa_total": {
        "codigo_serie": "10.03.1",
        "nome": "Despesa total",
        "maps_to": "primary_expense",
        "note": "RTN tema 10 — ≠ despesa empenhada SIAFI/SICONFI.",
    },
    "resultado_primario_gc": {
        "codigo_serie": "10.04.1",
        "nome": "Resultado Primário - Governo Central",
        "maps_to": "primary_result",
        "methodology": "RTN_ABOVE_THE_LINE",
    },
    "resultado_primario_abaixo_linha": {
        "codigo_serie": "10.07.1",
        "nome": "Resultado Primário do Governo Central - Abaixo da Linha",
        "maps_to": "primary_result",
        "methodology": "RTN_BELOW_THE_LINE",
    },
    "juros_nominais": {
        "codigo_serie": "10.08.1",
        "nome": "Juros Nominais",
        "maps_to": "interest",
        "note": "Componente do resultado nominal; ≠ custo médio da DPF (RMD).",
    },
    "resultado_nominal_gc": {
        "codigo_serie": "10.09.1",
        "nome": "Resultado Nominal do Governo Central",
        "maps_to": "nominal_result",
        "methodology": "RTN_NOMINAL",
    },
}

DATASET_URLS = {
    "rtn_ckan": "https://www.tesourotransparente.gov.br/ckan/dataset/resultado-do-tesouro-nacional",
    "rtn_api": "https://apiapex.tesouro.gov.br/aria/v1/series-temporais/docs",
    "dpf_estoque": "https://www.tesourotransparente.gov.br/ckan/dataset/estoque-da-divida-publica-federal",
    "dpf_emissoes": "https://www.tesourotransparente.gov.br/ckan/dataset/emissoes-e-resgates-divida-publica-federal",
    "dpf_execucao_nd": (
        "https://www.tesourotransparente.gov.br/ckan/dataset/"
        "execucao-orcamentaria-e-financeira-da-divida-publica-federal-por-nd"
    ),
    "siconfi_api": (
        "https://www.tesourotransparente.gov.br/consultas/consultas-siconfi/"
        "siconfi-api-de-dados-abertos"
    ),
}


def concept_note(a: str, b: str) -> str:
    return (
        f"«{a}» e «{b}» não são equivalentes contábeis. "
        "Não misturar em um único indicador sem metodologia explícita."
    )
