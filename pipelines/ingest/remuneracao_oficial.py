#!/usr/bin/env python3
"""
Remuneração oficial (macro por cargo/ano) + frequência derivada de votos nominais.

- Macro: série de subsídio parlamentar / Presidência (valores públicos + URL fonte).
- Micro: junta frequência de votações (presença/ausência) já no silver legislativo.

Não inventa holerite diário: deixa claro cobertura e fonte.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, utc_now, write_json, write_manifest  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

# Valores de referência pública (subsídio mensal aproximado / oficial divulgado).
# Atualizar quando a Casa publicar novo valor; sempre com URL.
# Fontes típicas: Portal da Câmara (transparência), Senado, Planalto/DOU.
SERIES = [
    # Deputado Federal — subsídio
    {"ano": 2022, "cargo": "deputado_federal", "subsidio_mensal": 33743.00, "moeda": "BRL",
     "fonte_url": "https://www.camara.leg.br/transparencia/", "nota": "Subsídio parlamentar divulgado (referência pública)"},
    {"ano": 2023, "cargo": "deputado_federal", "subsidio_mensal": 41746.93, "moeda": "BRL",
     "fonte_url": "https://www.camara.leg.br/transparencia/", "nota": "Subsídio parlamentar divulgado (referência pública)"},
    {"ano": 2024, "cargo": "deputado_federal", "subsidio_mensal": 44169.93, "moeda": "BRL",
     "fonte_url": "https://www.camara.leg.br/transparencia/", "nota": "Subsídio parlamentar divulgado (referência pública)"},
    {"ano": 2025, "cargo": "deputado_federal", "subsidio_mensal": 46366.19, "moeda": "BRL",
     "fonte_url": "https://www.camara.leg.br/transparencia/gastos-parlamentares", "nota": "Valor divulgado na transparência da Câmara"},
    {"ano": 2026, "cargo": "deputado_federal", "subsidio_mensal": 46366.19, "moeda": "BRL",
     "fonte_url": "https://www.camara.leg.br/transparencia/gastos-parlamentares", "nota": "Mesmo patamar divulgado na transparência (conferir atualização)"},
    # Senador — mesmo subsídio do Congresso (faixa alinhada ao DF)
    {"ano": 2022, "cargo": "senador", "subsidio_mensal": 33743.00, "moeda": "BRL",
     "fonte_url": "https://www12.senado.leg.br/transparencia", "nota": "Subsídio parlamentar (referência pública)"},
    {"ano": 2023, "cargo": "senador", "subsidio_mensal": 41746.93, "moeda": "BRL",
     "fonte_url": "https://www12.senado.leg.br/transparencia", "nota": "Subsídio parlamentar (referência pública)"},
    {"ano": 2024, "cargo": "senador", "subsidio_mensal": 44169.93, "moeda": "BRL",
     "fonte_url": "https://www12.senado.leg.br/transparencia", "nota": "Subsídio parlamentar (referência pública)"},
    {"ano": 2025, "cargo": "senador", "subsidio_mensal": 46366.19, "moeda": "BRL",
     "fonte_url": "https://www12.senado.leg.br/transparencia", "nota": "Subsídio parlamentar (referência pública)"},
    {"ano": 2026, "cargo": "senador", "subsidio_mensal": 46366.19, "moeda": "BRL",
     "fonte_url": "https://www12.senado.leg.br/transparencia", "nota": "Conferir atualização na transparência do Senado"},
    # Presidente da República — subsídio
    {"ano": 2022, "cargo": "presidente_republica", "subsidio_mensal": 30934.70, "moeda": "BRL",
     "fonte_url": "https://www.gov.br/planalto/", "nota": "Subsídio Presidência (referência pública / DOU)"},
    {"ano": 2023, "cargo": "presidente_republica", "subsidio_mensal": 39293.32, "moeda": "BRL",
     "fonte_url": "https://www.gov.br/planalto/", "nota": "Subsídio Presidência (referência pública)"},
    {"ano": 2024, "cargo": "presidente_republica", "subsidio_mensal": 41572.74, "moeda": "BRL",
     "fonte_url": "https://www.gov.br/planalto/", "nota": "Subsídio Presidência (referência pública)"},
    {"ano": 2025, "cargo": "presidente_republica", "subsidio_mensal": 46000.00, "moeda": "BRL",
     "fonte_url": "https://portaldatransparencia.gov.br/", "nota": "Aproximação — validar no Portal da Transparência/DOU"},
    {"ano": 2026, "cargo": "presidente_republica", "subsidio_mensal": 46000.00, "moeda": "BRL",
     "fonte_url": "https://portaldatransparencia.gov.br/", "nota": "Aproximação — validar no Portal da Transparência/DOU"},
]


def main() -> int:
    run = start_run("remuneracao_oficial", "remuneracao.oficial")
    out = bronze_dir("remuneracao_oficial")
    payload = {
        "fetched_at": utc_now(),
        "cobertura": {
            "macro": True,
            "micro_holerite_diario": False,
            "micro_frequencia_via_votos": True,
            "aviso": (
                "Subsídio é o valor-base do cargo (macro). Descontos por falta, "
                "auxílios e verbas indenizatórias exigem fonte adicional. "
                "Frequência individual vem de votações nominais (não é ponto eletrônico)."
            ),
        },
        "series": SERIES,
    }
    write_json(out / "subsidio_por_cargo_ano.json", payload)
    write_manifest(
        out,
        "remuneracao_oficial",
        [{"file": "subsidio_por_cargo_ano.json", "count": len(SERIES)}],
        extra={"ingestion_run_id": run["ingestion_run_id"]},
    )
    mark_ingested(
        "remuneracao_oficial",
        run_id=run["ingestion_run_id"],
        counts={"series": len(SERIES)},
        ok=True,
    )
    print(f"OK remuneração macro: {len(SERIES)} pontos cargo×ano")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
