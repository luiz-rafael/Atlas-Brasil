#!/usr/bin/env python3
"""
Silver CNPJ RFB — COMPANY master + SCD2-ish status/partners.

De bronze rfb_cnpj/*/cnpj_extract.jsonl (mais recente) → silver/companies/:
  - companies_latest.jsonl
  - company_status_history_latest.jsonl  (fecha is_current quando situação muda; observed_at)
  - company_partners_latest.jsonl        (snapshot QSA com observed_at)

Merge por CNPJ. Enriquece gold KB e_cnpj_* (nome/cnae/situacao) sem criar arestas políticas.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402


def only_cnpj14(val) -> str | None:
    if val is None:
        return None
    d = re.sub(r"\D", "", str(val))
    if len(d) >= 14:
        d = d.zfill(14)[-14:]
    elif d:
        d = d.zfill(14)
    return d if len(d) == 14 else None


def latest_extract() -> Path | None:
    base = LAKE / "bronze" / "rfb_cnpj"
    if not base.exists():
        return None
    candidates: list[Path] = []
    for day in base.iterdir():
        if not day.is_dir():
            continue
        p = day / "cnpj_extract.jsonl"
        if p.exists():
            candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def cnae_code(row: dict) -> str | None:
    c = row.get("cnae_fiscal")
    if isinstance(c, dict):
        code = c.get("codigo")
        return str(code) if code is not None else None
    if c is not None:
        return str(c)
    return None


def cnae_desc(row: dict) -> str | None:
    c = row.get("cnae_fiscal")
    if isinstance(c, dict):
        return c.get("descricao")
    return None


def merge_companies(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by: dict[str, dict] = {}
    for r in existing:
        c = only_cnpj14(r.get("cnpj"))
        if c:
            by[c] = r
    for r in incoming:
        c = only_cnpj14(r.get("cnpj"))
        if not c:
            continue
        prev = by.get(c) or {}
        by[c] = {**prev, **r, "cnpj": c, "company_id": f"co_{c}"}
    return sorted(by.values(), key=lambda x: x["cnpj"])


def merge_status(existing: list[dict], incoming_companies: list[dict], observed_at: str) -> list[dict]:
    """SCD2-ish: se situacao mudou, fecha anterior (is_current=false, valid_to=observed_at)."""
    hist = list(existing)
    current_by: dict[str, dict] = {}
    for h in hist:
        if h.get("is_current") and only_cnpj14(h.get("cnpj")):
            current_by[only_cnpj14(h["cnpj"])] = h  # type: ignore[index]

    for co in incoming_companies:
        cnpj = only_cnpj14(co.get("cnpj"))
        if not cnpj:
            continue
        situacao = co.get("situacao_cadastral")
        if not situacao:
            continue
        prev = current_by.get(cnpj)
        data_sit = co.get("data_situacao")
        if prev and str(prev.get("status") or "").upper() == str(situacao).upper():
            # mesma situação — atualiza observed_at / source fields leves
            prev["observed_at"] = observed_at
            prev["retrieved_at"] = co.get("retrieved_at") or observed_at
            continue
        if prev:
            prev["is_current"] = False
            prev["valid_to"] = observed_at
        entry = {
            "status_id": f"cos_{cnpj}_{observed_at[:10].replace('-', '')}",
            "company_id": f"co_{cnpj}",
            "cnpj": cnpj,
            "status": situacao,
            "valid_from": data_sit or None,
            "valid_to": None,
            "is_current": True,
            "observed_at": observed_at,
            "data_situacao_fonte": data_sit,
            "source": co.get("source") or "rfb_cnpj",
            "retrieved_at": co.get("retrieved_at") or observed_at,
        }
        hist.append(entry)
        current_by[cnpj] = entry
    return hist


def merge_partners(existing: list[dict], incoming_companies: list[dict], observed_at: str) -> list[dict]:
    """Snapshot QSA: marca snapshots anteriores is_current=false para o mesmo CNPJ."""
    hist = list(existing)
    for h in hist:
        c = only_cnpj14(h.get("cnpj"))
        if c and h.get("is_current"):
            # será fechado se houver novo snapshot para o CNPJ
            pass

    incoming_cnpjs = set()
    new_rows: list[dict] = []
    for co in incoming_companies:
        cnpj = only_cnpj14(co.get("cnpj"))
        if not cnpj:
            continue
        socios = co.get("socios") or []
        if not socios:
            continue
        incoming_cnpjs.add(cnpj)
        for i, s in enumerate(socios):
            new_rows.append(
                {
                    "partner_row_id": f"cop_{cnpj}_{i}_{observed_at[:10].replace('-', '')}",
                    "company_id": f"co_{cnpj}",
                    "cnpj": cnpj,
                    "partner_name": s.get("nome"),
                    "partner_cnpj_cpf": s.get("cnpj_cpf"),
                    "qualification": s.get("qualificacao"),
                    "is_current": True,
                    "observed_at": observed_at,
                    "valid_from": None,
                    "valid_to": None,
                    "source": co.get("source") or "rfb_cnpj",
                    "retrieved_at": co.get("retrieved_at") or observed_at,
                }
            )

    for h in hist:
        c = only_cnpj14(h.get("cnpj"))
        if c in incoming_cnpjs and h.get("is_current"):
            h["is_current"] = False
            h["valid_to"] = observed_at

    return hist + new_rows


def enrich_gold(companies: list[dict]) -> int:
    gold_path = ROOT / "data" / "atlas-brasil-kb-gold.json"
    if not gold_path.is_file():
        return 0
    kb = json.loads(gold_path.read_text(encoding="utf-8"))
    by_cnpj = {
        only_cnpj14(co.get("cnpj")): co
        for co in companies
        if only_cnpj14(co.get("cnpj"))
    }
    n = 0
    for e in kb.get("entidades") or []:
        if e.get("tipo") != "empresa":
            continue
        eid = str(e.get("id") or "")
        cnpj = only_cnpj14(e.get("cnpj"))
        if not cnpj and eid.startswith("e_cnpj_"):
            cnpj = only_cnpj14(eid[7:])
        if not cnpj or cnpj not in by_cnpj:
            continue
        co = by_cnpj[cnpj]
        nome = co.get("razao_social") or co.get("nome_fantasia")
        if nome and (not e.get("nome") or str(e.get("nome")).startswith("CNPJ")):
            e["nome"] = nome
        if co.get("nome_fantasia"):
            e["nome_fantasia"] = co["nome_fantasia"]
        if co.get("situacao_cadastral"):
            e["situacao_cadastral"] = co["situacao_cadastral"]
            e["rfb_status"] = co["situacao_cadastral"]
        code = co.get("cnae_fiscal") or cnae_code(co)
        if code:
            e["cnae_fiscal"] = code
            e["cnae_descricao"] = co.get("cnae_fiscal_descricao") or cnae_desc(co)
        if co.get("uf"):
            e["uf"] = co["uf"]
        if co.get("municipio"):
            e["municipio"] = co["municipio"]
        e["rfb_enriched_at"] = co.get("retrieved_at") or utc_now()
        tags = list(e.get("tags") or [])
        if "rfb_cnpj" not in tags:
            tags.append("rfb_cnpj")
        e["tags"] = tags
        n += 1
    gold_path.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")
    return n


def company_row(raw: dict) -> dict:
    cnpj = only_cnpj14(raw.get("cnpj")) or ""
    return {
        "company_id": f"co_{cnpj}",
        "cnpj": cnpj,
        "cnpj_basico": raw.get("cnpj_basico") or (cnpj[:8] if len(cnpj) == 14 else None),
        "razao_social": raw.get("razao_social"),
        "nome_fantasia": raw.get("nome_fantasia"),
        "situacao_cadastral": raw.get("situacao_cadastral"),
        "data_situacao": raw.get("data_situacao"),
        "natureza_juridica": raw.get("natureza_juridica"),
        "data_abertura": raw.get("data_abertura"),
        "capital_social": raw.get("capital_social"),
        "porte": raw.get("porte"),
        "cnae_fiscal": cnae_code(raw),
        "cnae_fiscal_descricao": cnae_desc(raw),
        "cnae_secundarios": raw.get("cnae_secundarios"),
        "municipio": raw.get("municipio"),
        "uf": raw.get("uf"),
        "simples": raw.get("simples"),
        "mei": raw.get("mei"),
        "retrieved_at": raw.get("retrieved_at"),
        "source": raw.get("source") or "rfb_cnpj",
        "updated_at": utc_now(),
    }


def main() -> int:
    extract_path = latest_extract()
    if not extract_path:
        print("SKIPPED silver_cnpj_rfb: bronze extract ausente", flush=True)
        return 0

    raw_rows = read_jsonl(extract_path)
    incoming = [company_row(r) for r in raw_rows if only_cnpj14(r.get("cnpj"))]
    # keep socios on a side channel from raw
    raw_by = {only_cnpj14(r.get("cnpj")): r for r in raw_rows if only_cnpj14(r.get("cnpj"))}
    for co in incoming:
        raw = raw_by.get(co["cnpj"]) or {}
        co["socios"] = raw.get("socios") or []
        co["source"] = raw.get("source") or co.get("source")
        co["retrieved_at"] = raw.get("retrieved_at") or co.get("retrieved_at")

    out = LAKE / "silver" / "companies"
    out.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    observed = utc_now()

    companies = merge_companies(read_jsonl(out / "companies_latest.jsonl"), incoming)
    # strip socios from company master for cleaner COMPANY table
    companies_clean = []
    for c in companies:
        cc = {k: v for k, v in c.items() if k != "socios"}
        companies_clean.append(cc)

    status = merge_status(
        read_jsonl(out / "company_status_history_latest.jsonl"),
        incoming,
        observed,
    )
    partners = merge_partners(
        read_jsonl(out / "company_partners_latest.jsonl"),
        incoming,
        observed,
    )

    write_jsonl(out / "companies_latest.jsonl", companies_clean)
    write_jsonl(out / f"companies_{stamp}.jsonl", companies_clean)
    write_jsonl(out / "company_status_history_latest.jsonl", status)
    write_jsonl(out / f"company_status_history_{stamp}.jsonl", status)
    write_jsonl(out / "company_partners_latest.jsonl", partners)
    write_jsonl(out / f"company_partners_{stamp}.jsonl", partners)
    write_json(
        out / "meta.json",
        {
            "updated_at": observed,
            "bronze_extract": str(extract_path),
            "companies": len(companies_clean),
            "status_rows": len(status),
            "partner_rows": len(partners),
            "incoming": len(incoming),
        },
    )

    gold_n = enrich_gold(incoming)
    print(
        f"OK silver_cnpj_rfb companies={len(companies_clean)} "
        f"status={len(status)} partners={len(partners)} gold_enriched={gold_n} -> {out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
