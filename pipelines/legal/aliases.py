"""Aliases da API pública DataJud (wiki CNJ)."""

from __future__ import annotations

# https://datajud-wiki.cnj.jus.br/api-publica/endpoints/
ALIASES: dict[str, str] = {
    "tst": "api_publica_tst",
    "tse": "api_publica_tse",
    "stj": "api_publica_stj",
    "stm": "api_publica_stm",
    "trf1": "api_publica_trf1",
    "trf2": "api_publica_trf2",
    "trf3": "api_publica_trf3",
    "trf4": "api_publica_trf4",
    "trf5": "api_publica_trf5",
    "trf6": "api_publica_trf6",
    "tjac": "api_publica_tjac",
    "tjal": "api_publica_tjal",
    "tjam": "api_publica_tjam",
    "tjap": "api_publica_tjap",
    "tjba": "api_publica_tjba",
    "tjce": "api_publica_tjce",
    "tjdft": "api_publica_tjdft",
    "tjes": "api_publica_tjes",
    "tjgo": "api_publica_tjgo",
    "tjma": "api_publica_tjma",
    "tjmg": "api_publica_tjmg",
    "tjms": "api_publica_tjms",
    "tjmt": "api_publica_tjmt",
    "tjpa": "api_publica_tjpa",
    "tjpb": "api_publica_tjpb",
    "tjpe": "api_publica_tjpe",
    "tjpi": "api_publica_tjpi",
    "tjpr": "api_publica_tjpr",
    "tjrj": "api_publica_tjrj",
    "tjrn": "api_publica_tjrn",
    "tjro": "api_publica_tjro",
    "tjrr": "api_publica_tjrr",
    "tjrs": "api_publica_tjrs",
    "tjsc": "api_publica_tjsc",
    "tjse": "api_publica_tjse",
    "tjsp": "api_publica_tjsp",
    "tjto": "api_publica_tjto",
}

# Justiça Estadual: código tribunal (2 dígitos NPU) → sigla
UF_TJ = {
    "01": "tjac",
    "02": "tjal",
    "03": "tjap",
    "04": "tjam",
    "05": "tjba",
    "06": "tjce",
    "07": "tjdft",
    "08": "tjes",
    "09": "tjgo",
    "10": "tjma",
    "11": "tjmt",
    "12": "tjms",
    "13": "tjmg",
    "14": "tjpa",
    "15": "tjpb",
    "16": "tjpr",
    "17": "tjpe",
    "18": "tjpi",
    "19": "tjrj",
    "20": "tjrn",
    "21": "tjrs",
    "22": "tjro",
    "23": "tjrr",
    "24": "tjsc",
    "25": "tjse",
    "26": "tjsp",
    "27": "tjto",
}

TRE = {
    "01": "tre-ac",
    "02": "tre-al",
    "03": "tre-ap",
    "04": "tre-am",
    "05": "tre-ba",
    "06": "tre-ce",
    "07": "tre-dft",
    "08": "tre-es",
    "09": "tre-go",
    "10": "tre-ma",
    "11": "tre-mt",
    "12": "tre-ms",
    "13": "tre-mg",
    "14": "tre-pa",
    "15": "tre-pb",
    "16": "tre-pr",
    "17": "tre-pe",
    "18": "tre-pi",
    "19": "tre-rj",
    "20": "tre-rn",
    "21": "tre-rs",
    "22": "tre-ro",
    "23": "tre-rr",
    "24": "tre-sc",
    "25": "tre-se",
    "26": "tre-sp",
    "27": "tre-to",
}

for i in range(1, 25):
    ALIASES[f"trt{i}"] = f"api_publica_trt{i}"
for code, slug in TRE.items():
    ALIASES[slug] = f"api_publica_{slug}"
ALIASES["tjmmg"] = "api_publica_tjmmg"
ALIASES["tjmrs"] = "api_publica_tjmrs"
ALIASES["tjmsp"] = "api_publica_tjmsp"


def resolve_alias(court_key: str) -> str | None:
    k = (court_key or "").strip().lower().replace("api_publica_", "")
    if k.startswith("api_publica_"):
        return k if k in ALIASES.values() else f"api_publica_{k}"
    if k in ALIASES:
        return ALIASES[k]
    if f"api_publica_{k}" in ALIASES.values():
        return f"api_publica_{k}"
    return ALIASES.get(k) or (f"api_publica_{k}" if k else None)
