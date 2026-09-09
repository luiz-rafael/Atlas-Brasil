"""Catálogo de órgãos do Judiciário cobertos pelo painel CNJ (~92)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

CNJ_PORTAL_URL = "https://www.cnj.jus.br/transparencia-cnj/remuneracao-dos-magistrados/"
CNJ_CORPORATIVO_URL = "https://www.cnj.jus.br/corporativo/index.php"
CNJ_QLIK_PANEL_URL = (
    "https://paineis.cnj.jus.br/QvAJAXZfc/opendoc.htm"
    "?document=qvw_l%2FPainelCNJ.qvw&host=QVS%40neodimio03"
    "&anonymous=true&sheet=shPORT63Relatorios"
)
SOURCE_ID = "cnj_magistrate_compensation"
DATASET_ID = "cnj_magistrate_compensation"
CONNECTOR_VERSION = "1.0.0"

_UFS: tuple[tuple[str, str], ...] = (
    ("AC", "do Acre"),
    ("AL", "de Alagoas"),
    ("AP", "do Amapá"),
    ("AM", "do Amazonas"),
    ("BA", "da Bahia"),
    ("CE", "do Ceará"),
    ("DF", "do Distrito Federal e dos Territórios"),
    ("ES", "do Espírito Santo"),
    ("GO", "de Goiás"),
    ("MA", "do Maranhão"),
    ("MT", "de Mato Grosso"),
    ("MS", "de Mato Grosso do Sul"),
    ("MG", "de Minas Gerais"),
    ("PA", "do Pará"),
    ("PB", "da Paraíba"),
    ("PR", "do Paraná"),
    ("PE", "de Pernambuco"),
    ("PI", "do Piauí"),
    ("RJ", "do Rio de Janeiro"),
    ("RN", "do Rio Grande do Norte"),
    ("RS", "do Rio Grande do Sul"),
    ("RO", "de Rondônia"),
    ("RR", "de Roraima"),
    ("SC", "de Santa Catarina"),
    ("SP", "de São Paulo"),
    ("SE", "de Sergipe"),
    ("TO", "do Tocantins"),
)


@dataclass(frozen=True)
class Court:
    court_id: str
    acronym: str
    name: str
    branch: str
    uf: str | None = None
    transparency_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _court(
    court_id: str,
    acronym: str,
    name: str,
    branch: str,
    uf: str | None = None,
    url: str | None = None,
) -> Court:
    return Court(
        court_id=court_id,
        acronym=acronym,
        name=name,
        branch=branch,
        uf=uf,
        transparency_url=url,
    )


def _build_courts() -> tuple[Court, ...]:
    rows: list[Court] = [
        _court("stf", "STF", "Supremo Tribunal Federal", "superior", url="https://portal.stf.jus.br/transparencia/"),
        _court("stj", "STJ", "Superior Tribunal de Justiça", "superior", url="https://www.stj.jus.br/sites/portalp/Transparencia"),
        _court("tst", "TST", "Tribunal Superior do Trabalho", "superior", url="https://www.tst.jus.br/transparencia"),
        _court("tse", "TSE", "Tribunal Superior Eleitoral", "superior", url="https://www.tse.jus.br/transparencia"),
        _court("stm", "STM", "Superior Tribunal Militar", "superior", url="https://www.stm.jus.br/transparencia"),
        _court("cnj", "CNJ", "Conselho Nacional de Justiça", "conselho", url=CNJ_PORTAL_URL),
        _court("cjf", "CJF", "Conselho da Justiça Federal", "conselho", url="https://www.cjf.jus.br/transparencia/"),
        _court("csjt", "CSJT", "Conselho Superior da Justiça do Trabalho", "conselho", url="https://www.csjt.jus.br/transparencia"),
        _court("tjmsp", "TJMSP", "Tribunal de Justiça Militar de São Paulo", "militar", "SP"),
        _court("tjmmg", "TJMMG", "Tribunal de Justiça Militar de Minas Gerais", "militar", "MG"),
        _court("tjmrs", "TJMRS", "Tribunal de Justiça Militar do Rio Grande do Sul", "militar", "RS"),
    ]
    for n in range(1, 7):
        rows.append(
            _court(f"trf{n}", f"TRF{n}", f"Tribunal Regional Federal da {n}ª Região", "federal")
        )
    for n in range(1, 25):
        rows.append(
            _court(f"trt{n}", f"TRT{n}", f"Tribunal Regional do Trabalho da {n}ª Região", "trabalho")
        )
    for uf, gentilic in _UFS:
        if uf == "DF":
            rows.append(
                _court(
                    "tjdf",
                    "TJDFT",
                    "Tribunal de Justiça do Distrito Federal e dos Territórios",
                    "estadual",
                    "DF",
                    "https://www.tjdft.jus.br/transparencia",
                )
            )
            rows.append(
                _court(
                    "tre_df",
                    "TRE-DF",
                    "Tribunal Regional Eleitoral do Distrito Federal",
                    "eleitoral",
                    "DF",
                )
            )
            continue
        rows.append(
            _court(
                f"tj{uf.lower()}",
                f"TJ{uf}",
                f"Tribunal de Justiça {gentilic}",
                "estadual",
                uf,
            )
        )
        rows.append(
            _court(
                f"tre_{uf.lower()}",
                f"TRE-{uf}",
                f"Tribunal Regional Eleitoral {gentilic}",
                "eleitoral",
                uf,
            )
        )
    return tuple(rows)


COURTS: tuple[Court, ...] = _build_courts()
COURTS_BY_ID: dict[str, Court] = {c.court_id: c for c in COURTS}
COURTS_BY_ACRONYM: dict[str, Court] = {c.acronym.upper(): c for c in COURTS}


def _norm_token(text: str) -> str:
    return (
        (text or "")
        .upper()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace(".", "")
    )


_TOKEN_INDEX: dict[str, Court] = {}
for _c in COURTS:
    _TOKEN_INDEX[_norm_token(_c.acronym)] = _c
    _TOKEN_INDEX[_norm_token(_c.court_id)] = _c


def match_court(*texts: str | None) -> Court | None:
    """Resolve tribunal por sigla/id em URL, nome de arquivo ou texto."""
    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", blob) if p]
    for part in sorted(parts, key=lambda p: len(_norm_token(p)), reverse=True):
        hit = _TOKEN_INDEX.get(_norm_token(part))
        if hit:
            return hit
    compact = _norm_token(blob)
    if compact in _TOKEN_INDEX:
        return _TOKEN_INDEX[compact]
    for court in sorted(COURTS, key=lambda c: len(_norm_token(c.acronym)), reverse=True):
        token = _norm_token(court.acronym)
        if len(token) < 3:
            continue
        if re.search(rf"(^|[^A-Z0-9]){re.escape(token)}([^A-Z0-9]|$)", compact):
            return court
        cid = _norm_token(court.court_id)
        if cid != token and re.search(rf"(^|[^A-Z0-9]){re.escape(cid)}([^A-Z0-9]|$)", compact):
            return court
    return None


def court_or_unknown(court_id: str | None) -> Court | None:
    if not court_id:
        return None
    return COURTS_BY_ID.get(court_id.lower()) or COURTS_BY_ACRONYM.get(court_id.upper())
