#!/usr/bin/env python3
"""
DataJud — coleta em 3 níveis (não espelho do Judiciário).

1) Discovery OFFICIAL_REFERENCE / COMPANY_CONTEXT / PERSON_CONTEXT → fila
2) Lookup DataJud só se gate INGEST
3) KNOWN_REFRESH: processos em known_legal_cases (skip se last_movement igual)

Entrada:
  data/lake/queues/datajud_discovery.jsonl
  ou ATLAS_DATAJUD_NPUS (legado → discovery_type=MANUAL)

Requer ATLAS_DATAJUD_API_KEY.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from pipelines.common import (  # noqa: E402
    UA,
    append_event,
    bronze_dir,
    day_stamp,
    sha1_bytes,
    throttle,
    utc_now,
    write_json,
    write_jsonl,
    write_manifest,
)
from pipelines.legal.aliases import resolve_alias  # noqa: E402
from pipelines.legal.discovery import (  # noqa: E402
    decide_ingest,
    discovery_provenance_blurb,
    make_discovery,
    to_quarantine_if_needed,
)
from pipelines.legal.npu import digits_only, format_npu, infer_alias  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

BASE = os.getenv("DATAJUD_BASE", "https://api-publica.datajud.cnj.jus.br").rstrip("/")
DISCOVERY_QUEUE = ROOT / "data" / "lake" / "queues" / "datajud_discovery.jsonl"
LEGACY_QUEUE = ROOT / "data" / "lake" / "queues" / "datajud_npus.jsonl"
KNOWN_PATH = ROOT / "data" / "lake" / "silver" / "legal" / "known_legal_cases.jsonl"
TERMS_URL = "https://datajud-wiki.cnj.jus.br/api-publica/"
TERMS_VERSION = os.getenv("ATLAS_DATAJUD_TERMS_VERSION", "wiki-acesso-2026-08")


def load_known() -> dict[str, dict]:
    if not KNOWN_PATH.exists():
        return {}
    out = {}
    for line in KNOWN_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = row.get("process_number_normalized") or digits_only(row.get("process_number") or "")
        if d:
            out[d] = row
    return out


def load_discoveries() -> list[dict]:
    items: list[dict] = []
    # env legado
    env_list = os.getenv("ATLAS_DATAJUD_NPUS", "").strip()
    if env_list:
        for part in env_list.split(","):
            part = part.strip()
            if not part:
                continue
            alias, npu = (None, part)
            if ":" in part and not part.split(":", 1)[0][0].isdigit():
                alias, npu = part.split(":", 1)
            disc = make_discovery(
                npu.strip(),
                discovered_by_source="manual_env",
                discovery_type="MANUAL",
                discovery_reference=alias,
            )
            if alias:
                disc["tribunal_alias"] = alias.strip()
            items.append(disc)

    for path in (DISCOVERY_QUEUE, LEGACY_QUEUE):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            npu = row.get("process_number") or row.get("numeroProcesso") or row.get("npu")
            if not npu:
                continue
            if row.get("discovery_type") or row.get("discovered_by_source"):
                disc = make_discovery(
                    npu,
                    discovered_by_source=str(row.get("discovered_by_source") or "queue"),
                    discovery_type=str(row.get("discovery_type") or "MANUAL"),
                    discovered_by_entity_id=row.get("discovered_by_entity_id") or row.get("entity_id"),
                    discovery_reference=row.get("discovery_reference") or row.get("tribunal_alias"),
                    case_id=row.get("case_id"),
                )
            else:
                disc = make_discovery(
                    npu,
                    discovered_by_source=str(row.get("seed_source_id") or "queue"),
                    discovery_type="MANUAL",
                    discovered_by_entity_id=row.get("entity_id"),
                    discovery_reference=row.get("tribunal_alias"),
                )
            if row.get("tribunal_alias"):
                disc["tribunal_alias"] = row["tribunal_alias"]
            items.append(disc)

    # Nível 3: known refresh
    known = load_known()
    for d, row in known.items():
        if not row.get("active", True):
            continue
        disc = make_discovery(
            format_npu(d) or d,
            discovered_by_source="atlas_known",
            discovery_type="KNOWN_REFRESH",
            discovered_by_entity_id=row.get("anchor_entity_id"),
            case_id=row.get("case_id"),
        )
        if row.get("court_alias"):
            disc["tribunal_alias"] = row["court_alias"]
        disc["_known_last_movement_at"] = row.get("last_movement_at")
        items.append(disc)

    # dedupe by digits (prefer OFFICIAL_REFERENCE)
    priority = {
        "OFFICIAL_REFERENCE": 0,
        "COMPANY_CONTEXT": 1,
        "PERSON_CONTEXT": 2,
        "KNOWN_REFRESH": 3,
        "MANUAL": 4,
    }
    best: dict[str, dict] = {}
    for it in items:
        d = it.get("process_number_normalized") or ""
        if len(d) != 20:
            continue
        prev = best.get(d)
        if not prev or priority.get(it.get("discovery_type"), 9) < priority.get(prev.get("discovery_type"), 9):
            best[d] = it
    return list(best.values())


def search_process(alias: str, digits: str, api_key: str) -> dict:
    url = f"{BASE}/{alias}/_search"
    headers = {
        "Authorization": f"APIKey {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,
    }
    body = {"size": 10, "query": {"match": {"numeroProcesso": digits}}}
    throttle()
    r = httpx.post(url, headers=headers, json=body, timeout=90.0)
    payload = {
        "http_status": r.status_code,
        "url": url,
        "alias": alias,
        "query_digits": digits,
        "retrieved_at": utc_now(),
    }
    try:
        payload["response"] = r.json()
    except Exception:
        payload["response_text"] = r.text[:4000]
    return payload


def extract_hits(payload: dict) -> list[dict]:
    resp = payload.get("response") or {}
    hits = ((resp.get("hits") or {}).get("hits")) or []
    return [h.get("_source") or h for h in hits if isinstance(h, dict)]


def last_movement_ts(src: dict) -> str | None:
    movs = src.get("movimentos") or []
    if not movs:
        return None
    dates = []
    for m in movs:
        if isinstance(m, dict) and m.get("dataHora"):
            dates.append(str(m["dataHora"]))
    return max(dates) if dates else None


def main() -> int:
    run = start_run("cnj_datajud", "cnj.datajud.enrich")
    out = bronze_dir("cnj_datajud")
    key = os.getenv("ATLAS_DATAJUD_API_KEY", "").strip()
    now = utc_now()
    meta = {
        "fetched_at": now,
        "base": BASE,
        "ingestion_run_id": run["ingestion_run_id"],
        "day": day_stamp(),
        "collection_mode": "scoped_enrichment_3_levels",
        "not": ["national_judiciary_mirror", "person_name_search", "indiscriminate_cnpj_dump"],
        "terms_url": TERMS_URL,
        "terms_version": TERMS_VERSION,
        "terms_checked_at": now,
        "usage_policy": "NON_COMMERCIAL",
        "regulation": {
            "portaria_374_2026": "https://atos.cnj.jus.br/atos/detalhar/6972",
            "wiki": TERMS_URL,
        },
        "rule": (
            "O Atlas não coleta o DataJud inteiro. "
            "Coleta e atualiza somente processos públicos documentalmente "
            "relacionados a pessoas, empresas ou entidades do escopo."
        ),
    }

    if not key:
        write_json(out / "stub.json", {"status": "skipped_no_api_key"})
        write_manifest(out, "cnj_datajud", [{"file": "stub.json"}], extra=meta)
        mark_ingested("cnj_datajud", run_id=run["ingestion_run_id"], counts={"stub": 1}, ok=True)
        print("DataJud: stub (sem API key)")
        return 0

    discoveries_raw = load_discoveries()
    decided = [decide_ingest(d) for d in discoveries_raw]
    quarantine = []
    for d in decided:
        q = to_quarantine_if_needed(d, retrieved_at=now)
        if q:
            quarantine.append(q)

    to_ingest = [d for d in decided if d.get("ingest_decision") == "INGEST"]
    ignored = [d for d in decided if d.get("ingest_decision") == "IGNORE"]
    max_env = os.getenv("ATLAS_DATAJUD_MAX", "").strip()
    if max_env.isdigit():
        lim = int(max_env)
        if lim >= 0 and len(to_ingest) > lim:
            print(f"DataJud: limitando ingest {len(to_ingest)} → {lim} (ATLAS_DATAJUD_MAX)")
            to_ingest = to_ingest[:lim]

    write_jsonl(out / "case_discovery.jsonl", decided)
    if quarantine:
        write_jsonl(out / "quarantine.jsonl", quarantine)
    if ignored:
        write_jsonl(out / "ignored_discovery.jsonl", ignored)

    if not to_ingest:
        write_json(out / "empty_after_gate.json", {"discoveries": len(decided), "ingest": 0})
        write_manifest(out, "cnj_datajud", [{"file": "case_discovery.jsonl"}], extra=meta)
        mark_ingested(
            "cnj_datajud",
            run_id=run["ingestion_run_id"],
            counts={"discoveries": len(decided), "ingest": 0, "ignored": len(ignored)},
            ok=True,
            dataset_id="cnj.datajud.enrich",
        )
        print(f"DataJud: gate fechou tudo discoveries={len(decided)} ignored={len(ignored)}")
        return 0

    raw_dir = out / "raw_searches"
    raw_dir.mkdir(exist_ok=True)
    cases: list[dict] = []
    movements: list[dict] = []
    subjects: list[dict] = []
    known_updates: list[dict] = []
    errors: list[dict] = []
    skipped_unchanged = 0
    ok = 0

    for item in to_ingest:
        digits = item["process_number_normalized"]
        alias_key = item.get("tribunal_alias") or infer_alias(digits)
        alias = resolve_alias(str(alias_key)) if alias_key else None
        if not alias:
            errors.append({"digits": digits, "error": "UNKNOWN_COURT"})
            quarantine.append(
                to_quarantine_if_needed(
                    {**item, "ingest_decision": "QUARANTINE", "decision_reason": "UNKNOWN_COURT"},
                    retrieved_at=now,
                )
            )
            continue
        try:
            payload = search_process(alias, digits, key)
        except Exception as e:
            errors.append({"digits": digits, "alias": alias, "error": str(e)})
            continue

        fname = f"{alias}_{digits}.json"
        (raw_dir / fname).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        hits = extract_hits(payload)
        if payload.get("http_status") != 200 or not hits:
            errors.append({"digits": digits, "alias": alias, "http_status": payload.get("http_status"), "error": "no_hits"})
            continue

        src = hits[0]
        lm = last_movement_ts(src)
        # Nível 3: skip se last_movement não mudou
        if item.get("discovery_type") == "KNOWN_REFRESH":
            prev = item.get("_known_last_movement_at")
            if prev and lm and prev == lm:
                skipped_unchanged += 1
                known_updates.append(
                    {
                        "process_number_normalized": digits,
                        "last_checked_at": now,
                        "last_movement_at": lm,
                        "skipped": True,
                    }
                )
                continue

        npu = format_npu(digits) or digits
        case_id = item.get("case_id") or f"case_cnj_{digits}"
        tribunal = (src.get("tribunal") or {}).get("sigla") if isinstance(src.get("tribunal"), dict) else src.get("tribunal")
        orgao = src.get("orgaoJulgador") or {}
        classe = src.get("classe") or {}
        assuntos = src.get("assuntos") or []

        cases.append(
            {
                "case_id": case_id,
                "canonical_case_id": f"canon_{digits}",
                "process_number": npu,
                "process_number_normalized": digits,
                "court_code": tribunal,
                "court_name": tribunal,
                "court": tribunal or alias.replace("api_publica_", "").upper(),
                "jurisdiction_degree": src.get("grau"),
                "judging_body_code": orgao.get("codigo") if isinstance(orgao, dict) else None,
                "judging_body_name": orgao.get("nome") if isinstance(orgao, dict) else orgao,
                "judging_body": orgao.get("nome") if isinstance(orgao, dict) else orgao,
                "procedural_class_code": classe.get("codigo") if isinstance(classe, dict) else None,
                "procedural_class_name": classe.get("nome") if isinstance(classe, dict) else classe,
                "procedural_class": classe.get("nome") if isinstance(classe, dict) else classe,
                "electronic_process": src.get("procEl") if "procEl" in src else src.get("tramitacaoEletronica"),
                "system_name": src.get("sistema"),
                "system": src.get("sistema"),
                "last_movement_date": lm,
                "source": "cnj_datajud",
                "source_id": "cnj_datajud",
                "datajud_alias": alias,
                "raw_record_id": fname,
                "discovery_id": item.get("id"),
                "discovered_by_source": item.get("discovered_by_source"),
                "discovered_by_entity_id": item.get("discovered_by_entity_id"),
                "discovery_type": item.get("discovery_type"),
                "discovery_blurb": discovery_provenance_blurb(item),
                "seed_source_id": item.get("discovered_by_source"),
                "seed_entity_id": item.get("discovered_by_entity_id"),
                "retrieved_at": now,
                "raw_sha1": sha1_bytes(json.dumps(src, sort_keys=True, default=str).encode()),
                "parties_note": "Portaria 374/2026: polos públicos quando PJ; não assumir PF.",
            }
        )

        for i, a in enumerate(assuntos):
            if not isinstance(a, dict):
                continue
            subjects.append(
                {
                    "id": f"subj_{digits}_{a.get('codigo')}_{i}",
                    "case_id": case_id,
                    "subject_code": a.get("codigo"),
                    "subject_name": a.get("nome"),
                    "is_primary": i == 0,
                    "source_id": "cnj_datajud",
                    "raw_record_id": fname,
                }
            )

        for i, mov in enumerate(src.get("movimentos") or []):
            if not isinstance(mov, dict):
                continue
            code = mov.get("codigo")
            desc = mov.get("nome")
            mdate = mov.get("dataHora")
            mid = f"mov_{digits}_{code}_{i}_{str(mdate or '')[:10]}"
            movements.append(
                {
                    "movement_id": mid,
                    "case_id": case_id,
                    "movement_code": code,
                    "movement_name": desc,
                    "movement_description": desc,
                    "movement_date": mdate,
                    "movement_timestamp": mdate,
                    "complement": mov.get("complementos"),
                    "sequence": i,
                    "source_id": "cnj_datajud",
                    "raw_record_id": fname,
                    "retrieved_at": now,
                }
            )

        known_updates.append(
            {
                "process_number_normalized": digits,
                "case_id": case_id,
                "court_alias": alias.replace("api_publica_", ""),
                "last_movement_at": lm,
                "last_checked_at": now,
                "last_successful_enrich_at": now,
                "active": True,
                "anchor_entity_id": item.get("discovered_by_entity_id"),
                "skipped": False,
            }
        )
        ok += 1
        print(f"  OK {npu} type={item.get('discovery_type')} movs={len(src.get('movimentos') or [])}", flush=True)

    write_jsonl(out / "legal_cases_extract.jsonl", cases)
    write_jsonl(out / "case_movements_extract.jsonl", movements)
    write_jsonl(out / "legal_case_subjects_extract.jsonl", subjects)
    write_jsonl(out / "known_cases_updates.jsonl", known_updates)
    if quarantine:
        # rewrite with UNKNOWN_COURT adds
        write_jsonl(out / "quarantine.jsonl", [q for q in quarantine if q])
    if errors:
        write_jsonl(out / "errors.jsonl", errors)

    write_json(
        out / "datajud_meta.json",
        {
            **meta,
            "ok": ok,
            "errors": len(errors),
            "discoveries": len(decided),
            "ingest_candidates": len(to_ingest),
            "skipped_unchanged": skipped_unchanged,
            "ignored": len(ignored),
        },
    )
    write_manifest(
        out,
        "cnj_datajud",
        [
            {"file": "case_discovery.jsonl", "rows": len(decided)},
            {"file": "legal_cases_extract.jsonl", "rows": len(cases)},
            {"file": "case_movements_extract.jsonl", "rows": len(movements)},
        ],
        extra=meta,
    )
    mark_ingested(
        "cnj_datajud",
        run_id=run["ingestion_run_id"],
        counts={
            "cases": len(cases),
            "movements": len(movements),
            "subjects": len(subjects),
            "skipped_unchanged": skipped_unchanged,
            "errors": len(errors),
        },
        ok=True,
        dataset_id="cnj.datajud.enrich",
    )
    append_event("document.discovered", {"source": "cnj_datajud", "cases": len(cases)})
    print(
        f"OK DataJud scoped: cases={len(cases)} movs={len(movements)} "
        f"skip_unchanged={skipped_unchanged} ignored={len(ignored)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
