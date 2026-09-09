#!/usr/bin/env python3
"""
CGU público → LEGAL_CASE (documental).

Coleta só o que cruza a KB (políticos Casa / CNPJs conhecidos):
- Acordos de leniência
- CEAF (expulsões administrativas — match por nome único)
- CEPIM (entidades impedidas — match por CNPJ)
- Operações especiais CGU (lista pública) + menções só se o texto oficial citar nome/CNPJ da KB

Relações: MENTIONED_IN apenas. Nunca INVESTIGATED_IN automático.
Alinhado a obs_investigacao.md §§8–9, 20.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
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
OPS_URL = (
    "https://www.gov.br/cgu/pt-br/assuntos/auditoria-e-fiscalizacao/"
    "operacoes-especiais/operacoes-especiais"
)
GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"


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


def only_digits(s: str | None) -> str | None:
    if not s:
        return None
    d = re.sub(r"\D", "", str(s))
    return d if len(d) >= 8 else None


def _norm(s: str | None) -> str:
    s = (s or "").upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def kb_index() -> tuple[set[str], dict[str, list[str]], dict[str, str]]:
    """cnpjs, nome_norm -> [person_ids], cnpj -> empresa_id."""
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
            if e.get("nome"):
                nn = _norm(e["nome"])
                if len(nn) > 8:
                    names.setdefault(nn, []).append(e["id"])
        if e.get("tipo") == "pessoa" and e["id"].startswith(("p_cam_", "p_sen_")):
            for n in [e.get("nome"), *(e.get("aliases") or [])]:
                nn = _norm(n)
                if len(nn) > 8:
                    names.setdefault(nn, []).append(e["id"])
    return cnpjs, names, emp_by_cnpj


def api_pages(path: str, headers: dict, max_pages: int) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        sep = "&" if "?" in path else "?"
        url = f"{BASE}{path}{sep}pagina={page}"
        try:
            r = http_get(url, headers=headers, timeout=60.0)
            if r.status_code != 200:
                print(f"  {path} p{page} HTTP {r.status_code}", file=sys.stderr)
                break
            data = r.json()
            if not isinstance(data, list) or not data:
                break
            rows.extend(data)
            if len(data) < 15:
                break
            time.sleep(0.05)
        except Exception as e:
            print(f"fail {path} p{page}: {e}", file=sys.stderr)
            break
    return rows


def match_blob(
    blob: str, cnpjs: set[str], names: dict[str, list[str]]
) -> tuple[str | None, str | None, str | None]:
    """Retorna (cnpj, name, entity_id) se match único/forte."""
    digits = re.sub(r"\D", "", blob)
    for c in cnpjs:
        if c in digits:
            return c, None, None
    blob_n = _norm(blob)
    for n, ids in names.items():
        if n in blob_n:
            # só aceita se o nome aponta para no máximo 1 entidade
            uniq = list(dict.fromkeys(ids))
            if len(uniq) == 1:
                return None, n, uniq[0]
    return None, None, None


def parse_operacoes(html: str) -> list[dict]:
    """Extrai lista 'DD/MM/AAAA - Operação Nome' e links de notícia relacionados."""
    ops: list[dict] = []
    # padrão textual da lista
    for m in re.finditer(
        r"(\d{2}/\d{2}/\d{4})\s*[-–]\s*(Operação[^<\n]+)",
        html,
        flags=re.IGNORECASE,
    ):
        data, nome = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
        ops.append({"data": data, "nome": nome, "url": OPS_URL})
    # notícias ligadas na mesma página
    news = re.findall(
        r'href="(https://www\.gov\.br/cgu/pt-br/assuntos/noticias/[^"]+)"',
        html,
    )
    seen = set()
    for u in news:
        if u in seen:
            continue
        seen.add(u)
        slug = u.rstrip("/").split("/")[-1].replace("-", " ")
        ops.append(
            {
                "data": "",
                "nome": f"Notícia CGU: {slug[:120]}",
                "url": u,
                "kind": "noticia",
            }
        )
    # dedupe por nome
    out, seen_n = [], set()
    for o in ops:
        k = _norm(o["nome"])
        if k in seen_n:
            continue
        seen_n.add(k)
        out.append(o)
    return out


def main() -> int:
    load_dotenv()
    run = start_run("cgu_portal", "cgu.legal")
    out = bronze_dir("cgu_legal")
    key = os.getenv("ATLAS_PORTAL_API_KEY", "").strip()
    if not key:
        write_json(out / "stub.json", {"status": "skipped_no_api_key"})
        print("CGU legal: stub sem chave")
        return 0

    headers = {"Accept": "application/json", "chave-api-dados": key}
    max_pages = int(os.getenv("CGU_LEGAL_PAGES", "5"))
    cnpjs, names, emp_by_cnpj = kb_index()

    # --- leniência ---
    leniencia_raw = api_pages("/acordos-leniencia", headers, max_pages)
    leniencia_kb: list[dict] = []
    for row in leniencia_raw:
        blob = json.dumps(row, ensure_ascii=False)
        hit_c, hit_n, hit_id = match_blob(blob, cnpjs, names)
        if hit_c or hit_n:
            row["_atlas_match_cnpj"] = hit_c
            row["_atlas_match_name"] = hit_n
            row["_atlas_entity_id"] = hit_id or (f"e_cnpj_{hit_c}" if hit_c else None)
            leniencia_kb.append(row)

    # --- CEAF: consulta por nome de políticos da Casa; só aceita match exato ---
    ceaf_kb: list[dict] = []
    ceaf_raw: list[dict] = []
    seen_ceaf: set[str] = set()
    pol_queries = sorted({n for n in names if any(i.startswith(("p_cam_", "p_sen_")) for i in names[n])})
    limit_ceaf = int(os.getenv("CGU_CEAF_NOME_LIMIT", "80"))
    for q in pol_queries[:limit_ceaf]:
        rows = api_pages(f"/ceaf?nomePunido={quote(q)}", headers, 1)
        ceaf_raw.extend(rows)
        for row in rows:
            rid = str(row.get("id") or "")
            if rid in seen_ceaf:
                continue
            pes = row.get("pessoa") or {}
            pun = row.get("punicao") or {}
            nome = _norm(pes.get("nome") or pun.get("nomePunido"))
            if nome != q:
                continue  # API pode ignorar filtro — exige igualdade
            ids = [
                i
                for i in dict.fromkeys(names.get(nome) or [])
                if i.startswith(("p_cam_", "p_sen_"))
            ]
            if len(ids) == 1:
                seen_ceaf.add(rid)
                row["_atlas_entity_id"] = ids[0]
                row["_atlas_match_name"] = nome
                ceaf_kb.append(row)
        time.sleep(0.04)

    # --- CEPIM: por CNPJ já na KB (cnpjSancionado) ---
    cepim_kb: list[dict] = []
    cepim_raw: list[dict] = []
    seen_cepim: set[str] = set()
    limit_cepim = int(os.getenv("CGU_CEPIM_CNPJ_LIMIT", "80"))
    for c14 in sorted(cnpjs)[:limit_cepim]:
        rows = api_pages(f"/cepim?cnpjSancionado={c14}", headers, 1)
        for row in rows:
            rid = str(row.get("id") or "")
            if rid in seen_cepim:
                continue
            pj = row.get("pessoaJuridica") or {}
            c = only_digits(pj.get("cnpjFormatado"))
            if not c or c.zfill(14)[-14:] != c14:
                continue
            seen_cepim.add(rid)
            cepim_raw.append(row)
            row["_atlas_match_cnpj"] = c14
            row["_atlas_entity_id"] = emp_by_cnpj.get(c14) or f"e_cnpj_{c14}"
            cepim_kb.append(row)
        time.sleep(0.04)

    # --- Operações especiais (HTML público) ---
    ops_keep: list[dict] = []
    ops_raw: list[dict] = []
    try:
        r = http_get(OPS_URL, timeout=60.0)
        if r.status_code == 200:
            write_raw_record(
                source_id="cgu_portal",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=r.content,
                filename="operacoes_especiais.html",
                source_url=OPS_URL,
                dataset_id="cgu.operacoes",
                content_type="text/html",
            )
            ops_raw = parse_operacoes(r.text)
            news_limit = int(os.getenv("CGU_OPS_NEWS_LIMIT", "12"))
            news_done = 0
            enriched: list[dict] = []
            for op in ops_raw:
                op_out = dict(op)
                op_out["_atlas_mentions"] = []
                if op.get("kind") == "noticia" and news_done < news_limit:
                    news_done += 1
                    try:
                        nr = http_get(op["url"], timeout=45.0)
                        if nr.status_code == 200:
                            text = re.sub(r"<[^>]+>", " ", nr.text)
                            text = re.sub(r"\s+", " ", text)
                            op_out["_atlas_body_sample"] = text[:4000]
                            hit_c, hit_n, hit_id = match_blob(text, cnpjs, names)
                            if hit_c or hit_id:
                                op_out["_atlas_mentions"].append(
                                    {
                                        "cnpj": hit_c,
                                        "name": hit_n,
                                        "entity_id": hit_id
                                        or (f"e_cnpj_{hit_c}" if hit_c else None),
                                    }
                                )
                            try:
                                from pipelines.ops.plug_datajud_discovery import (
                                    append_text_discoveries,
                                )

                                n = append_text_discoveries(
                                    nr.text,
                                    source="cgu_legal",
                                    url=op["url"],
                                    cnpjs=cnpjs,
                                    names=names,
                                    emp_by_cnpj=emp_by_cnpj,
                                )
                                if n:
                                    op_out["_atlas_discovery_npus"] = n
                            except Exception as de:
                                print(f"discovery hook fail-soft: {de}", file=sys.stderr)
                            time.sleep(0.08)
                    except Exception as e:
                        op_out["_fetch_error"] = str(e)
                enriched.append(op_out)
            # só guarda o que cruza KB (menção nominal/CNPJ) — sem lixo órfão
            ops_keep = [o for o in enriched if o.get("_atlas_mentions")]
            # também mantém operações listadas sem menção? NÃO — política do Atlas:
            # coletar só o que liga a político/empresa já na KB.
    except Exception as e:
        print(f"ops fail: {e}", file=sys.stderr)

    write_json(out / "acordos_leniencia_raw.json", leniencia_raw)
    write_jsonl(out / "acordos_leniencia_kb.jsonl", leniencia_kb)
    write_json(out / "ceaf_raw.json", ceaf_raw)
    write_jsonl(out / "ceaf_kb.jsonl", ceaf_kb)
    write_json(out / "cepim_raw.json", cepim_raw)
    write_jsonl(out / "cepim_kb.jsonl", cepim_kb)
    write_json(out / "operacoes_raw.json", ops_raw)
    write_jsonl(out / "operacoes_kb.jsonl", ops_keep)

    for name, payload in (
        ("acordos_leniencia_raw.json", leniencia_raw),
        ("ceaf_raw.json", ceaf_raw),
        ("cepim_raw.json", cepim_raw),
    ):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        write_raw_record(
            source_id="cgu_portal",
            ingestion_run_id=run["ingestion_run_id"],
            connector_version=run["connector_version"],
            payload=raw,
            filename=name,
            source_url=BASE,
            dataset_id="cgu.legal",
            content_type="application/json",
        )

    write_manifest(
        out,
        "cgu_legal",
        [
            {"file": "acordos_leniencia_kb.jsonl", "count": len(leniencia_kb)},
            {"file": "ceaf_kb.jsonl", "count": len(ceaf_kb)},
            {"file": "cepim_kb.jsonl", "count": len(cepim_kb)},
            {"file": "operacoes_kb.jsonl", "count": len(ops_keep)},
        ],
        extra={
            "fetched_at": utc_now(),
            "ingestion_run_id": run["ingestion_run_id"],
            "leniencia_raw": len(leniencia_raw),
            "ceaf_raw": len(ceaf_raw),
            "cepim_raw": len(cepim_raw),
            "operacoes_raw": len(ops_raw),
        },
    )
    mark_ingested(
        "cgu_portal",
        run_id=run["ingestion_run_id"],
        counts={
            "leniencia_kb": len(leniencia_kb),
            "ceaf_kb": len(ceaf_kb),
            "cepim_kb": len(cepim_kb),
            "operacoes_kb": len(ops_keep),
        },
    )
    print(
        f"OK CGU legal: leniencia={len(leniencia_kb)}/{len(leniencia_raw)} "
        f"ceaf={len(ceaf_kb)}/{len(ceaf_raw)} cepim={len(cepim_kb)}/{len(cepim_raw)} "
        f"ops={len(ops_keep)}/{len(ops_raw)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
