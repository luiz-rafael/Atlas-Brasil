#!/usr/bin/env python3
"""Ingestor Senado — Dados Abertos Legislativos -> bronze."""

from __future__ import annotations

import os
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

BASE = "https://legis.senado.leg.br/dadosabertos"


def fetch_json(path: str) -> dict:
    url = path if path.startswith("http") else f"{BASE}{path}"
    r = http_get(url, headers={"Accept": "application/json"}, timeout=90.0)
    r.raise_for_status()
    return r.json()


def list_senadores_atual() -> list[dict]:
    data = fetch_json("/senador/lista/atual.json")
    # estrutura: ListaParlamentarStanding / Parlamentares / Parlamentar
    root = data.get("ListaParlamentarStanding") or data.get("ListaParlamentarEmExercicio") or data
    pars = None
    if isinstance(root, dict):
        pars = (
            root.get("Parlamentares", {}).get("Parlamentar")
            if isinstance(root.get("Parlamentares"), dict)
            else root.get("Parlamentar")
        )
        if pars is None and "Parlamentares" in root:
            block = root["Parlamentares"]
            if isinstance(block, list):
                pars = block
            elif isinstance(block, dict):
                pars = block.get("Parlamentar")
    if pars is None:
        # fallback: procurar lista de IdentificacaoParlamentar
        pars = []
        def walk(o):
            if isinstance(o, dict):
                if "IdentificacaoParlamentar" in o:
                    pars.append(o)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for i in o:
                    walk(i)
        walk(data)
        return pars
    if isinstance(pars, dict):
        return [pars]
    return list(pars or [])


def main() -> int:
    run = start_run("senado_legis", "senado.senadores_atual")
    out = bronze_dir("senado_legis")
    print(f"bronze -> {out} run={run['ingestion_run_id']}")

    lista = list_senadores_atual()
    write_json(out / "lista_atual_raw.json", {"count": len(lista), "items": lista})

    # normalizar identificação
    rows = []
    for item in lista:
        ident = item.get("IdentificacaoParlamentar") or item
        if not isinstance(ident, dict):
            continue
        rows.append(
            {
                "CodigoParlamentar": ident.get("CodigoParlamentar"),
                "NomeParlamentar": ident.get("NomeParlamentar") or ident.get("NomeCompletoParlamentar"),
                "NomeCompletoParlamentar": ident.get("NomeCompletoParlamentar"),
                "SiglaPartidoParlamentar": ident.get("SiglaPartidoParlamentar"),
                "UfParlamentar": ident.get("UfParlamentar"),
                "UrlFotoParlamentar": ident.get("UrlFotoParlamentar"),
                "UrlPaginaParlamentar": ident.get("UrlPaginaParlamentar"),
                "EmailParlamentar": ident.get("EmailParlamentar"),
                "FormaTratamento": ident.get("FormaTratamento"),
                "raw": item,
            }
        )

    write_jsonl(out / "senadores.jsonl", rows)

    # 0 = sem detalhe; -1 = todos; N = primeiros N
    max_detail = int(os.getenv("SENADO_DETAIL_LIMIT", "0") or "0")
    if max_detail == 0:
        targets = []
    elif max_detail < 0:
        targets = rows
    else:
        targets = rows[:max_detail]
    details = []
    for i, s in enumerate(targets, 1):
        code = s.get("CodigoParlamentar")
        if not code:
            continue
        try:
            det = fetch_json(f"/senador/{code}.json")
            details.append({"CodigoParlamentar": code, "detalhe": det})
        except Exception as e:
            print(f"  fail detalhe {code}: {e}", file=sys.stderr)
        if i % 20 == 0:
            print(f"  detalhes {i}/{len(targets)}")

    write_jsonl(out / "senadores_detalhe.jsonl", details)

    write_raw_record(
        source_id="senado_legis",
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=run["connector_version"],
        payload=rows,
        filename="senadores.jsonl",
        source_url=BASE,
        dataset_id="senado.senadores_atual",
    )

    files_meta = []
    for name in ("lista_atual_raw.json", "senadores.jsonl", "senadores_detalhe.jsonl"):
        path = out / name
        raw = path.read_bytes()
        count = len(rows) if "senadores.jsonl" == name else (
            len(details) if "detalhe" in name else 1
        )
        files_meta.append({"file": name, "bytes": len(raw), "sha1": sha1_bytes(raw), "count": count})

    write_manifest(
        out,
        "senado_legis",
        files_meta,
        extra={
            "source_url": BASE,
            "fetched_at": utc_now(),
            "ingestion_run_id": run["ingestion_run_id"],
        },
    )
    append_event(
        "document.discovered",
        {
            "document_id": f"senado_legis_{out.name}",
            "source": "senado_legis",
            "path": str(out),
            "counts": {"senadores": len(rows), "detalhes": len(details)},
        },
    )
    mark_ingested(
        "senado_legis",
        run_id=run["ingestion_run_id"],
        counts={"senadores": len(rows)},
    )
    print(f"OK Senado: {len(rows)} senadores, {len(details)} detalhes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
