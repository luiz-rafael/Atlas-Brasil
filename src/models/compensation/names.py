"""Normalização de nomes e cabeçalhos. Homônimos não são chave."""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_SPACES = re.compile(r"\s+")

_TITLES = (
    "desembargador federal",
    "desembargadora federal",
    "desembargador",
    "desembargadora",
    "ministro",
    "ministra",
    "juiz federal substituto",
    "juiza federal substituta",
    "juíza federal substituta",
    "juiz federal",
    "juiza federal",
    "juíza federal",
    "juiz substituto",
    "juiza substituta",
    "juíza substituta",
    "juiz de direito",
    "juiza de direito",
    "juíza de direito",
    "juiz",
    "juiza",
    "juíza",
    "dr.",
    "dra.",
    "dr",
    "dra",
    "exmo.",
    "exma.",
    "exmo",
    "exma",
    "mm.",
    "mm",
)

_TITLE_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(t) for t in sorted(_TITLES, key=len, reverse=True)) + r")\s+",
    re.IGNORECASE,
)


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def slug_header(text: str) -> str:
    s = strip_accents(str(text or "")).lower().strip()
    s = s.replace("º", "").replace("ª", "")
    s = _NON_ALNUM.sub("_", s).strip("_")
    s = re.sub(r"_+", "_", s)
    return s


def normalize_person_name(name: str | None) -> str:
    if not name:
        return ""
    text = _SPACES.sub(" ", str(name).strip())
    text = _TITLE_RE.sub("", text)
    text = strip_accents(text).upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return _SPACES.sub(" ", text).strip()


def looks_like_total_label(name: str | None) -> bool:
    slug = slug_header(name or "")
    if not slug:
        return False
    tokens = (
        "total",
        "soma",
        "subtotal",
        "geral",
        "totais",
        "somatorio",
        "consolidado",
        "resultado",
        "folha",
        "resumo",
    )
    if slug in tokens or slug.startswith("total") or slug.startswith("soma"):
        return True
    if "total_geral" in slug or "soma_geral" in slug:
        return True
    if slug in {"t", "tt"}:
        return False
    return bool(re.match(r"^(total|soma|subtotal)(_|$)", slug))
