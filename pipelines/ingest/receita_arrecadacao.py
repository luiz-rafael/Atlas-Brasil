#!/usr/bin/env python3
"""
Receita Federal — Arrecadação ( Contas do Brasil / início ).

Tenta baixar série histórica aberta da RFB. Se falhar, aceita ATLAS_ARRECADACAO_FILE
ou sai SKIPPED (exit 0).

Nota editorial: arrecadação RF ≠ toda receita pública brasileira.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    append_event,
    bronze_dir,
    http_get,
    sha1_bytes,
    utc_now,
    write_json,
    write_jsonl,
    write_manifest,
    write_raw_record,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

PORTAL = "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos"
SERIE_PAGE = (
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/"
    "receitadata/arrecadacao/serie-historica"
)
CANDIDATE_URLS = [
    (
        "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/"
        "receitadata/arrecadacao/serie-historica/"
        "arrecadacao-das-receitas-federais-1994-a-2025.xlsx/@@download/file"
    ),
    (
        "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/"
        "receitadata/arrecadacao/serie-historica/"
        "arrecadacao-das-receitas-federais-1994-a-2024.xlsx/@@download/file"
    ),
]

MONTHS = {
    "JAN": 1,
    "FEV": 2,
    "MAR": 3,
    "ABR": 4,
    "MAI": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "OUT": 10,
    "NOV": 11,
    "DEZ": 12,
}


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("$env:"):
            line = line[5:]
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _norm(s: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", s or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().upper()


def parse_xlsx(path: Path) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows_out: list[dict] = []
    for sheet_name in wb.sheetnames:
        if not str(sheet_name).isdigit():
            continue
        year = int(sheet_name)
        ws = wb[sheet_name]
        header_idx = None
        month_cols: dict[int, int] = {}
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            cells = list(row)
            labels = [_norm(str(c)) if c is not None else "" for c in cells]
            if header_idx is None:
                if any(x in MONTHS for x in labels):
                    header_idx = i
                    for j, lab in enumerate(labels):
                        if lab in MONTHS:
                            month_cols[j] = MONTHS[lab]
                continue
            label = labels[0] if labels else ""
            if not label:
                continue
            # TOTAL GERAL = arrecadação federal agregada
            if "TOTAL GERAL" not in label and label not in ("TOTAL", "TOTAL DA ARRECADACAO"):
                continue
            for col_i, month in month_cols.items():
                if col_i >= len(cells):
                    continue
                val = cells[col_i]
                if val is None or val == "":
                    continue
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    continue
                rows_out.append(
                    {
                        "ano": year,
                        "mes": month,
                        "uf": None,
                        "territory_id": "terr_br",
                        "territory_type": "BRASIL",
                        "rubrica": label,
                        "valor_milhoes": num,
                        "valor": num * 1_000_000.0,
                        "unidade_fonte": "R$ milhões",
                        "fonte": "receita_arrecadacao",
                        "nota": "Arrecadação federal RF — não cobre toda receita pública BR",
                    }
                )
    return rows_out


def try_download(out: Path) -> tuple[Path | None, dict]:
    env_file = os.getenv("ATLAS_ARRECADACAO_FILE", "").strip()
    if env_file:
        p = Path(env_file)
        if p.is_file():
            dest = out / p.name
            dest.write_bytes(p.read_bytes())
            return dest, {"via": "ATLAS_ARRECADACAO_FILE", "file": dest.name, "bytes": dest.stat().st_size}

    last_err = None
    for url in CANDIDATE_URLS:
        try:
            r = http_get(url, timeout=120.0)
            if r.status_code != 200 or len(r.content) < 1000:
                last_err = f"HTTP {r.status_code} bytes={len(r.content)}"
                continue
            # sniff xlsx/zip
            name = "arrecadacao_serie_historica.xlsx"
            dest = out / name
            dest.write_bytes(r.content)
            return dest, {
                "via": "http",
                "url": url,
                "file": dest.name,
                "bytes": len(r.content),
                "sha1": sha1_bytes(r.content),
            }
        except Exception as e:
            last_err = str(e)
    return None, {"error": last_err or "download failed", "candidates": CANDIDATE_URLS}


def main() -> int:
    load_dotenv()
    try:
        run = start_run("receita_arrecadacao", "rfb.arrecadacao")
    except Exception as e:
        print(f"fail-soft start_run receita_arrecadacao: {e}", file=sys.stderr)
        return 0

    out = bronze_dir("receita_arrecadacao")
    file_path, meta_dl = try_download(out)
    meta = {
        "fetched_at": utc_now(),
        "portal": PORTAL,
        "serie_page": SERIE_PAGE,
        "ingestion_run_id": run["ingestion_run_id"],
        "nota": "Arrecadação administrada/registrada pela RF ≠ receita pública total BR",
        **meta_dl,
    }

    if not file_path:
        meta["status"] = "SKIPPED"
        meta["reason"] = (
            "URL estável indisponível. Defina ATLAS_ARRECADACAO_FILE com xlsx/csv local."
        )
        write_json(out / "meta.json", meta)
        write_manifest(out, "receita_arrecadacao", [], extra=meta)
        mark_ingested(
            "receita_arrecadacao",
            run_id=run["ingestion_run_id"],
            counts={"rows": 0},
            dataset_id="rfb.arrecadacao",
            ok=True,
        )
        print(
            "SKIPPED receita_arrecadacao: sem arquivo. "
            "Use ATLAS_ARRECADACAO_FILE ou verifique URLs candidatas.",
            flush=True,
        )
        return 0

    try:
        rows = parse_xlsx(file_path)
    except Exception as e:
        meta["status"] = "SKIPPED"
        meta["parse_error"] = str(e)
        write_json(out / "meta.json", meta)
        print(f"SKIPPED receita_arrecadacao parse: {e}", flush=True)
        mark_ingested(
            "receita_arrecadacao",
            run_id=run["ingestion_run_id"],
            counts={"rows": 0},
            ok=True,
            dataset_id="rfb.arrecadacao",
        )
        return 0

    write_jsonl(out / "arrecadacao_extract.jsonl", rows)
    write_json(out / "meta.json", {**meta, "rows": len(rows), "status": "OK"})
    write_raw_record(
        source_id="receita_arrecadacao",
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=run["connector_version"],
        payload=file_path.read_bytes(),
        filename=file_path.name,
        source_url=meta.get("url") or SERIE_PAGE,
        dataset_id="rfb.arrecadacao",
    )
    write_manifest(
        out,
        "receita_arrecadacao",
        [{"file": file_path.name, "bytes": file_path.stat().st_size}],
        extra=meta,
    )
    append_event(
        "document.discovered",
        {"source": "receita_arrecadacao", "rows": len(rows)},
    )
    mark_ingested(
        "receita_arrecadacao",
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        dataset_id="rfb.arrecadacao",
        ok=True,
    )
    print(f"OK receita_arrecadacao rows={len(rows)} -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
