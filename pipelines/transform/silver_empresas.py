#!/usr/bin/env python3
"""Silver empresas a partir de CNPJs do PNCP (+ manifesto RFB se houver)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_jsonl  # noqa: E402


def only_digits(s: str | None) -> str | None:
    if not s:
        return None
    d = re.sub(r"\D", "", str(s))
    return d if len(d) >= 8 else None


def main() -> int:
    contratos_path = LAKE / "silver" / "contratos" / "contratos_latest.jsonl"
    by_cnpj: dict[str, dict] = {}
    if contratos_path.exists():
        for line in contratos_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cnpj = only_digits(row.get("cnpj"))
            if not cnpj:
                continue
            cur = by_cnpj.get(cnpj) or {
                "id_externo": f"cnpj:{cnpj}",
                "cnpj": cnpj,
                "fonte": "pncp",
                "nome": f"CNPJ {cnpj}",
                "contratos": 0,
                "valor_total": 0.0,
                "fetched_at": utc_now(),
            }
            cur["contratos"] += 1
            v = row.get("valor") or 0
            try:
                cur["valor_total"] = round(float(cur["valor_total"]) + float(v), 2)
            except Exception:
                pass
            orgao = row.get("orgao")
            if isinstance(orgao, str) and orgao and cur["nome"].startswith("CNPJ"):
                # orgao é contratante; mantém nome genérico do fornecedor
                pass
            by_cnpj[cnpj] = cur

    # nota RFB se houver README bronze
    rfb_note = None
    bronze = LAKE / "bronze" / "rfb_cnpj"
    if bronze.exists():
        for p in sorted(bronze.rglob("README.json"), reverse=True):
            try:
                rfb_note = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
            break

    rows = list(by_cnpj.values())
    for r in rows:
        r["rfb_status"] = "pending_dump" if not rfb_note else "manifest_only"
        if rfb_note:
            r["rfb_canonical"] = rfb_note.get("canonical_index")

    outdir = LAKE / "silver" / "empresas"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    write_jsonl(outdir / f"empresas_{stamp}.jsonl", rows)
    write_jsonl(outdir / "empresas_latest.jsonl", rows)
    print(f"OK silver empresas: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
