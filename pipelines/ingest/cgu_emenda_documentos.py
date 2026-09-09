#!/usr/bin/env python3
"""
FASE 4 (resto) — documentos / execução de emendas no Portal da Transparência.

Endpoint: GET /emendas/documentos/{codigoEmenda}?pagina=N

Para cada emenda em silver/emendas (ou amostra Kim), baixa documentos
orçamentários ligados ao código e grava bronze + silver com beneficiário
quando o payload trouxer CNPJ/nome/órgão.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    LAKE,
    append_event,
    bronze_dir,
    day_stamp,
    http_get,
    utc_now,
    write_json,
    write_jsonl,
    write_manifest,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"


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


def only_digits(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_emenda_codigos() -> list[dict]:
    """Lista {codigo, person_id, emenda_id?, ano} a partir do silver."""
    rows = _load_jsonl(LAKE / "silver" / "emendas" / "emendas_latest.jsonl")
    out: list[dict] = []
    seen: set[str] = set()
    force = {
        x.strip()
        for x in (os.getenv("EMENDA_DOC_FORCE_CODIGOS", "") or "").split(",")
        if x.strip()
    }
    force_person = os.getenv("EMENDA_DOC_PERSON_ID", "").strip()
    anos_ok = {
        int(x)
        for x in (os.getenv("EMENDA_DOC_ANOS", "") or "").split(",")
        if x.strip().isdigit()
    }
    # pular códigos já enriquecidos (resume)
    skip_done = os.getenv("EMENDA_DOC_SKIP_DONE", "1") == "1"
    done: set[str] = set()
    prev = LAKE / "silver" / "emenda_transferencias" / "resumo_latest.jsonl"
    if skip_done and prev.exists():
        for r in _load_jsonl(prev):
            bens = r.get("beneficiarios") or []
            if bens and r.get("codigo_emenda"):
                done.add(str(r["codigo_emenda"]))

    for r in rows:
        cod = str(r.get("codigo") or r.get("id_externo") or "").strip()
        if not cod or cod in seen:
            continue
        if force and cod not in force:
            continue
        if force_person and str(r.get("person_id") or "") != force_person:
            continue
        ano = r.get("ano")
        if anos_ok and ano not in anos_ok and str(ano) not in {str(a) for a in anos_ok}:
            try:
                if int(ano) not in anos_ok:
                    continue
            except (TypeError, ValueError):
                continue
        if skip_done and cod in done:
            continue
        seen.add(cod)
        out.append(
            {
                "codigo": cod,
                "person_id": r.get("person_id"),
                "ano": r.get("ano"),
                "autor": r.get("autor"),
                "localidade": r.get("localidade"),
                "valor_pago": r.get("valor_pago") or r.get("valor_empenhado"),
            }
        )
    limit = int(os.getenv("EMENDA_DOC_LIMIT", "0") or "0")
    if limit > 0:
        out = out[:limit]
    return out


def money(s) -> float | None:
    if s is None or s == "" or s == "-":
        return None
    t = str(s).strip()
    if "," in t and t.rfind(",") > t.rfind("."):
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def fetch_documentos(codigo: str, headers: dict, max_pages: int) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        path = f"/emendas/documentos/{codigo}?pagina={page}"
        url = BASE + path
        r = http_get(url, headers=headers, timeout=60.0)
        if r.status_code != 200 or not r.content:
            break
        try:
            data = json.loads(r.content.decode("utf-8"))
        except Exception:
            break
        if not isinstance(data, list) or not data:
            break
        for row in data:
            if isinstance(row, dict):
                row = dict(row)
                row["_atlas_codigo_emenda"] = codigo
                rows.append(row)
        if len(data) < 15:
            break
        time.sleep(float(os.getenv("EMENDA_DOC_SLEEP", "0.12")))
    return rows


def enrich_documento(ref: dict, headers: dict) -> dict:
    """Lista de emendas só traz refs — detalhe em /despesas/documentos/{codigo}."""
    codigo_doc = str(ref.get("codigoDocumento") or "").strip()
    if not codigo_doc:
        return ref
    url = f"{BASE}/despesas/documentos/{codigo_doc}"
    r = http_get(url, headers=headers, timeout=60.0)
    if r.status_code != 200 or not r.content:
        return ref
    try:
        detail = json.loads(r.content.decode("utf-8"))
    except Exception:
        return ref
    if not isinstance(detail, dict):
        return ref
    merged = {**ref, **detail}
    merged["_atlas_codigo_emenda"] = ref.get("_atlas_codigo_emenda")
    merged["_atlas_enriched"] = True
    return merged


def normalize_doc(row: dict, meta: dict) -> dict:
    """Extrai campos úteis de documento orçamentário / transferência."""
    cnpj = only_digits(row.get("codigoFavorecido") or row.get("cnpjFavorecido") or row.get("cnpj"))
    nome = row.get("nomeFavorecido") or row.get("nomeBeneficiario")
    if not nome and row.get("favorecido"):
        # "CNPJ - NOME"
        fav = str(row.get("favorecido"))
        if " - " in fav:
            nome = fav.split(" - ", 1)[1].strip()
        else:
            nome = fav
    orgao = row.get("orgao") or row.get("ug") or row.get("uo")
    valor_f = money(row.get("valor"))
    fase = row.get("fase") or row.get("especie")
    data = row.get("data")
    doc_id = str(row.get("documento") or row.get("codigoDocumento") or "")

    return {
        "codigo_emenda": meta.get("codigo") or row.get("_atlas_codigo_emenda"),
        "person_id": meta.get("person_id"),
        "documento_id": doc_id or None,
        "fase": fase,
        "data": data,
        "valor": round(valor_f, 2) if valor_f is not None else None,
        "cnpj_beneficiario": cnpj if len(cnpj) in (11, 14) else None,
        "nome_beneficiario": (str(nome).strip() if nome else None),
        "orgao": (str(orgao).strip() if orgao else None),
        "ug": row.get("ug"),
        "observacao": (str(row.get("observacao") or "")[:280] or None),
        "funcao": row.get("funcao"),
        "localidade": meta.get("localidade") or row.get("localizadorGasto"),
        "ano": meta.get("ano"),
        "fonte": "cgu_emenda_documentos",
        "fonte_url": f"{BASE}/despesas/documentos/{doc_id}" if doc_id else None,
        "enriched": bool(row.get("_atlas_enriched")),
    }


def main() -> int:
    load_dotenv()
    run = start_run("cgu_emenda_documentos", "cgu.emenda_documentos")
    key = os.getenv("ATLAS_PORTAL_API_KEY", "").strip()
    if not key:
        print("sem ATLAS_PORTAL_API_KEY", file=sys.stderr)
        return 1

    emendas = load_emenda_codigos()
    if not emendas:
        print("nenhuma emenda no silver — rode silver_cgu / cgu_portal", file=sys.stderr)
        return 1

    headers = {"Accept": "application/json", "chave-api-dados": key}
    max_pages = int(os.getenv("EMENDA_DOC_MAX_PAGES", "3"))
    enrich = os.getenv("EMENDA_DOC_ENRICH", "1") == "1"
    detail_limit = int(os.getenv("EMENDA_DOC_DETAIL_LIMIT", "0") or "0")
    out = bronze_dir("cgu_emenda_docs")
    print(
        f"emenda docs: {len(emendas)} códigos · max_pages={max_pages} "
        f"enrich={enrich}"
    )

    bronze_rows: list[dict] = []
    silver_rows: list[dict] = []
    n_docs = 0
    n_enriched = 0
    n_empty = 0
    n_err = 0
    n_detail = 0

    for i, meta in enumerate(emendas, 1):
        cod = meta["codigo"]
        try:
            docs = fetch_documentos(cod, headers, max_pages)
        except Exception as e:
            n_err += 1
            print(f"  err {cod}: {e}", file=sys.stderr)
            continue
        if not docs:
            n_empty += 1
        else:
            n_docs += len(docs)
            # prioriza Empenho/Pagamento (têm valor/favorecido útil)
            fases_ok = {"empenho", "pagamento"}
            ranked = sorted(
                docs,
                key=lambda d: (
                    0 if str(d.get("fase") or "").lower() in fases_ok else 1,
                    str(d.get("fase") or ""),
                ),
            )
            per_em = int(os.getenv("EMENDA_DOC_DETAIL_PER_EMENDA", "8") or "8")
            to_enrich = ranked[:per_em] if enrich else []
            enrich_set = {id(x) for x in to_enrich}
            for d in ranked:
                if enrich and id(d) in enrich_set and (
                    detail_limit <= 0 or n_detail < detail_limit
                ):
                    d = enrich_documento(d, headers)
                    n_detail += 1
                    if d.get("_atlas_enriched"):
                        n_enriched += 1
                    time.sleep(float(os.getenv("EMENDA_DOC_SLEEP", "0.1")))
                bronze_rows.append(d)
                silver_rows.append(normalize_doc(d, meta))
        if i % 10 == 0 or i == len(emendas):
            print(
                f"  {i}/{len(emendas)} docs={n_docs} enriched={n_enriched} "
                f"vazias={n_empty} err={n_err}",
                flush=True,
            )
        time.sleep(float(os.getenv("EMENDA_DOC_SLEEP", "0.12")))

    write_jsonl(out / "emenda_documentos.jsonl", bronze_rows)
    write_json(
        out / "meta.json",
        {
            "fetched_at": utc_now(),
            "ingestion_run_id": run["ingestion_run_id"],
            "emendas": len(emendas),
            "documentos": n_docs,
            "emendas_sem_doc": n_empty,
            "erros": n_err,
        },
    )
    write_manifest(
        out,
        "cgu_emenda_docs",
        [{"count": n_docs}],
        extra={"emendas": len(emendas), "vazias": n_empty},
    )

    silver_dir = LAKE / "silver" / "emenda_transferencias"
    silver_dir.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    write_jsonl(silver_dir / f"docs_{stamp}.jsonl", silver_rows)
    # merge com docs anteriores (resume / lotes)
    prev_docs = {
        f"{d.get('codigo_emenda')}|{d.get('documento_id')}": d
        for d in _load_jsonl(silver_dir / "docs_latest.jsonl")
        if d.get("codigo_emenda")
    }
    for d in silver_rows:
        prev_docs[f"{d.get('codigo_emenda')}|{d.get('documento_id')}"] = d
    merged_docs = list(prev_docs.values())
    write_jsonl(silver_dir / "docs_latest.jsonl", merged_docs)
    silver_rows = merged_docs
    # agrega por emenda → beneficiários (prioriza fase Pagamento; senão Empenho)
    by_em: dict[str, dict] = {}
    for s in silver_rows:
        cod = s.get("codigo_emenda") or ""
        slot = by_em.setdefault(
            cod,
            {
                "codigo_emenda": cod,
                "person_id": s.get("person_id"),
                "ano": s.get("ano"),
                "localidade": s.get("localidade"),
                "qtd_documentos": 0,
                "valor_pagamento": 0.0,
                "valor_empenho": 0.0,
                "beneficiarios": {},
                "fonte": "cgu_emenda_documentos",
            },
        )
        slot["qtd_documentos"] += 1
        fase = (s.get("fase") or "").lower()
        val = float(s["valor"]) if s.get("valor") is not None else None
        if val is not None:
            if "pagamento" in fase:
                slot["valor_pagamento"] += val
            elif "empenho" in fase:
                slot["valor_empenho"] += val
        key_b = (
            s.get("cnpj_beneficiario")
            or (s.get("nome_beneficiario") or "").upper()
            or (s.get("orgao") or "").upper()
        )
        if not key_b:
            continue
        b = slot["beneficiarios"].setdefault(
            key_b,
            {
                "cnpj": s.get("cnpj_beneficiario"),
                "nome": s.get("nome_beneficiario"),
                "orgao": s.get("orgao"),
                "valor_pagamento": 0.0,
                "valor_empenho": 0.0,
                "qtd": 0,
            },
        )
        b["qtd"] += 1
        if not b.get("nome") and s.get("nome_beneficiario"):
            b["nome"] = s.get("nome_beneficiario")
        if val is not None:
            if "pagamento" in fase:
                b["valor_pagamento"] += val
            elif "empenho" in fase:
                b["valor_empenho"] += val

    resumos = []
    for slot in by_em.values():
        bens_raw = []
        for b in slot["beneficiarios"].values():
            valor = b["valor_pagamento"] or b["valor_empenho"]
            bens_raw.append(
                {
                    "cnpj": b.get("cnpj"),
                    "nome": b.get("nome") or b.get("orgao"),
                    "orgao": b.get("orgao"),
                    "valor": round(valor, 2),
                    "qtd": b.get("qtd"),
                }
            )
        bens = sorted(bens_raw, key=lambda x: -x["valor"])[:20]
        valor_total = slot["valor_pagamento"] or slot["valor_empenho"]
        resumos.append(
            {
                "codigo_emenda": slot["codigo_emenda"],
                "person_id": slot["person_id"],
                "ano": slot["ano"],
                "localidade": slot["localidade"],
                "qtd_documentos": slot["qtd_documentos"],
                "valor_total": round(valor_total, 2),
                "beneficiarios": bens,
                "fonte": slot["fonte"],
                "fonte_url": (
                    "https://portaldatransparencia.gov.br/emendas/consulta"
                    f"?codigoEmenda={slot['codigo_emenda']}"
                ),
            }
        )
    write_jsonl(silver_dir / f"resumo_{stamp}.jsonl", resumos)
    write_jsonl(silver_dir / "resumo_latest.jsonl", resumos)

    mark_ingested(
        "cgu_emenda_documentos",
        run_id=run["ingestion_run_id"],
        counts={"documentos": n_docs, "emendas": len(emendas), "com_beneficiario": len(resumos)},
        ok=True,
    )
    append_event(
        "document.discovered",
        {"source": "cgu_emenda_documentos", "docs": n_docs, "emendas": len(emendas)},
    )
    print(
        f"OK emenda docs: emendas={len(emendas)} docs={n_docs} "
        f"resumos={len(resumos)} vazias={n_empty}"
    )
    return 0 if n_docs or not emendas else 1


if __name__ == "__main__":
    raise SystemExit(main())
