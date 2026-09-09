#!/usr/bin/env python3
"""
Receita Federal CNPJ — enriquecimento escopado (Fase 1).

Modos (ATLAS_CNPJ_MODE):
  interest_api (DEFAULT) — BrasilAPI mirror do CNPJ público RFB para a fila
    data/lake/queues/cnpj_interest.jsonl
    ATLAS_CNPJ_LIMIT (default 200), rate limit via ATLAS_HTTP_RPS
  dump — lista competência mais recente nos índices RFB; só baixa se
    ATLAS_CNPJ_DUMP=1 (pesado); caso contrário manifesto + SKIP.

source_id: rfb_cnpj
Não carrega dump nacional no Neo4j — só interesse Atlas.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

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

BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
DUMP_INDEXES = [
    "https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj/",
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/",
]

SITUACAO_MAP = {
    1: "NULA",
    2: "ATIVA",
    3: "SUSPENSA",
    4: "INAPTA",
    8: "BAIXADA",
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


def only_cnpj14(val) -> str | None:
    if val is None:
        return None
    d = re.sub(r"\D", "", str(val))
    if len(d) >= 14:
        d = d.zfill(14)[-14:]
    elif d:
        d = d.zfill(14)
    return d if len(d) == 14 else None


def load_interest(limit: int) -> list[dict]:
    path = ROOT / "data" / "lake" / "queues" / "cnpj_interest.jsonl"
    if not path.is_file():
        print(
            "WARN: cnpj_interest.jsonl ausente — rode pipelines/ops/cnpj_interest_list.py",
            file=sys.stderr,
        )
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cnpj = only_cnpj14(row.get("cnpj"))
        if not cnpj:
            continue
        rows.append({**row, "cnpj": cnpj})
        if len(rows) >= limit:
            break
    return rows


def situacao_label(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.isdigit():
        return raw.strip().upper() or None
    try:
        code = int(raw)
    except (TypeError, ValueError):
        return str(raw)
    return SITUACAO_MAP.get(code, str(code))


def normalize_brasilapi(payload: dict, retrieved_at: str) -> dict:
    cnpj = only_cnpj14(payload.get("cnpj")) or ""
    socios = []
    for s in payload.get("qsa") or []:
        socios.append(
            {
                "nome": s.get("nome_socio") or s.get("nome"),
                "cnpj_cpf": s.get("cnpj_cpf_do_socio") or s.get("cnpj_cpf"),
                "qualificacao": s.get("qualificacao_socio") or s.get("qualificacao"),
            }
        )
    cnae_sec = []
    for c in payload.get("cnaes_secundarios") or []:
        if isinstance(c, dict):
            cnae_sec.append(
                {
                    "codigo": c.get("codigo"),
                    "descricao": c.get("descricao"),
                }
            )
        else:
            cnae_sec.append(c)

    situacao = situacao_label(
        payload.get("descricao_situacao_cadastral") or payload.get("situacao_cadastral")
    )
    return {
        "cnpj": cnpj,
        "cnpj_basico": cnpj[:8] if len(cnpj) == 14 else None,
        "razao_social": payload.get("razao_social"),
        "nome_fantasia": payload.get("nome_fantasia") or None,
        "situacao_cadastral": situacao,
        "data_situacao": payload.get("data_situacao_cadastral"),
        "natureza_juridica": payload.get("natureza_juridica"),
        "data_abertura": payload.get("data_inicio_atividade"),
        "capital_social": payload.get("capital_social"),
        "porte": payload.get("porte") or payload.get("descricao_porte"),
        "cnae_fiscal": {
            "codigo": payload.get("cnae_fiscal"),
            "descricao": payload.get("cnae_fiscal_descricao"),
        },
        "cnae_secundarios": cnae_sec,
        "municipio": payload.get("municipio"),
        "uf": payload.get("uf"),
        "socios": socios,
        "simples": payload.get("opcao_pelo_simples"),
        "mei": payload.get("opcao_pelo_mei"),
        "retrieved_at": retrieved_at,
        "source": "brasilapi-mirror/rfb_cnpj",
    }


def mode_interest_api(run: dict) -> int:
    limit = int(os.getenv("ATLAS_CNPJ_LIMIT", "200"))
    interest = load_interest(limit)
    out = bronze_dir("rfb_cnpj")
    raw_dir = out / "by_cnpj"
    raw_dir.mkdir(parents=True, exist_ok=True)

    extract: list[dict] = []
    errors: list[dict] = []
    files: list[dict] = []

    for i, item in enumerate(interest, 1):
        cnpj = item["cnpj"]
        url = BRASILAPI.format(cnpj=cnpj)
        try:
            r = http_get(url, timeout=45.0)
            if r.status_code == 404:
                errors.append({"cnpj": cnpj, "error": "not_found", "status": 404})
                continue
            r.raise_for_status()
            payload = r.json()
            retrieved = utc_now()
            dest = raw_dir / f"{cnpj}.json"
            dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            write_raw_record(
                source_id="rfb_cnpj",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=payload,
                filename=f"cnpj_{cnpj}.json",
                source_url=url,
                dataset_id="rfb.cnpj",
                source_record_id=cnpj,
            )
            files.append({"file": dest.name, "bytes": dest.stat().st_size, "cnpj": cnpj})
            extract.append(normalize_brasilapi(payload, retrieved))
        except Exception as e:
            errors.append({"cnpj": cnpj, "error": str(e)})
            print(f"fail-soft CNPJ {cnpj}: {e}", file=sys.stderr)
        if i % 25 == 0:
            print(f"… {i}/{len(interest)} enriquecidos={len(extract)}", flush=True)

    write_jsonl(out / "cnpj_extract.jsonl", extract)
    write_json(
        out / "meta.json",
        {
            "mode": "interest_api",
            "fetched_at": utc_now(),
            "limit": limit,
            "interest_requested": len(interest),
            "enriched": len(extract),
            "errors": len(errors),
            "source_note": "BrasilAPI espelho do CNPJ público RFB (não API oficial RFB)",
            "ingestion_run_id": run["ingestion_run_id"],
        },
    )
    if errors:
        write_json(out / "errors.json", errors[:500])
    write_manifest(
        out,
        "rfb_cnpj",
        files[:50] + ([{"file": "…", "note": f"{len(files)} total"}] if len(files) > 50 else []),
        extra={"mode": "interest_api", "enriched": len(extract)},
    )
    append_event(
        "document.discovered",
        {"source": "rfb_cnpj", "mode": "interest_api", "enriched": len(extract)},
    )
    mark_ingested(
        "rfb_cnpj",
        run_id=run["ingestion_run_id"],
        counts={"enriched": len(extract), "errors": len(errors), "requested": len(interest)},
        dataset_id="rfb.cnpj",
        ok=True,
    )
    print(f"OK cnpj interest_api enriched={len(extract)}/{len(interest)} -> {out}", flush=True)
    return 0


def _list_dump_months(index_url: str) -> tuple[str, list[str]] | None:
    try:
        r = http_get(index_url, timeout=60.0)
        r.raise_for_status()
    except Exception as e:
        print(f"dump index fail {index_url}: {e}", file=sys.stderr)
        return None
    # pastas YYYY-MM/
    months = sorted(set(re.findall(r"href=[\"']?(\d{4}-\d{2})/?[\"']?", r.text)))
    if not months:
        # fallback: qualquer link relativo
        hrefs = re.findall(r"href=[\"']([^\"'#]+)[\"']", r.text)
        months = sorted({h.strip("/").split("/")[-1] for h in hrefs if re.match(r"^\d{4}-\d{2}$", h.strip("/").split("/")[-1])})
    return index_url, months


def mode_dump(run: dict) -> int:
    out = bronze_dir("rfb_cnpj")
    do_download = os.getenv("ATLAS_CNPJ_DUMP", "").strip() in ("1", "true", "True", "yes")
    chosen: tuple[str, list[str]] | None = None
    for url in DUMP_INDEXES:
        chosen = _list_dump_months(url)
        if chosen and chosen[1]:
            break
        time.sleep(0.5)

    meta = {
        "mode": "dump",
        "fetched_at": utc_now(),
        "indexes_tried": DUMP_INDEXES,
        "ATLAS_CNPJ_DUMP": do_download,
        "ingestion_run_id": run["ingestion_run_id"],
        "nota": (
            "Dump nacional é pesado (GB). Default: só manifesto. "
            "Defina ATLAS_CNPJ_DUMP=1 para baixar arquivos da competência mais recente."
        ),
    }
    files: list[dict] = []
    if not chosen or not chosen[1]:
        meta["status"] = "SKIPPED"
        meta["reason"] = "nenhum índice de competências acessível"
        write_json(out / "dump_manifest.json", meta)
        write_manifest(out, "rfb_cnpj", files, extra=meta)
        mark_ingested(
            "rfb_cnpj",
            run_id=run["ingestion_run_id"],
            counts={"files": 0},
            dataset_id="rfb.cnpj.dump",
            ok=True,
        )
        print("SKIPPED cnpj dump: índices indisponíveis", flush=True)
        return 0

    index_url, months = chosen
    latest = months[-1]
    month_url = urljoin(index_url if index_url.endswith("/") else index_url + "/", latest + "/")
    meta["index_url"] = index_url
    meta["latest_month"] = latest
    meta["available_months"] = months[-12:]
    meta["month_url"] = month_url

    file_names: list[str] = []
    try:
        r = http_get(month_url, timeout=60.0)
        r.raise_for_status()
        file_names = sorted(
            set(re.findall(r"href=[\"']([^\"']+\.(?:zip|ZIP))[\"']", r.text))
        )
    except Exception as e:
        meta["list_error"] = str(e)

    meta["files_available"] = file_names
    write_json(out / "dump_manifest.json", meta)
    write_raw_record(
        source_id="rfb_cnpj",
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=run["connector_version"],
        payload=meta,
        filename="dump_manifest.json",
        source_url=month_url,
        dataset_id="rfb.cnpj.dump",
    )

    if not do_download:
        meta["status"] = "SKIPPED"
        meta["reason"] = "ATLAS_CNPJ_DUMP!=1 — manifesto apenas"
        write_json(out / "dump_manifest.json", meta)
        write_manifest(out, "rfb_cnpj", files, extra=meta)
        mark_ingested(
            "rfb_cnpj",
            run_id=run["ingestion_run_id"],
            counts={"files_listed": len(file_names), "downloaded": 0},
            dataset_id="rfb.cnpj.dump",
            ok=True,
        )
        print(
            f"SKIPPED cnpj dump download (manifest only): {latest} files={len(file_names)}",
            flush=True,
        )
        return 0

    # download pesado — opcional
    for name in file_names:
        url = urljoin(month_url, name)
        try:
            r = http_get(url, timeout=600.0)
            r.raise_for_status()
            dest = out / Path(name).name
            dest.write_bytes(r.content)
            files.append(
                {"file": dest.name, "bytes": len(r.content), "sha1": sha1_bytes(r.content)}
            )
            write_raw_record(
                source_id="rfb_cnpj",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=r.content,
                filename=dest.name,
                source_url=url,
                dataset_id="rfb.cnpj.dump",
            )
        except Exception as e:
            print(f"fail dump file {name}: {e}", file=sys.stderr)

    write_manifest(out, "rfb_cnpj", files, extra=meta)
    mark_ingested(
        "rfb_cnpj",
        run_id=run["ingestion_run_id"],
        counts={"downloaded": len(files)},
        dataset_id="rfb.cnpj.dump",
        ok=True,
    )
    print(f"OK cnpj dump downloaded={len(files)} -> {out}", flush=True)
    return 0


def main() -> int:
    load_dotenv()
    mode = (os.getenv("ATLAS_CNPJ_MODE") or "interest_api").strip().lower()
    try:
        run = start_run("rfb_cnpj", "rfb.cnpj")
    except Exception as e:
        print(f"fail-soft start_run: {e}", file=sys.stderr)
        return 0

    try:
        if mode == "dump":
            return mode_dump(run)
        return mode_interest_api(run)
    except Exception as e:
        print(f"fail-soft cnpj_rfb: {e}", file=sys.stderr)
        try:
            mark_ingested(
                "rfb_cnpj",
                run_id=run["ingestion_run_id"],
                ok=False,
                error=str(e),
                dataset_id="rfb.cnpj",
            )
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
