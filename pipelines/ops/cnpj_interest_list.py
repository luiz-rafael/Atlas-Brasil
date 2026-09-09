#!/usr/bin/env python3
"""
Monta fila de CNPJs de interesse do Atlas (escopo — não dump nacional).

Fontes:
  - data/atlas-brasil-kb-gold.json (+ active se existir) — entidades tipo empresa
  - bronze CGU sancoes_cnpj_kb.jsonl (mais recente)
  - bronze PNCP (niFornecedor / orgaoEntidade.cnpj)
  - bronze TSE prestação (colunas *CNPJ* com 14 dígitos), se presente

Saída:
  data/lake/queues/cnpj_interest.jsonl  → {cnpj, entity_id?, sources:[...]}
  data/lake/queues/cnpj_interest_summary.json
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json, write_jsonl  # noqa: E402

CNPJ_RE = re.compile(r"^\d{14}$")


def only_cnpj14(val) -> str | None:
    if val is None:
        return None
    d = re.sub(r"\D", "", str(val))
    if len(d) == 11:
        return None  # CPF
    if len(d) >= 14:
        d = d.zfill(14)[-14:]
    elif len(d) > 0:
        d = d.zfill(14)
    if not CNPJ_RE.match(d):
        return None
    if d == "0" * 14 or len(set(d)) == 1:
        return None
    # dígitos verificadores
    try:
        nums = [int(c) for c in d]
        w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        s1 = sum(n * w for n, w in zip(nums[:12], w1))
        r1 = s1 % 11
        d1 = 0 if r1 < 2 else 11 - r1
        if nums[12] != d1:
            return None
        w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        s2 = sum(n * w for n, w in zip(nums[:13], w2))
        r2 = s2 % 11
        d2 = 0 if r2 < 2 else 11 - r2
        if nums[13] != d2:
            return None
    except Exception:
        return None
    return d


def add(bucket: dict[str, dict], cnpj: str | None, source: str, entity_id: str | None = None) -> None:
    if not cnpj:
        return
    row = bucket.setdefault(cnpj, {"cnpj": cnpj, "sources": [], "entity_id": None})
    if source not in row["sources"]:
        row["sources"].append(source)
    if entity_id and not row.get("entity_id"):
        row["entity_id"] = entity_id


def from_gold_kb(bucket: dict[str, dict], path: Path, source: str) -> int:
    if not path.is_file():
        return 0
    n = 0
    kb = json.loads(path.read_text(encoding="utf-8"))
    for e in kb.get("entidades") or []:
        if e.get("tipo") != "empresa":
            continue
        cnpj = only_cnpj14(e.get("cnpj"))
        if not cnpj:
            # tenta id e_cnpj_*
            eid = str(e.get("id") or "")
            if eid.startswith("e_cnpj_"):
                cnpj = only_cnpj14(eid[7:])
        if not cnpj:
            continue
        add(bucket, cnpj, source, entity_id=e.get("id"))
        n += 1
    return n


def latest_bronze_day(fonte: str) -> Path | None:
    base = LAKE / "bronze" / fonte
    if not base.exists():
        return None
    days = [p for p in base.iterdir() if p.is_dir()]
    # prefer YYYY-MM-DD; senão run_id
    dated = [p for p in days if len(p.name) == 10 and p.name[4] == "-"]
    pool = dated or days
    return max(pool, key=lambda p: p.name) if pool else None


def from_cgu_sancoes(bucket: dict[str, dict]) -> int:
    n = 0
    base = LAKE / "bronze" / "cgu_portal"
    if not base.exists():
        return 0
    hits = list(base.rglob("sancoes_cnpj_kb*.jsonl"))
    if not hits:
        return 0
    # maior arquivo (o dia YYYY-MM-DD às vezes é stub; run_id tem o dump completo)
    path = max(hits, key=lambda p: p.stat().st_size)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cnpj = only_cnpj14(
            row.get("_atlas_cnpj")
            or (row.get("pessoa") or {}).get("cnpjFormatado")
            or (row.get("sancionado") or {}).get("codigoFormatado")
        )
        if cnpj:
            add(bucket, cnpj, "cgu_sancoes")
            n += 1
    return n


def from_pncp(bucket: dict[str, dict]) -> int:
    n = 0
    day = latest_bronze_day("pncp")
    if not day:
        return 0
    paths = list(day.glob("contratos*.jsonl"))
    if not paths:
        # run folders
        base = LAKE / "bronze" / "pncp"
        for p in sorted(base.rglob("contratos*.jsonl"), reverse=True)[:3]:
            paths.append(p)
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            rows = raw if isinstance(raw, list) else [raw]
            for row in rows:
                for key in ("niFornecedor",):
                    c = only_cnpj14(row.get(key))
                    if c:
                        add(bucket, c, "pncp")
                        n += 1
                org = row.get("orgaoEntidade") or {}
                c2 = only_cnpj14(org.get("cnpj"))
                if c2:
                    add(bucket, c2, "pncp_orgao")
                    n += 1
    return n


def from_tse_prestacao(bucket: dict[str, dict], max_files: int = 40) -> int:
    """Extrai CNPJs 14 dígitos de colunas *CNPJ* (fornecedor/doador PJ)."""
    base = LAKE / "bronze" / "tse_prestacao"
    if not base.exists():
        return 0
    day = latest_bronze_day("tse_prestacao")
    if not day:
        return 0
    csvs = sorted(day.rglob("*.csv"))[:max_files]
    n = 0
    want = (
        "NR_CPF_CNPJ_FORNECEDOR",
        "NR_CPF_CNPJ_DOADOR",
        "NR_CNPJ_PRESTADOR_CONTA",
        "NR_CPF_CNPJ_FORNECEDOR_RECEITA",
    )
    for path in csvs:
        try:
            with path.open("r", encoding="latin-1", newline="") as fh:
                reader = csv.DictReader(fh, delimiter=";")
                if not reader.fieldnames:
                    continue
                cols = [c for c in reader.fieldnames if c in want or ("CNPJ" in (c or "").upper())]
                if not cols:
                    continue
                for row in reader:
                    for c in cols:
                        cnpj = only_cnpj14(row.get(c))
                        if cnpj:
                            add(bucket, cnpj, "tse_prestacao")
                            n += 1
        except Exception:
            continue
    return n


def main() -> int:
    bucket: dict[str, dict] = {}
    counts = {
        "gold": from_gold_kb(bucket, ROOT / "data" / "atlas-brasil-kb-gold.json", "gold_kb"),
        "active": from_gold_kb(bucket, ROOT / "data" / "atlas-brasil-kb-active.json", "active_kb"),
        "cgu_sancoes": from_cgu_sancoes(bucket),
        "pncp": from_pncp(bucket),
        "tse_prestacao": from_tse_prestacao(bucket),
    }
    rows = sorted(
        bucket.values(),
        key=lambda r: (
            0 if "gold_kb" in (r.get("sources") or []) else 1,
            0 if "active_kb" in (r.get("sources") or []) else 1,
            0 if "pncp" in (r.get("sources") or []) else 1,
            0 if "cgu_sancoes" in (r.get("sources") or []) else 1,
            r["cnpj"],
        ),
    )
    out_dir = LAKE / "queues"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "cnpj_interest.jsonl", rows)
    summary = {
        "fetched_at": utc_now(),
        "unique_cnpjs": len(rows),
        "source_hit_counts": counts,
        "sources_distribution": defaultdict_count(rows),
    }
    write_json(out_dir / "cnpj_interest_summary.json", summary)
    print(
        f"OK cnpj_interest: unique={len(rows)} "
        f"gold={counts['gold']} cgu={counts['cgu_sancoes']} "
        f"pncp={counts['pncp']} tse={counts['tse_prestacao']}",
        flush=True,
    )
    return 0


def defaultdict_count(rows: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = defaultdict(int)
    for r in rows:
        for s in r.get("sources") or []:
            dist[s] += 1
    return dict(dist)


if __name__ == "__main__":
    raise SystemExit(main())
