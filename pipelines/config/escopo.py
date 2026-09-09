#!/usr/bin/env python3
"""
Escopo político do Atlas.

INCLUSO: Presidente, Vice, Ministros de Estado, Deputados Federais, Senadores
         + Ministros do STF (elites do Judiciário federal)
         + Governadores (FASE 7 — mandatos TSE)
         + ex-ocupantes no período; suplentes só se exerceram.
FORA: dep. estaduais, prefeitos, vereadores (salvo flag futura),
      STJ/TCU nesta onda.
"""

from __future__ import annotations

import os
from datetime import datetime

ANO_INICIO = int(os.getenv("ATLAS_ANO_INICIO", "2010"))
ANO_FIM = int(os.getenv("ATLAS_ANO_FIM", str(datetime.now().year)))

# Legislaturas Câmara que cobrem ~2010–2026
# 53: 2007–2011 (parcial 2010–2011), 54–57: 2011–2027
CAMARA_LEGISLATURAS_DEFAULT = (53, 54, 55, 56, 57)

CARGOS_INCLUSOS = frozenset(
    {
        "presidente_republica",
        "vice_presidente",
        "ministro_estado",
        "ministro_stf",
        "deputado_federal",
        "senador",
        "governador",
        "vice_governador",
    }
)

CARGOS_EXCLUIDOS_MVP = frozenset(
    {
        "deputado_estadual",
        "deputado_distrital",
        "prefeito",
        "vice_prefeito",
        "vereador",
    }
)


def anos_periodo() -> list[int]:
    raw = os.getenv("ATLAS_ANOS", "").strip()
    if raw:
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]
    return list(range(ANO_INICIO, ANO_FIM + 1))


def anos_csv() -> str:
    return ",".join(str(a) for a in anos_periodo())


def camara_legislaturas() -> list[int]:
    raw = os.getenv("CAMARA_LEGISLATURAS", "").strip()
    if raw:
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]
    # filtra legs que intersectam o período
    # mapa aproximado id -> (ini, fim)
    spans = {
        53: (2007, 2011),
        54: (2011, 2015),
        55: (2015, 2019),
        56: (2019, 2023),
        57: (2023, 2027),
    }
    out = []
    for leg in CAMARA_LEGISLATURAS_DEFAULT:
        a, b = spans[leg]
        if b >= ANO_INICIO and a <= ANO_FIM:
            out.append(leg)
    return out
