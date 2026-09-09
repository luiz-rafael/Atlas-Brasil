"""Normalização NPU / número CNJ e inferência de tribunal DataJud."""

from __future__ import annotations

import re

from pipelines.legal.aliases import TRE, UF_TJ, resolve_alias


def digits_only(npu: str) -> str:
    return re.sub(r"\D", "", npu or "")


def format_npu(digits: str) -> str | None:
    d = digits_only(digits)
    if len(d) != 20:
        return None
    return f"{d[0:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:20]}"


def parse_npu(npu: str) -> dict | None:
    d = digits_only(npu)
    if len(d) != 20:
        return None
    return {
        "digits": d,
        "formatted": format_npu(d),
        "year": int(d[9:13]),
        "segment": d[13],  # J
        "tribunal_code": d[14:16],  # TR
        "origin": d[16:20],
    }


def infer_alias(npu: str) -> str | None:
    """Melhor esforço a partir do segmento J + TR do NPU."""
    p = parse_npu(npu)
    if not p:
        return None
    j, tr = p["segment"], p["tribunal_code"]
    if j == "3":
        return resolve_alias("stj")
    if j == "4":
        # Justiça Federal → TRF1..6
        n = int(tr)
        if 1 <= n <= 6:
            return resolve_alias(f"trf{n}")
    if j == "5":
        n = int(tr)
        if 1 <= n <= 24:
            return resolve_alias(f"trt{n}")
        return resolve_alias("tst")
    if j == "6":
        slug = TRE.get(tr)
        return resolve_alias(slug) if slug else resolve_alias("tse")
    if j == "8":
        slug = UF_TJ.get(tr)
        return resolve_alias(slug) if slug else None
    if j == "9":
        # militar estadual — subset
        if tr == "13":
            return resolve_alias("tjmmg")
        if tr == "21":
            return resolve_alias("tjmrs")
        if tr == "26":
            return resolve_alias("tjmsp")
    return None
