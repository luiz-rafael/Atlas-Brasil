#!/usr/bin/env python3
"""
Plug de descobertas reais DataJud.

Varre bronze STF/CGU (e refetch leve opcional), extrai NPUs CNJ e append
em data/lake/queues/datajud_discovery.jsonl via make_discovery.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from pipelines.common import day_stamp, utc_now, write_json, write_manifest  # noqa: E402
from pipelines.legal.discovery import make_discovery  # noqa: E402
from pipelines.legal.extract_npu import extract_npus, strip_html  # noqa: E402
from pipelines.legal.npu import digits_only, infer_alias  # noqa: E402

LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))
QUEUE = LAKE / "queues" / "datajud_discovery.jsonl"
GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
STF_BRONZE = LAKE / "bronze" / "stf"
CGU_LEGAL = LAKE / "bronze" / "cgu_legal"
CGU_PORTAL = LAKE / "bronze" / "cgu_portal"

OPS_LIST_URL = (
    "https://www.gov.br/cgu/pt-br/assuntos/auditoria-e-fiscalizacao/"
    "operacoes-especiais/operacoes-especiais"
)


def _norm(s: str | None) -> str:
    s = (s or "").upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def only_digits(s: str | None) -> str | None:
    if not s:
        return None
    d = re.sub(r"\D", "", str(s))
    return d if len(d) >= 8 else None


def load_kb() -> tuple[set[str], dict[str, list[str]], dict[str, str]]:
    """cnpjs KB, nome_norm -> [person_ids], cnpj -> empresa_id (só IDs reais)."""
    cnpjs: set[str] = set()
    names: dict[str, list[str]] = {}
    emp_by_cnpj: dict[str, str] = {}
    if not GOLD.exists():
        return cnpjs, names, emp_by_cnpj
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    for e in kb.get("entidades") or []:
        if e.get("tipo") == "empresa":
            c = only_digits(e.get("cnpj"))
            if c and len(c) >= 14:
                c14 = c.zfill(14)[-14:]
                cnpjs.add(c14)
                emp_by_cnpj[c14] = e["id"]
        if e.get("tipo") == "pessoa" and str(e.get("id", "")).startswith(("p_cam_", "p_sen_")):
            for n in [e.get("nome"), *(e.get("aliases") or [])]:
                nn = _norm(n)
                if len(nn) > 8:
                    names.setdefault(nn, []).append(e["id"])
    return cnpjs, names, emp_by_cnpj


def match_entity(
    text: str,
    cnpjs: set[str],
    names: dict[str, list[str]],
    emp_by_cnpj: dict[str, str],
) -> tuple[str | None, str | None]:
    """
    Match confiável no mesmo documento.
    Retorna (entity_id, kind) onde kind é 'COMPANY' | 'PERSON' | None.
    Não inventa entity_id.
    """
    digits = re.sub(r"\D", "", text or "")
    for c in cnpjs:
        if c in digits:
            eid = emp_by_cnpj.get(c)
            if eid:
                return eid, "COMPANY"
    blob_n = _norm(strip_html(text) if text else "")
    for n, ids in names.items():
        if n in blob_n:
            uniq = list(dict.fromkeys(ids))
            if len(uniq) == 1 and uniq[0].startswith(("p_cam_", "p_sen_")):
                return uniq[0], "PERSON"
    return None, None


def load_queue_digits(path: Path = QUEUE) -> set[str]:
    seen: set[str] = set()
    if not path.is_file():
        return seen
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = row.get("process_number_normalized") or digits_only(
            row.get("process_number") or ""
        )
        if len(d) == 20:
            seen.add(d)
    return seen


def append_discoveries(records: list[dict], path: Path = QUEUE) -> int:
    """Append dedupe por process_number_normalized. Retorna quantos novos."""
    if not records:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_queue_digits(path)
    written = 0
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            d = rec.get("process_number_normalized") or ""
            if len(d) != 20 or d in existing:
                continue
            existing.add(d)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
    return written


def resolve_discovery_type(
    source: str,
    entity_kind: str | None,
) -> str:
    """STF/notícias → OFFICIAL_REFERENCE; só CNPJ âncora → COMPANY_CONTEXT."""
    if entity_kind == "COMPANY" and source in ("cgu_portal", "cgu_legal"):
        return "COMPANY_CONTEXT"
    return "OFFICIAL_REFERENCE"


def discoveries_from_text(
    text: str,
    *,
    discovered_by_source: str,
    discovery_reference: str | None,
    cnpjs: set[str] | None = None,
    names: dict[str, list[str]] | None = None,
    emp_by_cnpj: dict[str, str] | None = None,
    discovered_at: str | None = None,
) -> list[dict]:
    npus = extract_npus(text or "")
    if not npus:
        return []
    entity_id = None
    entity_kind = None
    if cnpjs is not None and names is not None and emp_by_cnpj is not None:
        entity_id, entity_kind = match_entity(text, cnpjs, names, emp_by_cnpj)
    dtype = resolve_discovery_type(discovered_by_source, entity_kind)
    now = discovered_at or utc_now()
    out: list[dict] = []
    for npu in npus:
        disc = make_discovery(
            npu,
            discovered_by_source=discovered_by_source,
            discovery_type=dtype,
            discovered_by_entity_id=entity_id,
            discovery_reference=discovery_reference,
            discovered_at=now,
        )
        alias = infer_alias(npu)
        if alias:
            disc["tribunal_alias"] = alias
        out.append(disc)
    return out


def append_text_discoveries(
    text: str,
    *,
    source: str,
    url: str | None,
    cnpjs: set[str] | None = None,
    names: dict[str, list[str]] | None = None,
    emp_by_cnpj: dict[str, str] | None = None,
) -> int:
    """Helper fail-soft para hooks de ingest. Retorna novos escritos."""
    if cnpjs is None or names is None or emp_by_cnpj is None:
        cnpjs, names, emp_by_cnpj = load_kb()
    recs = discoveries_from_text(
        text,
        discovered_by_source=source,
        discovery_reference=url,
        cnpjs=cnpjs,
        names=names,
        emp_by_cnpj=emp_by_cnpj,
    )
    return append_discoveries(recs)


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _text_from_json_obj(obj: object) -> str:
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


def _emit_unit(
    text: str,
    *,
    source: str,
    ref: str,
    cnpjs: set[str],
    names: dict[str, list[str]],
    emp_by_cnpj: dict[str, str],
    stats: dict,
    found: list[dict],
) -> None:
    if not (text or "").strip():
        return
    recs = discoveries_from_text(
        text,
        discovered_by_source=source,
        discovery_reference=ref,
        cnpjs=cnpjs,
        names=names,
        emp_by_cnpj=emp_by_cnpj,
    )
    if recs:
        stats["npus_found"] = stats.get("npus_found", 0) + len(recs)
        found.extend(recs)


def scan_path_files(
    root: Path,
    *,
    source: str,
    cnpjs: set[str],
    names: dict[str, list[str]],
    emp_by_cnpj: dict[str, str],
    stats: dict,
) -> list[dict]:
    """Scan *.html / *.json / *.jsonl sob root (match entidade por registro)."""
    found: list[dict] = []
    if not root.exists():
        return found
    patterns = ("**/*.html", "**/*.json", "**/*.jsonl")
    files: list[Path] = []
    for pat in patterns:
        files.extend(root.glob(pat))
    for path in sorted(set(files)):
        if path.name in ("manifest.json",):
            continue
        stats["files_scanned"] = stats.get("files_scanned", 0) + 1
        file_ref = str(path.relative_to(LAKE)).replace("\\", "/")
        suffix = path.suffix.lower()
        if suffix == ".html":
            text = _read_text_file(path)
            url = None
            sib = path.with_suffix(".json")
            if sib.is_file():
                try:
                    meta = json.loads(sib.read_text(encoding="utf-8"))
                    url = meta.get("url") or meta.get("source_url")
                except (json.JSONDecodeError, OSError):
                    pass
            _emit_unit(
                text,
                source=source,
                ref=url or file_ref,
                cnpjs=cnpjs,
                names=names,
                emp_by_cnpj=emp_by_cnpj,
                stats=stats,
                found=found,
            )
            continue
        if suffix == ".jsonl":
            for line in _read_text_file(path).splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    _emit_unit(
                        line,
                        source=source,
                        ref=file_ref,
                        cnpjs=cnpjs,
                        names=names,
                        emp_by_cnpj=emp_by_cnpj,
                        stats=stats,
                        found=found,
                    )
                    continue
                ref = (
                    (row.get("url") if isinstance(row, dict) else None)
                    or (row.get("source_url") if isinstance(row, dict) else None)
                    or file_ref
                )
                _emit_unit(
                    _text_from_json_obj(row),
                    source=source,
                    ref=ref,
                    cnpjs=cnpjs,
                    names=names,
                    emp_by_cnpj=emp_by_cnpj,
                    stats=stats,
                    found=found,
                )
            continue
        # .json
        raw = _read_text_file(path)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            _emit_unit(
                raw,
                source=source,
                ref=file_ref,
                cnpjs=cnpjs,
                names=names,
                emp_by_cnpj=emp_by_cnpj,
                stats=stats,
                found=found,
            )
            continue
        if isinstance(obj, list):
            for row in obj:
                ref = file_ref
                if isinstance(row, dict):
                    ref = row.get("url") or row.get("source_url") or file_ref
                _emit_unit(
                    _text_from_json_obj(row),
                    source=source,
                    ref=ref,
                    cnpjs=cnpjs,
                    names=names,
                    emp_by_cnpj=emp_by_cnpj,
                    stats=stats,
                    found=found,
                )
        elif isinstance(obj, dict):
            url = obj.get("url") or obj.get("source_url")
            text = ""
            hp = obj.get("html_path")
            if hp:
                html_p = LAKE / str(hp).replace("\\", "/")
                if not html_p.is_file():
                    html_p = path.with_suffix(".html")
                if html_p.is_file():
                    text = _read_text_file(html_p)
            if not text:
                text = _text_from_json_obj(obj)
            _emit_unit(
                text,
                source=source,
                ref=url or file_ref,
                cnpjs=cnpjs,
                names=names,
                emp_by_cnpj=emp_by_cnpj,
                stats=stats,
                found=found,
            )
        else:
            _emit_unit(
                _text_from_json_obj(obj),
                source=source,
                ref=file_ref,
                cnpjs=cnpjs,
                names=names,
                emp_by_cnpj=emp_by_cnpj,
                stats=stats,
                found=found,
            )
    return found


def refetch_stf(max_pages: int, stats: dict) -> list[dict]:
    from pipelines.ingest.stf import SEEDS, extract_links, fetch

    cnpjs, names, emp_by_cnpj = load_kb()
    out: list[dict] = []
    seen: set[str] = set()
    pages = 0
    for seed in SEEDS:
        if pages >= max_pages:
            break
        html = fetch(seed)
        if not html:
            continue
        links = extract_links(html, seed) or [seed]
        for url in links:
            if pages >= max_pages:
                break
            if url in seen:
                continue
            seen.add(url)
            body = fetch(url)
            pages += 1
            stats["refetch_pages"] = stats.get("refetch_pages", 0) + 1
            if not body:
                continue
            # persiste leve no bronze stf (mesma convenção do ingest)
            try:
                import hashlib
                from datetime import datetime, timezone

                slug = hashlib.sha1(url.encode()).hexdigest()[:16]
                doc_id = f"stf_{slug}"
                STF_BRONZE.mkdir(parents=True, exist_ok=True)
                path = STF_BRONZE / f"{doc_id}.json"
                path.with_suffix(".html").write_text(body, encoding="utf-8", errors="ignore")
                rec = {
                    "id": doc_id,
                    "fonte": "STF",
                    "orgao": "STF",
                    "nivel_fonte": "1_primaria",
                    "tipo": "noticia_oficial",
                    "titulo": "",
                    "url": url,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "html_bytes": len(body),
                    "html_path": str(path.with_suffix(".html").relative_to(LAKE)),
                    "via": "datajud_discovery_plug",
                }
                path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"stf save soft-fail: {e}", file=sys.stderr)
            recs = discoveries_from_text(
                body,
                discovered_by_source="stf",
                discovery_reference=url,
                cnpjs=cnpjs,
                names=names,
                emp_by_cnpj=emp_by_cnpj,
            )
            out.extend(recs)
            time.sleep(0.05)
    return out


def refetch_cgu_ops(max_pages: int, stats: dict) -> list[dict]:
    """Refetch páginas listadas em operacoes_raw.json (notícias prioritárias)."""
    import httpx

    from pipelines.common import UA

    cnpjs, names, emp_by_cnpj = load_kb()
    urls: list[str] = []
    for day_dir in sorted(CGU_LEGAL.glob("*"), reverse=True):
        op_path = day_dir / "operacoes_raw.json"
        if not op_path.is_file():
            continue
        try:
            ops = json.loads(op_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(ops, list):
            continue
        # notícias primeiro
        news = [o for o in ops if isinstance(o, dict) and o.get("kind") == "noticia"]
        rest = [o for o in ops if isinstance(o, dict) and o.get("kind") != "noticia"]
        for o in news + rest:
            u = o.get("url")
            if u and u != OPS_LIST_URL and u not in urls:
                urls.append(u)
        break  # só o run mais recente

    out: list[dict] = []
    for url in urls[:max_pages]:
        try:
            r = httpx.get(
                url,
                timeout=45.0,
                follow_redirects=True,
                headers={"User-Agent": UA},
            )
            stats["refetch_pages"] = stats.get("refetch_pages", 0) + 1
            if r.status_code != 200:
                continue
            body = r.text
            recs = discoveries_from_text(
                body,
                discovered_by_source="cgu_legal",
                discovery_reference=url,
                cnpjs=cnpjs,
                names=names,
                emp_by_cnpj=emp_by_cnpj,
            )
            out.extend(recs)
            time.sleep(0.08)
        except Exception as e:
            print(f"cgu refetch fail {url}: {e}", file=sys.stderr)
    return out


def main() -> int:
    max_pages = int(os.getenv("ATLAS_DISCOVERY_MAX_PAGES", "30"))
    do_refetch = os.getenv("ATLAS_DISCOVERY_REFETCH", "1").strip() not in ("0", "false", "no")
    cnpjs, names, emp_by_cnpj = load_kb()
    stats: dict = {
        "files_scanned": 0,
        "npus_found": 0,
        "refetch_pages": 0,
        "kb_cnpjs": len(cnpjs),
        "kb_names": len(names),
    }
    all_recs: list[dict] = []

    print("scan bronze/stf …", flush=True)
    all_recs.extend(
        scan_path_files(
            STF_BRONZE,
            source="stf",
            cnpjs=cnpjs,
            names=names,
            emp_by_cnpj=emp_by_cnpj,
            stats=stats,
        )
    )
    print("scan bronze/cgu_legal …", flush=True)
    all_recs.extend(
        scan_path_files(
            CGU_LEGAL,
            source="cgu_legal",
            cnpjs=cnpjs,
            names=names,
            emp_by_cnpj=emp_by_cnpj,
            stats=stats,
        )
    )
    print("scan bronze/cgu_portal …", flush=True)
    all_recs.extend(
        scan_path_files(
            CGU_PORTAL,
            source="cgu_portal",
            cnpjs=cnpjs,
            names=names,
            emp_by_cnpj=emp_by_cnpj,
            stats=stats,
        )
    )

    if do_refetch and max_pages > 0:
        # divide cota: metade STF, metade CGU ops
        stf_budget = max(1, max_pages // 2)
        cgu_budget = max(1, max_pages - stf_budget)
        print(f"refetch STF (max {stf_budget}) …", flush=True)
        all_recs.extend(refetch_stf(stf_budget, stats))
        print(f"refetch CGU ops (max {cgu_budget}) …", flush=True)
        all_recs.extend(refetch_cgu_ops(cgu_budget, stats))

    # dedupe in-memory (prefer OFFICIAL_REFERENCE + entity)
    priority = {"OFFICIAL_REFERENCE": 0, "COMPANY_CONTEXT": 1, "PERSON_CONTEXT": 2}
    best: dict[str, dict] = {}
    for r in all_recs:
        d = r.get("process_number_normalized") or ""
        if len(d) != 20:
            continue
        prev = best.get(d)
        if not prev:
            best[d] = r
            continue
        p_new = priority.get(r.get("discovery_type"), 9)
        p_old = priority.get(prev.get("discovery_type"), 9)
        if p_new < p_old:
            best[d] = r
        elif p_new == p_old and r.get("discovered_by_entity_id") and not prev.get(
            "discovered_by_entity_id"
        ):
            best[d] = r

    unique = list(best.values())
    written = append_discoveries(unique)
    queue_total = len(load_queue_digits())

    out = LAKE / "bronze" / "datajud_discovery_plug" / day_stamp()
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "fetched_at": utc_now(),
        "files_scanned": stats["files_scanned"],
        "npus_extracted_raw": stats.get("npus_found", 0) + sum(
            1 for _ in unique
        ),  # corrected below
        "unique_npus": len(unique),
        "written_new": written,
        "queue_total": queue_total,
        "refetch_pages": stats.get("refetch_pages", 0),
        "refetch_enabled": do_refetch,
        "max_pages": max_pages,
        "kb_cnpjs": stats["kb_cnpjs"],
        "kb_names": stats["kb_names"],
        "by_source": {},
    }
    # recount extracted during scan
    meta["npus_extracted_raw"] = len(all_recs)
    by_src: dict[str, int] = {}
    for r in unique:
        s = str(r.get("discovered_by_source") or "?")
        by_src[s] = by_src.get(s, 0) + 1
    meta["by_source"] = by_src

    write_json(out / "discoveries_batch.json", {"items": unique, "meta": meta})
    write_json(out / "meta.json", meta)
    write_manifest(
        out,
        "datajud_discovery_plug",
        [
            {"file": "discoveries_batch.json", "count": len(unique)},
            {"file": "meta.json", "count": 1},
        ],
        extra=meta,
    )

    print(
        f"OK plug datajud_discovery: unique={len(unique)} written_new={written} "
        f"queue_total={queue_total} scanned={stats['files_scanned']} "
        f"refetch_pages={stats.get('refetch_pages', 0)} by_source={by_src}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
