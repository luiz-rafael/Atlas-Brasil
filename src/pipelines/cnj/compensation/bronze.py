"""RAW → VALIDATE → BRONZE (linhas por pessoa ainda não resolvidas)."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, write_json, write_jsonl  # noqa: E402
from src.connectors.cnj.compensation.courts import SOURCE_ID  # noqa: E402
from src.pipelines.cnj.compensation.parsers.cnj_portaria_63 import (  # noqa: E402
    parse_rubrica_row,
)
from src.pipelines.cnj.compensation.parsers.detect import read_tabular  # noqa: E402
from src.pipelines.cnj.compensation.parsers.generic import parse_generic_sheet  # noqa: E402
from src.pipelines.cnj.compensation.parsers.totals import is_total_row  # noqa: E402
from src.models.compensation.names import slug_header  # noqa: E402
from src.pipelines.cnj.compensation.quarantine import make_quarantine  # noqa: E402

_MAGISTRATE_HINTS = (
    "juiz",
    "desembargador",
    "ministro",
    "magistrad",
    "conselheiro",
)
_NOT_MAGISTRATE = (
    "servidor",
    "tecnico",
    "analista",
    "estagi",
    "colaborador",
    "terceiriz",
    "oficial_de_justica",
    "oficial_justica",
)


def is_magistrate_row(row: dict[str, Any], *, layout_id: str | None = None) -> bool:
    """Anexo VIII mistura folha inteira; só entra magistrado identificado."""
    cargo = slug_header(str(row.get("position") or row.get("cargo") or ""))
    extra = slug_header(
        " ".join(
            str(row.get(k) or "")
            for k in ("categoria", "vinculo", "tipo", "situacao")
        )
    )
    blob = f"{cargo} {extra}".strip()
    if any(h in blob for h in _MAGISTRATE_HINTS):
        return True
    if "membro" in blob and not any(n in blob for n in _NOT_MAGISTRATE):
        return True
    if any(n in blob for n in _NOT_MAGISTRATE):
        return False
    if layout_id == "cnj_portaria_63":
        return True
    return False


def bronze_dir(run_id: str) -> Path:
    return LAKE / "bronze" / SOURCE_ID / run_id


def _merge_person_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base = dict(rows[0])
    components: list[dict] = []
    for row in rows:
        components.extend(row.get("components") or [])
        for key in (
            "base_subsidy",
            "personal_advantages",
            "eventual_advantages",
            "indemnities",
            "retroactive_payments",
            "other_components",
            "gross_total",
            "discounts",
            "net_total",
            "position",
            "display_name",
            "source_person_identifier",
        ):
            if base.get(key) in (None, "") and row.get(key) not in (None, ""):
                base[key] = row[key]
    # dedup componentes por code+name
    seen: set[tuple] = set()
    uniq: list[dict] = []
    for c in components:
        k = (c.get("component_code"), c.get("component_name"), c.get("amount"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    base["components"] = uniq
    return base


def parse_saved_file(item: dict[str, Any]) -> dict[str, Any]:
    rel = item.get("file_path")
    if not rel:
        return {
            "rows": [],
            "quarantine": [
                make_quarantine(
                    "EMPTY_FILE",
                    payload={"item": item},
                    raw_record_id=item.get("raw_record_id"),
                )
            ],
            "layouts": [],
        }
    path = LAKE / rel if not Path(rel).is_absolute() else Path(rel)
    if not path.is_file():
        return {
            "rows": [],
            "quarantine": [
                make_quarantine(
                    "EMPTY_FILE",
                    payload={"missing": str(path)},
                    raw_record_id=item.get("raw_record_id"),
                )
            ],
            "layouts": [],
        }
    if path.stat().st_size == 0:
        return {
            "rows": [],
            "quarantine": [
                make_quarantine(
                    "EMPTY_FILE",
                    payload={"file": str(path)},
                    raw_record_id=item.get("raw_record_id"),
                )
            ],
            "layouts": [],
        }

    parsed = read_tabular(path)
    q: list[dict] = []
    if not parsed.get("ok"):
        reason = parsed.get("reason") or "UNSUPPORTED_FORMAT"
        q.append(
            make_quarantine(
                reason,
                payload={"file": str(path), "error": parsed.get("error")},
                raw_record_id=item.get("raw_record_id"),
            )
        )
        return {"rows": [], "quarantine": q, "layouts": []}
    if parsed.get("empty"):
        q.append(
            make_quarantine(
                "EMPTY_FILE",
                payload={"file": str(path)},
                raw_record_id=item.get("raw_record_id"),
            )
        )
        return {"rows": [], "quarantine": q, "layouts": []}

    court_id = item.get("court_id")
    year = item.get("reference_year")
    month = item.get("reference_month")
    raw_id = item.get("raw_record_id")
    rows: list[dict] = []
    layouts: list[dict] = []

    for sheet in parsed["sheets"]:
        layout = sheet["layout"]
        layouts.append(
            {
                "file": item.get("filename"),
                "sheet": sheet["name"],
                **layout,
                "court_id": court_id,
            }
        )
        records = sheet["records"]
        if layout.get("confidence") == "none" and records:
            q.append(
                make_quarantine(
                    "SCHEMA_CHANGED",
                    payload={
                        "file": item.get("filename"),
                        "sheet": sheet["name"],
                        "headers": sheet.get("headers"),
                        "fingerprint": layout.get("fingerprint"),
                    },
                    raw_record_id=raw_id,
                    entity_hint=court_id,
                )
            )
            # ainda tenta genérico se houver nome
        kind = layout.get("sheet_kind")
        layout_id = layout.get("layout_id") or "generic_tabular"

        total_skipped = 0
        kept_records = []
        for rec in records:
            if is_total_row(rec):
                total_skipped += 1
                continue
            kept_records.append(rec)
        if total_skipped:
            q.append(
                make_quarantine(
                    "TOTAL_ROW",
                    payload={
                        "file": item.get("filename"),
                        "sheet": sheet["name"],
                        "count": total_skipped,
                    },
                    raw_record_id=raw_id,
                )
            )

        if kind in {"personal_advantages", "indemnities", "eventual_advantages"}:
            for rec in kept_records:
                parsed_row = parse_rubrica_row(
                    rec,
                    category=kind,
                    court_id=court_id,
                    year=year,
                    month=month,
                    raw_record_id=raw_id,
                    layout_id=layout_id,
                )
                if parsed_row:
                    if not is_magistrate_row(parsed_row, layout_id=layout_id) and not is_magistrate_row(rec, layout_id=layout_id):
                        continue
                    parsed_row["original_file_url"] = item.get("original_source_url") or item.get("url")
                    parsed_row["original_file_source"] = item.get("origin")
                    parsed_row["filename"] = item.get("filename")
                    rows.append(parsed_row)
        else:
            extra = parse_generic_sheet(
                kept_records,
                layout,
                court_id=court_id,
                year=year,
                month=month,
                raw_record_id=raw_id,
            )
            for parsed_row in extra:
                if not is_magistrate_row(parsed_row, layout_id=layout_id):
                    continue
                parsed_row["original_file_url"] = item.get("original_source_url") or item.get("url")
                parsed_row["original_file_source"] = item.get("origin")
                parsed_row["filename"] = item.get("filename")
                rows.append(parsed_row)

    merged_map: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        merged_map[row["row_key"]].append(row)
    merged = [_merge_person_rows(group) for group in merged_map.values()]
    return {"rows": merged, "quarantine": q, "layouts": layouts}


def build_bronze(download_result: dict, *, run_id: str) -> dict[str, Any]:
    all_rows: list[dict] = []
    quarantine: list[dict] = []
    layouts: list[dict] = []
    items = [i for i in (download_result.get("saved") or []) if not str(i.get("filename") or "").lower().endswith(".zip")]
    total = len(items)
    for idx, item in enumerate(items, 1):
        print(
            f"bronze {idx}/{total} {item.get('court_id')} {item.get('filename')} "
            f"{item.get('reference_year')}-{item.get('reference_month')}",
            flush=True,
        )
        try:
            parsed = parse_saved_file(item)
        except Exception as exc:
            print(f"  FAIL {item.get('filename')}: {exc}", flush=True)
            quarantine.append(
                make_quarantine(
                    "UNSUPPORTED_FORMAT",
                    payload={"filename": item.get("filename"), "error": str(exc)},
                    entity_hint=item.get("court_id"),
                    raw_record_id=item.get("raw_record_id"),
                )
            )
            continue
        all_rows.extend(parsed["rows"])
        quarantine.extend(parsed["quarantine"])
        layouts.extend(parsed["layouts"])
    for err in download_result.get("errors") or []:
        quarantine.append(
            make_quarantine(
                "UNSUPPORTED_FORMAT",
                payload=err,
                entity_hint=err.get("court_id"),
            )
        )

    out = bronze_dir(run_id)
    write_jsonl(out / "bronze_rows.jsonl", all_rows)
    write_jsonl(out / "quarantine.jsonl", quarantine)
    write_json(
        out / "bronze_meta.json",
        {
            "run_id": run_id,
            "rows": len(all_rows),
            "quarantine": len(quarantine),
            "layouts": layouts,
        },
    )
    return {
        "run_id": run_id,
        "rows": all_rows,
        "quarantine": quarantine,
        "layouts": layouts,
        "counts": {"rows": len(all_rows), "quarantine": len(quarantine), "files": len(download_result.get("saved") or [])},
    }
