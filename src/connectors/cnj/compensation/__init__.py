"""Conector CNJ — remuneração de magistrados (não DataJud)."""

from src.connectors.cnj.compensation.courts import (
    CNJ_PORTAL_URL,
    CNJ_QLIK_PANEL_URL,
    CONNECTOR_VERSION,
    COURTS,
    DATASET_ID,
    SOURCE_ID,
    match_court,
)

__all__ = [
    "CNJ_PORTAL_URL",
    "CNJ_QLIK_PANEL_URL",
    "CONNECTOR_VERSION",
    "COURTS",
    "DATASET_ID",
    "SOURCE_ID",
    "match_court",
]
