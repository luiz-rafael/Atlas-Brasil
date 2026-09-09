#!/usr/bin/env python3
"""
Silver DataJud (escopo Atlas):
  LEGAL_CASE, CASE_SUBJECT, CASE_MOVEMENT (append-only),
  CASE_STATUS (SCD2 current), CASE_DISCOVERY, known_legal_cases, quarantine.

Não promove culpa. Assunto ≠ conduta da pessoa.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.legal.case_status import derive_status  # noqa: E402
from pipelines.legal.tpu_rules import classify_movement  # noqa: E402


def latest_bronze() -> Path | None:
    base = LAKE / "bronze" / "cnj_datajud"
    if not base.exists():
        return None
    days = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
    for d in days:
        if (d / "legal_cases_extract.jsonl").exists() or (d / "case_discovery.jsonl").exists():
            return d
    return days[0] if days else None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def merge_by_id(existing: list[dict], new: list[dict], key: str) -> list[dict]:
    m = {str(r.get(key)): r for r in existing if r.get(key)}
    for r in new:
        kid = str(r.get(key) or "")
        if not kid:
            continue
        if kid in m and key == "movement_id":
            prev = m[kid]
            merged = {**prev, **r}
            merged["first_retrieved_at"] = prev.get("first_retrieved_at") or prev.get("retrieved_at")
            m[kid] = merged
        elif kid in m and key == "case_id":
            prev = m[kid]
            m[kid] = {**prev, **r, "first_seen_at": prev.get("first_seen_at") or prev.get("retrieved_at")}
        else:
            m[kid] = r
    return list(m.values())


def merge_known(existing: list[dict], updates: list[dict]) -> list[dict]:
    m = {str(r.get("process_number_normalized")): r for r in existing if r.get("process_number_normalized")}
    for u in updates:
        d = str(u.get("process_number_normalized") or "")
        if not d:
            continue
        if u.get("skipped") and d in m:
            prev = m[d]
            m[d] = {**prev, "last_checked_at": u.get("last_checked_at") or prev.get("last_checked_at")}
            continue
        prev = m.get(d) or {}
        m[d] = {**prev, **{k: v for k, v in u.items() if k != "skipped"}, "active": u.get("active", True)}
    return list(m.values())


def main() -> int:
    bronze = latest_bronze()
    if not bronze:
        print("SKIPPED silver_datajud: bronze ausente", flush=True)
        return 0

    sil = LAKE / "silver" / "legal"
    sil.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    stamp = day_stamp()

    discoveries = read_jsonl(bronze / "case_discovery.jsonl")
    cases_new = read_jsonl(bronze / "legal_cases_extract.jsonl")
    movs_new = read_jsonl(bronze / "case_movements_extract.jsonl")
    subj_new = read_jsonl(bronze / "legal_case_subjects_extract.jsonl")
    known_upd = read_jsonl(bronze / "known_cases_updates.jsonl")
    quar_new = read_jsonl(bronze / "quarantine.jsonl")

    if discoveries:
        write_jsonl(sil / f"case_discovery_{stamp}.jsonl", discoveries)
        write_jsonl(
            sil / "case_discovery_latest.jsonl",
            merge_by_id(read_jsonl(sil / "case_discovery_latest.jsonl"), discoveries, "id"),
        )

    if quar_new:
        write_jsonl(
            sil / "quarantine_latest.jsonl",
            merge_by_id(read_jsonl(sil / "quarantine_latest.jsonl"), quar_new, "quarantine_id"),
        )

    if not cases_new:
        # ainda assim persiste known checks / discovery
        if known_upd:
            known = merge_known(read_jsonl(sil / "known_legal_cases.jsonl"), known_upd)
            write_jsonl(sil / "known_legal_cases.jsonl", known)
        print("OK silver DataJud: sem cases novos (skip/gate/refresh unchanged)", flush=True)
        return 0

    cases = merge_by_id(read_jsonl(sil / "legal_cases_latest.jsonl"), cases_new, "case_id")
    movs = merge_by_id(read_jsonl(sil / "case_movements_latest.jsonl"), movs_new, "movement_id")
    subjects = merge_by_id(read_jsonl(sil / "legal_case_subjects_latest.jsonl"), subj_new, "id")

    # procedural classes dim
    classes = {str(c.get("procedural_class_code")): {
        "class_code": c.get("procedural_class_code"),
        "class_name": c.get("procedural_class_name") or c.get("procedural_class"),
        "taxonomy": "TPU",
        "source": "cnj_datajud",
    } for c in cases_new if c.get("procedural_class_code")}
    classes_all = merge_by_id(
        read_jsonl(sil / "procedural_classes_latest.jsonl"),
        list(classes.values()),
        "class_code",
    )

    # events + status
    events = []
    for mov in movs_new:
        clf = classify_movement(mov.get("movement_code"), mov.get("movement_description"))
        events.append(
            {
                "legal_event_id": f"le_{mov.get('movement_id')}",
                "case_id": mov.get("case_id"),
                "movement_id": mov.get("movement_id"),
                "event_type": clf["event_type"],
                "event_date": mov.get("movement_date"),
                "source_id": "cnj_datajud",
                "classification_method": clf["classification_method"],
                "confidence": clf["confidence"],
                "human_verified": False,
                "relation_type": clf.get("relation_type"),
                "notes": clf.get("notes"),
                "retrieved_at": now,
            }
        )
    events_all = merge_by_id(read_jsonl(sil / "legal_events_latest.jsonl"), events, "legal_event_id")

    movs_by_case: dict[str, list] = {}
    for m in movs:
        movs_by_case.setdefault(str(m.get("case_id")), []).append(m)

    status_out: list[dict] = []
    prev_status = read_jsonl(sil / "case_status_latest.jsonl")
    new_current = []
    for c in cases_new:
        cid = c.get("case_id")
        der = derive_status(movs_by_case.get(str(cid), []))
        new_current.append(
            {
                "case_status_id": f"cs_{cid}_{now[:19].replace(':', '')}",
                "case_id": cid,
                "status": der["status"],
                "status_source": der["status_source"],
                "derived_from_movement_id": der.get("derived_from_movement_id"),
                "valid_from": now,
                "valid_to": None,
                "is_current": True,
                "confidence": der.get("confidence"),
                "notes": der.get("notes"),
            }
        )
    touched = {s["case_id"] for s in new_current}
    for h in prev_status:
        if h.get("case_id") in touched and h.get("is_current"):
            status_out.append({**h, "is_current": False, "valid_to": now})
        else:
            status_out.append(h)
    status_out.extend(new_current)

    known = merge_known(read_jsonl(sil / "known_legal_cases.jsonl"), known_upd or [
        {
            "process_number_normalized": c.get("process_number_normalized"),
            "case_id": c.get("case_id"),
            "court_alias": (c.get("datajud_alias") or "").replace("api_publica_", ""),
            "last_movement_at": c.get("last_movement_date"),
            "last_checked_at": now,
            "last_successful_enrich_at": now,
            "active": True,
            "anchor_entity_id": c.get("discovered_by_entity_id"),
        }
        for c in cases_new
    ])

    write_jsonl(sil / f"legal_cases_{stamp}.jsonl", cases)
    write_jsonl(sil / "legal_cases_latest.jsonl", cases)
    write_jsonl(sil / f"case_movements_{stamp}.jsonl", movs)
    write_jsonl(sil / "case_movements_latest.jsonl", movs)
    write_jsonl(sil / "legal_case_subjects_latest.jsonl", subjects)
    write_jsonl(sil / "procedural_classes_latest.jsonl", classes_all)
    write_jsonl(sil / "legal_events_latest.jsonl", events_all)
    write_jsonl(sil / "case_status_latest.jsonl", status_out)
    write_jsonl(sil / "known_legal_cases.jsonl", known)
    write_json(
        sil / "meta_datajud.json",
        {
            "em": now,
            "cases": len(cases),
            "movements": len(movs),
            "subjects": len(subjects),
            "known": len(known),
            "status_current": len(new_current),
            "policy": "scoped_enrichment; append_only_movements; status_scd2; no auto guilt",
        },
    )
    print(
        f"OK silver DataJud: cases={len(cases)} movs={len(movs)} "
        f"subjects={len(subjects)} known={len(known)} status={len(new_current)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
