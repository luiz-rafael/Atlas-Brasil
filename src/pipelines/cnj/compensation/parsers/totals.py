"""Detecção de linhas de totalização (não são indivíduos)."""

from __future__ import annotations

from src.models.compensation.names import looks_like_total_label, normalize_person_name

_TOTALISH = (
    "total",
    "soma",
    "subtotal",
    "geral",
    "totais",
    "consolidado",
    "resumo da folha",
    "folha de pagamento",
)


def is_total_row(row: dict) -> bool:
    name = None
    for key in ("nome", "name", "magistrado", "servidor"):
        if row.get(key):
            name = str(row[key])
            break
    if name is None:
        for k, v in row.items():
            if "nome" in str(k).lower() and v:
                name = str(v)
                break
    if looks_like_total_label(name):
        return True
    if name and normalize_person_name(name) in {"TOTAL", "SOMA", "SUBTOTAL", "GERAL"}:
        return True
    blob = " ".join(str(v) for v in list(row.values())[:4] if v).lower()
    if any(blob.strip() == t or blob.startswith(t + " ") for t in _TOTALISH):
        return True
    ident = row.get("cpf") or row.get("matricula") or row.get("source_person_identifier")
    if not name and not ident:
        numeric_only = True
        nonempty = 0
        for v in row.values():
            if v is None or str(v).strip() == "":
                continue
            nonempty += 1
            try:
                float(str(v).replace(".", "").replace(",", "."))
            except ValueError:
                numeric_only = False
                break
        if nonempty >= 3 and numeric_only:
            return True
    return False
