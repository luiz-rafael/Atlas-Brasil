"""Extração de NPU CNJ (20 dígitos) a partir de texto/HTML.

Ignora processos administrativos (ex.: CEAF `08620.xxxxxx/AAAA-DD`) —
só aceita número CNJ válido no formato NNNNNNN-DD.AAAA.J.TR.OOOO.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from pipelines.legal.npu import digits_only, format_npu, parse_npu

# Formato oficial CNJ (separadores flexíveis: -, ., /, espaços)
_CNJ_FLEX = re.compile(
    r"(?<!\d)(\d{7})\s*[-–/]?\s*(\d{2})\s*[.\s/]\s*(\d{4})\s*[.\s/]\s*"
    r"(\d)\s*[.\s/]\s*(\d{2})\s*[.\s/]\s*(\d{4})(?!\d)"
)

# Sequência contínua de 20 dígitos (raro em prosa, mas aparece em JSON)
_CNJ_DIGITS20 = re.compile(r"(?<!\d)(\d{20})(?!\d)")

# Processo administrativo CGU/CEAF — NÃO é NPU CNJ
_ADMIN_PROC = re.compile(
    r"\b\d{5}\.\d{4,6}/\d{4}-\d{2}\b|\b08620\.\d+",
    flags=re.IGNORECASE,
)

_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_ENTITY = re.compile(r"&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);")
_WS = re.compile(r"\s+")

_YEAR_MIN = 1990


def strip_html(html: str) -> str:
    if not html:
        return ""
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = _HTML_TAG.sub(" ", t)
    t = _HTML_ENTITY.sub(" ", t)
    return _WS.sub(" ", t).strip()


def _year_max() -> int:
    return datetime.now(timezone.utc).year + 1


def is_valid_cnj_digits(digits: str) -> bool:
    """Valida NPU CNJ: 20 dígitos, ano plausível, segmento J 1–9."""
    d = digits_only(digits)
    if len(d) != 20:
        return False
    p = parse_npu(d)
    if not p:
        return False
    year = p["year"]
    if year < _YEAR_MIN or year > _year_max():
        return False
    if p["segment"] not in "123456789":
        return False
    # prefixo típico de processo admin CGU (08620…) não é CNJ estruturado
    # mas se passou no formato 20 dígitos com J válido, aceita só se formatar
    return format_npu(d) is not None


def extract_npus(text: str) -> list[str]:
    """
    Extrai NPUs CNJ formatados de texto (HTML já pode vir limpo ou bruto).
    Retorna lista deduplicada de strings no formato NNNNNNN-DD.AAAA.J.TR.OOOO.
    """
    if not text:
        return []
    # remove menções admin antes de caçar CNJ (evita falso-positivo parcial)
    cleaned = _ADMIN_PROC.sub(" ", text)
    if "<" in cleaned and ">" in cleaned:
        cleaned = strip_html(cleaned)

    found: list[str] = []
    seen: set[str] = set()

    def _add(digits: str) -> None:
        if not is_valid_cnj_digits(digits):
            return
        d = digits_only(digits)
        if d in seen:
            return
        fmt = format_npu(d)
        if not fmt:
            return
        seen.add(d)
        found.append(fmt)

    for m in _CNJ_FLEX.finditer(cleaned):
        _add("".join(m.groups()))

    for m in _CNJ_DIGITS20.finditer(cleaned):
        _add(m.group(1))

    return found
