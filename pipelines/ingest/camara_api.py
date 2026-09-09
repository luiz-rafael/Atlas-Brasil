#!/usr/bin/env python3
"""Ingestor Câmara — API Dados Abertos v2 -> bronze.

Por padrão (CAMARA_HISTORICO=1) une legislaturas do escopo 2010–2026.
Titulares e suplentes que assumiram entram na lista da API por idLegislatura.
"""

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
from pipelines.config.escopo import camara_legislaturas  # noqa: E402
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402

BASE = "https://dadosabertos.camara.leg.br/api/v2"
HEADERS = {"Accept": "application/json"}


def fetch_json(url: str) -> dict:
    r = http_get(url, headers=HEADERS, timeout=90.0)
    r.raise_for_status()
    return r.json()


def paginate_deputados(
    id_legislatura: int | None = None, limit_pages: int | None = None
) -> list[dict]:
    q = "itens=100&ordem=ASC&ordenarPor=nome"
    if id_legislatura is not None:
        q += f"&idLegislatura={id_legislatura}"
    url = f"{BASE}/deputados?{q}"
    rows: list[dict] = []
    page = 0
    while url:
        page += 1
        if limit_pages and page > limit_pages:
            break
        data = fetch_json(url)
        batch = data.get("dados") or []
        for d in batch:
            if id_legislatura is not None:
                d["_idLegislatura"] = id_legislatura
        rows.extend(batch)
        next_link = None
        for link in data.get("links") or []:
            if link.get("rel") == "next":
                next_link = link.get("href")
                break
        url = next_link
        print(
            f"  deputados leg={id_legislatura or 'atual'} p{page}: "
            f"+{len(batch)} (total {len(rows)})"
        )
    return rows


def paginate_partidos() -> list[dict]:
    url = f"{BASE}/partidos?itens=100"
    rows: list[dict] = []
    while url:
        data = fetch_json(url)
        rows.extend(data.get("dados") or [])
        next_link = None
        for link in data.get("links") or []:
            if link.get("rel") == "next":
                next_link = link.get("href")
                break
        url = next_link
    return rows


def main() -> int:
    run = start_run("camara_v2", "camara.deputados")
    out = bronze_dir("camara_v2")
    print(f"bronze -> {out} run={run['ingestion_run_id']}")

    historico = os.getenv("CAMARA_HISTORICO", "1") == "1"
    legs = camara_legislaturas() if historico else []
    by_id: dict[int, dict] = {}
    if legs:
        for leg in legs:
            for d in paginate_deputados(id_legislatura=leg):
                did = d.get("id")
                if did is None:
                    continue
                prev = by_id.get(did)
                if not prev:
                    d["_legislaturas"] = [leg]
                    by_id[did] = d
                else:
                    legs_l = list(prev.get("_legislaturas") or [])
                    if leg not in legs_l:
                        legs_l.append(leg)
                    # Manter campos da legislatura mais recente (partido/UF mudam).
                    prev_max = max(prev.get("_legislaturas") or [0])
                    if leg >= prev_max:
                        d["_legislaturas"] = legs_l
                        by_id[did] = d
                    else:
                        prev["_legislaturas"] = legs_l
                        by_id[did] = prev
        # Overlay da lista atual (sem filtro de legislatura) = mandato em exercício.
        print("  overlay lista atual (partido/UF vigentes)…")
        for d in paginate_deputados():
            did = d.get("id")
            if did is None:
                continue
            if did in by_id:
                cur = by_id[did]
                for k in (
                    "siglaPartido",
                    "siglaUf",
                    "nome",
                    "email",
                    "urlFoto",
                    "uri",
                    "idLegislatura",
                ):
                    if d.get(k) is not None:
                        cur[k] = d[k]
                cur["_status_atual"] = True
                legs_l = list(cur.get("_legislaturas") or [])
                leg_now = d.get("idLegislatura")
                if leg_now and leg_now not in legs_l:
                    legs_l.append(leg_now)
                    cur["_legislaturas"] = legs_l
            else:
                d["_legislaturas"] = [d.get("idLegislatura")] if d.get("idLegislatura") else []
                d["_status_atual"] = True
                by_id[did] = d
        deputados = list(by_id.values())
        print(f"unificados por id: {len(deputados)} (legs={legs})")
    else:
        deputados = paginate_deputados()

    partidos = paginate_partidos()

    max_detail = int(os.getenv("CAMARA_DETAIL_LIMIT", "0") or "0")
    details = []
    if max_detail == 0:
        targets = []
    elif max_detail < 0:
        targets = deputados
    else:
        targets = deputados[:max_detail]
    for i, d in enumerate(targets, 1):
        did = d.get("id")
        if not did:
            continue
        try:
            det = fetch_json(f"{BASE}/deputados/{did}")
            details.append(det.get("dados") or det)
        except Exception as e:
            print(f"  fail detalhe {did}: {e}", file=sys.stderr)
        if i % 50 == 0:
            print(f"  detalhes {i}/{len(targets)}")

    files_meta = []
    for name, payload, ds in [
        ("deputados.jsonl", deputados, "camara.deputados"),
        ("partidos.jsonl", partidos, None),
        ("deputados_detalhe.jsonl", details, None),
    ]:
        path = out / name
        write_jsonl(path, payload if isinstance(payload, list) else [payload])
        raw = path.read_bytes()
        files_meta.append(
            {
                "file": name,
                "bytes": len(raw),
                "sha1": sha1_bytes(raw),
                "count": len(payload) if isinstance(payload, list) else 1,
            }
        )
        write_raw_record(
            source_id="camara_v2",
            ingestion_run_id=run["ingestion_run_id"],
            connector_version=run["connector_version"],
            payload=payload,
            filename=name,
            source_url=BASE,
            dataset_id=ds or "camara.deputados",
        )

    write_json(
        out / "meta_escopo.json",
        {
            "historico": historico,
            "legislaturas": legs,
            "deputados": len(deputados),
            "fetched_at": utc_now(),
        },
    )
    write_manifest(
        out,
        "camara_v2",
        files_meta,
        extra={"ingestion_run_id": run["ingestion_run_id"], "legislaturas": legs},
    )
    append_event("document.discovered", {"source": "camara_v2", "deputados": len(deputados)})
    mark_ingested(
        "camara_v2",
        run_id=run["ingestion_run_id"],
        counts={"deputados": len(deputados), "partidos": len(partidos)},
        ok=True,
        dataset_id=dataset_id_from_env("camara_api"),
    )
    print(f"OK Camara: {len(deputados)} deputados, {len(partidos)} partidos, {len(details)} detalhes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
