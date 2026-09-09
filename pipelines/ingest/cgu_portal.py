#!/usr/bin/env python3
"""
CGU Portal — coleta FOCADA no que o Atlas usa:
- Emendas só de autores que existem como p_cam_ / p_sen_ na gold
- CEIS/CNEP só para CNPJs que já aparecem em contratos PNCP (silver/gold)

Não baixa páginas genéricas de sanções/contratos aleatórios.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

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

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ANO = int(os.getenv("CGU_ANO", str(datetime.now(timezone.utc).year)))


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        # aceita também linha colada do PowerShell: $env:KEY="val"
        if line.startswith("$env:"):
            line = line[5:]
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def only_digits(s: str | None) -> str | None:
    if not s:
        return None
    d = re.sub(r"\D", "", str(s))
    return d if len(d) >= 8 else None


def load_politicos() -> list[dict]:
    if not GOLD.exists():
        return []
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    out = []
    for e in kb.get("entidades") or []:
        if e.get("tipo") != "pessoa":
            continue
        if not e["id"].startswith(("p_cam_", "p_sen_")):
            continue
        nome = e.get("nome") or e.get("nome_civil")
        if not nome:
            continue
        aliases = [a for a in (e.get("aliases") or []) if a]
        # API emendas exige nomeAutor em maiúsculas (nome de urna)
        queries: list[str] = []
        for n in [nome, *aliases]:
            u = str(n).strip().upper()
            if u and u not in queries:
                queries.append(u)
        out.append(
            {
                "id": e["id"],
                "nome": nome,
                "uf": e.get("uf"),
                "queries": queries,
                "no_poder": bool(e.get("no_poder_2026")),
            }
        )
    # Em exercício primeiro — limite CGU_EMENDA_AUTOR_LIMIT não deixa Kim/ativos de fora
    out.sort(key=lambda p: (0 if p.get("no_poder") else 1, p.get("nome") or ""))
    return out


def load_cnpjs_interessados() -> list[str]:
    """Prioriza CNPJs de contratos PNCP (cruzamento útil); depois empresas gold."""
    from_ctr: list[str] = []
    seen: set[str] = set()
    p = ROOT / "data" / "lake" / "silver" / "contratos" / "contratos_latest.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            c = only_digits(json.loads(line).get("cnpj"))
            if c and len(c) == 14 and c not in seen:
                seen.add(c)
                from_ctr.append(c)
    # empresas gold (só se sobrar cota — não misturar no topo)
    from_emp: list[str] = []
    if GOLD.exists():
        kb = json.loads(GOLD.read_text(encoding="utf-8"))
        for e in kb.get("entidades") or []:
            if e.get("tipo") != "empresa":
                continue
            c = only_digits(e.get("cnpj"))
            if c and len(c) == 14 and c not in seen:
                seen.add(c)
                from_emp.append(c)
    return from_ctr + sorted(from_emp)


def api_get(path: str, headers: dict) -> tuple[int, bytes | None]:
    url = f"{BASE}{path}"
    r = http_get(url, headers=headers, timeout=60.0)
    return r.status_code, r.content if r.status_code == 200 else r.content


def anos_emenda() -> list[int]:
    raw = os.getenv("CGU_EMENDA_ANOS", "")
    if raw.strip():
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]
    # ano corrente + anterior (emendas podem atrasar no portal)
    return [ANO, ANO - 1]


def fetch_emendas_autor(
    queries: list[str], headers: dict, max_pages: int
) -> list[dict]:
    """Tenta aliases em maiúsculas até achar; pagina por ano."""
    rows: list[dict] = []
    seen_cod: set[str] = set()
    for q in queries:
        got_any = False
        for ano in anos_emenda():
            for page in range(1, max_pages + 1):
                path = f"/emendas?ano={ano}&nomeAutor={quote(q)}&pagina={page}"
                code, body = api_get(path, headers)
                if code != 200 or not body:
                    break
                try:
                    data = json.loads(body.decode("utf-8"))
                except Exception:
                    break
                if not isinstance(data, list) or not data:
                    break
                got_any = True
                for row in data:
                    cod = str(row.get("codigoEmenda") or "")
                    if not cod or cod in seen_cod:
                        continue
                    seen_cod.add(cod)
                    row["_atlas_nome_autor_query"] = q
                    rows.append(row)
                if len(data) < 15:
                    break
        if got_any:
            break  # um alias que bate basta
    return rows


def fetch_sancao_cnpj(cadastro: str, cnpj: str, headers: dict) -> list[dict]:
    # codigoSancionado costuma aceitar CNPJ sem máscara
    path = f"/{cadastro}?codigoSancionado={cnpj}&pagina=1"
    code, body = api_get(path, headers)
    if code != 200 or not body:
        return []
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def main() -> int:
    load_dotenv()
    run = start_run("cgu_portal", "cgu.portal")
    out = bronze_dir("cgu_portal")
    key = os.getenv("ATLAS_PORTAL_API_KEY", "").strip()
    meta = {
        "fetched_at": utc_now(),
        "ingestion_run_id": run["ingestion_run_id"],
        "ano": ANO,
        "modo": "somente_politicos_e_cnpjs_kb",
    }

    if not key:
        write_json(
            out / "stub.json",
            {
                "status": "skipped_no_api_key",
                "instrucao": "Defina ATLAS_PORTAL_API_KEY no .env (formato KEY=valor).",
            },
        )
        mark_ingested("cgu_portal", run_id=run["ingestion_run_id"], counts={"stub": 1}, ok=True)
        print("CGU: stub (sem ATLAS_PORTAL_API_KEY)")
        return 0

    headers = {"Accept": "application/json", "chave-api-dados": key}
    politicos = load_politicos()
    limit_pol = int(os.getenv("CGU_EMENDA_AUTOR_LIMIT", "200"))
    max_pages = int(os.getenv("CGU_EMENDA_MAX_PAGES", "3"))
    politicos = politicos[:limit_pol]

    cnpjs = load_cnpjs_interessados()
    # default: todos os CNPJs de contratos + até N empresas extras
    limit_cnpj = int(os.getenv("CGU_CNPJ_LIMIT", "200"))
    cnpjs = cnpjs[:limit_cnpj]

    print(
        f"CGU foco: {len(politicos)} autores Casa · {len(cnpjs)} CNPJs "
        f"(PNCP primeiro) · anos={anos_emenda()}"
    )

    emendas: list[dict] = []
    emenda_por_pessoa: list[dict] = []
    seen_emenda: set[str] = set()
    autores_com_hit = 0
    for i, pol in enumerate(politicos, 1):
        rows = fetch_emendas_autor(pol["queries"], headers, max_pages)
        if rows:
            autores_com_hit += 1
        for row in rows:
            cod = str(row.get("codigoEmenda") or "")
            if not cod or cod in seen_emenda:
                continue
            seen_emenda.add(cod)
            row["_atlas_person_id"] = pol["id"]
            row["_atlas_person_nome"] = pol["nome"]
            emendas.append(row)
            emenda_por_pessoa.append(
                {"person_id": pol["id"], "codigoEmenda": cod, "nome": pol["nome"]}
            )
        if i % 20 == 0:
            print(
                f"  emendas {i}/{len(politicos)} "
                f"(total {len(emendas)}, autores_ok={autores_com_hit})",
                flush=True,
            )
        time.sleep(0.05)  # folga além do RPS global

    sancoes: list[dict] = []
    for i, cnpj in enumerate(cnpjs, 1):
        for cad in ("ceis", "cnep"):
            rows = fetch_sancao_cnpj(cad, cnpj, headers)
            for row in rows:
                row["_atlas_cnpj"] = cnpj
                row["_atlas_cadastro"] = cad.upper()
                sancoes.append(row)
        if i % 20 == 0:
            print(f"  sancoes {i}/{len(cnpjs)} (hits {len(sancoes)})", flush=True)

    write_jsonl(out / "emendas_politicos.jsonl", emendas)
    write_json(out / "emendas.json", emendas)  # compat silver_cgu
    write_jsonl(out / "emenda_links.jsonl", emenda_por_pessoa)
    write_json(out / "ceis.json", [s for s in sancoes if s.get("_atlas_cadastro") == "CEIS"])
    write_json(out / "cnep.json", [s for s in sancoes if s.get("_atlas_cadastro") == "CNEP"])
    write_jsonl(out / "sancoes_cnpj_kb.jsonl", sancoes)

    files_meta = []
    for name in (
        "emendas_politicos.jsonl",
        "emendas.json",
        "emenda_links.jsonl",
        "ceis.json",
        "cnep.json",
        "sancoes_cnpj_kb.jsonl",
    ):
        p = out / name
        if p.exists():
            raw = p.read_bytes()
            files_meta.append({"file": name, "bytes": len(raw), "sha1": sha1_bytes(raw)})
            write_raw_record(
                source_id="cgu_portal",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=raw,
                filename=name,
                source_url=BASE,
                dataset_id="cgu.portal",
                content_type="application/json",
            )

    write_manifest(
        out,
        "cgu_portal",
        files_meta,
        extra={
            **meta,
            "emendas": len(emendas),
            "sancoes": len(sancoes),
            "autores_consultados": len(politicos),
            "autores_com_emenda": autores_com_hit,
            "cnpjs_consultados": len(cnpjs),
        },
    )
    append_event(
        "document.discovered",
        {"source": "cgu_portal", "emendas": len(emendas), "sancoes": len(sancoes)},
    )
    mark_ingested(
        "cgu_portal",
        run_id=run["ingestion_run_id"],
        counts={
            "emendas": len(emendas),
            "sancoes": len(sancoes),
            "autores_com_emenda": autores_com_hit,
        },
        ok=True,
    )
    print(
        f"OK CGU foco: emendas={len(emendas)} autores_ok={autores_com_hit} "
        f"sancoes={len(sancoes)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
