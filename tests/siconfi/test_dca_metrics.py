"""Testes SICONFI — helpers de métricas DCA."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.ingest.siconfi_dca import extract_dca_metrics, pick_valor


def test_pick_valor_and_extract():
    items = [
        {
            "anexo": "Anexo I-C - Receitas",
            "coluna": "Receitas Brutas Realizadas",
            "cod_conta": "ReceitasExcetoIntraOrcamentarias",
            "conta": "Receitas (Exceto Intraorçamentárias)",
            "valor": 1000.0,
        },
        {
            "anexo": "Anexo I-D - Despesas",
            "coluna": "Despesas Empenhadas",
            "cod_conta": "TotalDespesas",
            "conta": "Total Geral da Despesa",
            "valor": 800.0,
        },
        {
            "anexo": "Anexo I-D - Despesas",
            "coluna": "Despesas Liquidadas",
            "cod_conta": "TotalDespesas",
            "conta": "Total Geral da Despesa",
            "valor": 750.0,
        },
        {
            "anexo": "Anexo I-D - Despesas",
            "coluna": "Despesas Pagas",
            "cod_conta": "TotalDespesas",
            "conta": "Total Geral da Despesa",
            "valor": 700.0,
        },
        {
            "anexo": "Anexo I-D - Despesas",
            "coluna": "Despesas Empenhadas",
            "cod_conta": "DO3.1.00.00.00.00",
            "conta": "Pessoal",
            "valor": 400.0,
        },
    ]
    assert pick_valor(
        items,
        anexo_contains="Anexo I-C",
        coluna="Receitas Brutas Realizadas",
        cod_conta="ReceitasExcetoIntraOrcamentarias",
    ) == 1000.0
    m = extract_dca_metrics(items)
    assert m["receita_bruta"] == 1000.0
    assert m["despesa_total"] == 800.0
    assert m["despesa_liquidada"] == 750.0
    assert m["despesa_paga"] == 700.0
    assert m["despesa_pessoal"] == 400.0


if __name__ == "__main__":
    test_pick_valor_and_extract()
    print("OK tests/siconfi/test_dca_metrics.py")
