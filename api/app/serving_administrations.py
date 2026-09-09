"""ADMINISTRATION / MANDATE serving — Fase B.

Fonte: silver governadores (TSE) + resolução de PERSON via KB quando possível.
Indicadores NÃO são copiados para cá — join por território+ano na camada C.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.cache import cache_get, cache_set
from app.db import get_conn
from app.kb_loader import load_kb

DISCLAIMER = (
    "O Atlas não acusa. O Atlas documenta. "
    "Administração vigente ≠ causalidade sobre indicadores do período. "
    "Mandato documentado ≠ culpa."
)

ROOT = Path(__file__).resolve().parents[2]
SILVER_MANDATOS = ROOT / "data" / "lake" / "silver" / "governadores" / "mandatos_latest.jsonl"
_ADMIN_SOURCE = "silver_governadores"


def _year_from_iso(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(str(s)[:4])
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _person_resolve() -> dict[str, str]:
    """Mapa stub TSE / nome_norm → person_id canônico na KB."""
    kb = load_kb()
    by_stub: dict[str, str] = {}
    by_cpf: dict[str, str] = {}
    by_nome: dict[str, str] = {}
    for e in kb.get("entidades") or []:
        if e.get("tipo") != "pessoa":
            continue
        pid = e.get("id")
        if not pid:
            continue
        for sid in e.get("source_ids") or []:
            if isinstance(sid, str) and sid.startswith("tse:"):
                by_stub[f"p_tse_{sid[4:]}"] = pid
        if str(pid).startswith("p_tse_"):
            by_stub[pid] = pid
        cpf = "".join(c for c in str(e.get("cpf") or "") if c.isdigit())
        if len(cpf) == 11:
            by_cpf[cpf] = pid
        nn = (e.get("nome_norm") or e.get("nome") or "").upper().strip()
        if nn:
            by_nome[nn] = pid
        for m in e.get("mandatos") or []:
            mid = m.get("id")
            if mid and "governador" in str(m.get("cargo") or "").lower():
                # tenure_gov_UF_ANO_SQ → stub
                parts = str(mid).split("_")
                if len(parts) >= 5 and parts[0] == "tenure":
                    sq = parts[-1]
                    by_stub[f"p_tse_{sq}"] = pid
    return {"__cpf__": json.dumps(by_cpf), "__nome__": json.dumps(by_nome), **by_stub}


def resolve_person_id(stub: str | None, cpf: str | None = None, nome: str | None = None) -> str | None:
    """Resolve stub TSE → id canônico.

    Ordem: mapa explícito do stub → stub bruto (sem CPF/nome se stub existe)
    → CPF → nome. Homônimos e CPF duplicados na KB não devem sobrescrever o stub TSE.
    """
    m = _person_resolve()
    if stub and stub in m and not stub.startswith("__"):
        return m[stub]
    if stub:
        return stub
    cpf_map = json.loads(m.get("__cpf__", "{}"))
    if cpf:
        digits = "".join(c for c in cpf if c.isdigit())
        if digits in cpf_map:
            return cpf_map[digits]
    nome_map = json.loads(m.get("__nome__", "{}"))
    if nome:
        key = nome.upper().strip()
        if key in nome_map:
            return nome_map[key]
    return None


@lru_cache(maxsize=1)
def load_mandatos_silver() -> list[dict[str, Any]]:
    if not SILVER_MANDATOS.is_file():
        return []
    rows = []
    for line in SILVER_MANDATOS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def mandate_from_silver(row: dict[str, Any]) -> dict[str, Any]:
    uf = (row.get("uf") or "").upper()
    person_stub = row.get("person_id")
    person_id = resolve_person_id(
        person_stub, cpf=row.get("cpf"), nome=row.get("nome")
    )
    return {
        "mandate_id": row.get("id"),
        "person_id": person_id or person_stub,
        "person_stub": person_stub,
        "person_name": row.get("nome") or row.get("nome_urna"),
        "office": row.get("cargo") or "Governador",
        "territory_id": f"uf_{uf}" if uf else None,
        "state_code": uf or None,
        "start_date": row.get("inicio"),
        "end_date": row.get("fim"),
        "election_year": row.get("ano_eleicao"),
        "party_at_start": row.get("partido"),
        "source": row.get("fonte") or "tse_ckan",
        "source_url": row.get("fonte_url"),
        "evidence_degree": row.get("grau_confirmacao") or "fato_documentado",
    }


def administration_from_mandate(m: dict[str, Any]) -> dict[str, Any]:
    uf = m.get("state_code") or ""
    start_y = _year_from_iso(m.get("start_date")) or m.get("election_year")
    end_y = _year_from_iso(m.get("end_date"))
    adm_id = f"adm_state_{uf}_{start_y}_{end_y or 'open'}"
    return {
        "administration_id": adm_id,
        "territory_id": m.get("territory_id"),
        "state_code": uf,
        "administration_type": "STATE_ADMINISTRATION",
        "executive_person_id": m.get("person_id"),
        "executive_person_name": m.get("person_name"),
        "start_date": m.get("start_date"),
        "end_date": m.get("end_date"),
        "party_at_start": m.get("party_at_start"),
        "mandate_id": m.get("mandate_id"),
        "election_year": m.get("election_year"),
        "source": m.get("source"),
        "source_url": m.get("source_url"),
        "disclaimer": DISCLAIMER,
    }


def _from_postgres() -> list[dict[str, Any]] | None:
    """Se tabelas existirem e tiverem linhas, preferir PG."""
    conn = get_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT administration_id, territory_id, state_code, administration_type,
                       executive_person_id, executive_person_name, start_date, end_date,
                       party_at_start, mandate_id, election_year, source, source_url
                FROM administrations
                ORDER BY start_date DESC NULLS LAST
                """
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            if not rows:
                return None
            for r in rows:
                for k in ("start_date", "end_date"):
                    if r.get(k) is not None:
                        r[k] = str(r[k])
            return rows
    except Exception:
        return None


@lru_cache(maxsize=1)
def list_administrations_cached() -> tuple[dict[str, Any], ...]:
    global _ADMIN_SOURCE
    pg = _from_postgres()
    if pg is not None:
        _ADMIN_SOURCE = "postgres"
        return tuple(pg)
    _ADMIN_SOURCE = "silver_governadores"
    mandatos = [mandate_from_silver(r) for r in load_mandatos_silver()]
    admins = [administration_from_mandate(m) for m in mandatos]
    seen: dict[str, dict] = {}
    for a in admins:
        seen[a["administration_id"]] = a
    return tuple(seen.values())


def clear_admin_cache() -> None:
    list_administrations_cached.cache_clear()
    load_mandatos_silver.cache_clear()
    _person_resolve.cache_clear()


def list_administrations(
    *,
    state_code: str | None = None,
    territory_id: str | None = None,
    year: int | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    cache_key = f"adm:list:{state_code}:{territory_id}:{year}:{limit}:{offset}"
    hit = cache_get(cache_key)
    if hit:
        return hit
    items = list(list_administrations_cached())
    if state_code:
        uf = state_code.upper()
        items = [a for a in items if (a.get("state_code") or "").upper() == uf]
    if territory_id:
        items = [a for a in items if a.get("territory_id") == territory_id]
    if year is not None:
        items = [a for a in items if covers_year(a, year)]
    total = len(items)
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))
    out = {
        "ok": True,
        "total": total,
        "items": items[offset : offset + limit],
        "disclaimer": DISCLAIMER,
        "source": _ADMIN_SOURCE,
    }
    cache_set(cache_key, out, 120)
    return out


def covers_year(admin: dict[str, Any], year: int) -> bool:
    """Ano de referência ∈ [start, end) — end exclusivo quando conhecido."""
    y0 = _year_from_iso(admin.get("start_date"))
    y1 = _year_from_iso(admin.get("end_date"))
    if y0 is None:
        return False
    if year < y0:
        return False
    if y1 is not None and year >= y1:
        return False
    if y1 is None and year > y0 + 4:
        return False
    return True


def get_administration(administration_id: str) -> dict[str, Any] | None:
    for a in list_administrations_cached():
        if a.get("administration_id") == administration_id:
            return {**a, "disclaimer": DISCLAIMER}
    return None


def administration_at(territory_id: str, year: int) -> dict[str, Any] | None:
    tid = territory_id
    if tid.startswith("UF_"):
        tid = f"uf_{tid[3:].upper()}"
    if len(tid) == 2 and tid.isalpha():
        tid = f"uf_{tid.upper()}"
    candidates = [
        a
        for a in list_administrations_cached()
        if a.get("territory_id") == tid and covers_year(a, year)
    ]
    if not candidates:
        return None
    # prefer more recent start
    candidates.sort(key=lambda a: a.get("start_date") or "", reverse=True)
    return candidates[0]


def list_mandates(
    *,
    state_code: str | None = None,
    person_id: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    items = [mandate_from_silver(r) for r in load_mandatos_silver()]
    if state_code:
        uf = state_code.upper()
        items = [m for m in items if (m.get("state_code") or "").upper() == uf]
    if person_id:
        items = [
            m
            for m in items
            if m.get("person_id") == person_id or m.get("person_stub") == person_id
        ]
    items.sort(key=lambda m: m.get("election_year") or 0, reverse=True)
    return {
        "ok": True,
        "total": len(items),
        "items": items[: max(1, min(limit, 2000))],
        "disclaimer": DISCLAIMER,
        "source": "silver_governadores",
    }
