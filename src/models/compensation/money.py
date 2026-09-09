"""Parse de valores monetários. Ausência nunca vira zero."""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

_BLANK = {
    "",
    "-",
    "--",
    "—",
    "n/a",
    "na",
    "null",
    "none",
    "nil",
    ".",
    "*",
    "x",
    "s/i",
    "si",
    "nd",
    "n.d.",
    "n.d",
    "nao informado",
    "não informado",
    "nao se aplica",
    "não se aplica",
}

_CURRENCY_PREFIX = re.compile(r"^\s*(r\$|brl)\s*", re.IGNORECASE)
_SPACES = re.compile(r"\s+")


def is_missing_amount(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    if isinstance(value, Decimal) and value.is_nan():
        return True
    text = str(value).strip().lower()
    return text in _BLANK


def parse_amount(value: Any) -> Decimal | None:
    """
    Converte valor da fonte em Decimal.

    Retorna None quando o campo está ausente/ilegível.
    Zero só é retornado se a fonte explicitamente informar 0.
    """
    if is_missing_amount(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return Decimal(str(value))

    text = _CURRENCY_PREFIX.sub("", str(value).strip())
    text = _SPACES.sub("", text)
    text = text.replace("\xa0", "")
    if not text or text.lower() in _BLANK:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if text.endswith("-"):
        negative = True
        text = text[:-1]
    text = text.replace("+", "")

    if not text:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")

    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if negative:
        amount = -amount
    return amount


def decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
