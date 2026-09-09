#!/usr/bin/env python3
"""
Despesas da cota parlamentar via arquivo anual da Câmara (recomendado oficialmente).

Fonte: https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip
Mais estável que /deputados/{id}/despesas (API frequentemente vazia/lenta).

Gera bronze/camara_despesas_bulk/ e atualiza perfis_enriquecidos + gold
(despesas_resumo + fornecedores + relações pessoa→empresa).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    LAKE,
    bronze_dir,
    sha1_bytes,
    utc_now,
    write_json,
    write_jsonl,
    write_manifest,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"
BASE = "https://www.camara.leg.br/cotas"


def anos() -> list[int]:
    raw = os.getenv("COTA_ANOS", "").strip()
    if raw:
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]
    y = datetime.now().year
    return [y - 1, y]


def download_ano(ano: int) -> bytes | None:
    url = f"{BASE}/Ano-{ano}.csv.zip"
    try:
        req = Request(url, headers={"User-Agent": "AtlasBrasil/1.0"})
        with urlopen(req, timeout=120) as r:
            return r.read()
    except Exception as e:
        print(f"  fail download {ano}: {e}", file=sys.stderr)
        return None


def parse_zip(raw: bytes) -> list[dict]:
    out: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            return out
        with zf.open(names[0]) as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace")
            # CSV Câmara usa ; 
            reader = csv.DictReader(text, delimiter=";")
            for row in reader:
                out.append(row)
    return out


def only_digits(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def money(s: str | None) -> float:
    """Arquivo anual da Câmara usa ponto decimal (ex.: 2247.42)."""
    if s is None or s == "":
        return 0.0
    t = str(s).strip()
    # formato BR: 1.234.567,89
    if "," in t and t.rfind(",") > t.rfind("."):
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def aggregate(rows: list[dict], wanted_ids: set[str]) -> dict[str, dict]:
    """person_id -> despesas_resumo por ano (escolhe melhor ano)."""
    by: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {
        "total": 0.0,
        "qtd": 0,
        "por_tipo": defaultdict(float),
        "por_forn": {},
    }))
    for row in rows:
        ide = only_digits(row.get("ideCadastro") or row.get("idDeputado") or "")
        if not ide:
            continue
        pid = f"p_cam_{ide}"
        if wanted_ids and pid not in wanted_ids:
            continue
        try:
            ano = int(float(str(row.get("numAno") or row.get("ano") or "0")))
        except ValueError:
            continue
        if not ano:
            continue
        v = money(row.get("vlrLiquido") or row.get("vlrDocumento"))
        tipo = (row.get("txtDescricao") or row.get("tipoDespesa") or "Outros").strip()
        nome_f = (row.get("txtFornecedor") or row.get("nomeFornecedor") or "").strip()
        cnpj = only_digits(row.get("txtCNPJCPF") or row.get("cnpjCpfFornecedor"))
        slot = by[pid][ano]
        slot["total"] += v
        slot["qtd"] += 1
        slot["por_tipo"][tipo] += v
        if len(cnpj) >= 11 or nome_f:
            key = cnpj if len(cnpj) >= 11 else f"nome:{nome_f.upper()}"
            forn = slot["por_forn"].setdefault(
                key,
                {"cnpj": cnpj if len(cnpj) in (11, 14) else None, "nome": nome_f or None, "valor": 0.0, "qtd": 0},
            )
            if nome_f and not forn.get("nome"):
                forn["nome"] = nome_f
            forn["valor"] += v
            forn["qtd"] += 1

    out: dict[str, dict] = {}
    for pid, anos_map in by.items():
        por_ano = []
        for ano, s in sorted(anos_map.items()):
            top_tipo = sorted(s["por_tipo"].items(), key=lambda x: -x[1])[:8]
            top_forn = sorted(s["por_forn"].values(), key=lambda x: -x["valor"])[:12]
            for f in top_forn:
                f["valor"] = round(f["valor"], 2)
            por_ano.append(
                {
                    "ano": ano,
                    "total": round(s["total"], 2),
                    "qtd_lancamentos": s["qtd"],
                    "por_tipo": [{"tipo": t, "valor": round(v, 2)} for t, v in top_tipo],
                    "fornecedores": top_forn,
                    "fonte_url": f"{BASE}/Ano-{ano}.csv.zip",
                    "completo": True,
                }
            )
        escolhido = next((d for d in reversed(por_ano) if d.get("qtd_lancamentos")), por_ano[-1] if por_ano else None)
        out[pid] = {"despesas": escolhido, "despesas_por_ano": por_ano}
    return out


def patch_gold(agg: dict[str, dict]) -> tuple[int, int]:
    if not GOLD.exists():
        return 0, 0
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}
    n_p = 0
    n_f = 0
    for pid, block in agg.items():
        e = ents.get(pid)
        if not e:
            continue
        desp = block.get("despesas")
        if not desp:
            continue
        e["despesas_resumo"] = desp
        e["despesas_por_ano"] = block.get("despesas_por_ano")
        n_p += 1
        fonte = desp.get("fonte_url") or BASE
        did = f"doc_cota_{pid}_{desp.get('ano')}"
        docs[did] = {
            "id": did,
            "tipo": "dados_abertos",
            "titulo": f"Cota parlamentar {desp.get('ano')} (arquivo anual Câmara)",
            "nivel_fonte": "1_primaria",
            "orgao": "camara",
            "url": fonte,
            "casos": [],
        }
        tags = list(e.get("tags") or [])
        for forn in desp.get("fornecedores") or []:
            cnpj = only_digits(forn.get("cnpj"))
            nome_f = (forn.get("nome") or "").strip()
            if len(cnpj) == 14:
                emp_id = f"e_cnpj_{cnpj}"
            elif nome_f:
                emp_id = f"e_nome_{hashlib.sha1(nome_f.upper().encode()).hexdigest()[:12]}"
            else:
                continue
            if emp_id not in ents:
                ents[emp_id] = {
                    "id": emp_id,
                    "tipo": "empresa",
                    "nome": nome_f or f"CNPJ {cnpj}",
                    "tags": ["coletado", "despesa_parlamentar", "cota_bulk"],
                    "cnpj": cnpj if len(cnpj) == 14 else None,
                    "source_ids": [f"cota:{cnpj or nome_f}"],
                }
            else:
                if nome_f and str(ents[emp_id].get("nome") or "").startswith("CNPJ"):
                    ents[emp_id]["nome"] = nome_f
            rid = f"r_{pid}_{emp_id}_desp_forn"
            rels[rid] = {
                "id": rid,
                "origem": pid,
                "destino": emp_id,
                "tipo": "pagou_despesa_parlamentar_a",
                "periodo": str(desp.get("ano") or ""),
                "contexto": f"Cota parlamentar {desp.get('ano')}",
                "justificativa_documental": (
                    f"Fornecedor no arquivo anual da cota ({desp.get('ano')}): "
                    f"{nome_f or cnpj} · R$ {forn.get('valor')}"
                ),
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [did],
                "fontes": ["camara_cotas_anuais"],
                "nota": "Pagamento de cota parlamentar — não implica irregularidade.",
            }
            n_f += 1
            if "tem_fornecedor_cota" not in tags:
                tags.append("tem_fornecedor_cota")
        e["tags"] = tags

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["camara_cotas_bulk"] = {
        "em": utc_now(),
        "pessoas": n_p,
        "rels_fornecedor": n_f,
        "anos": anos(),
    }
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    return n_p, n_f


def main() -> int:
    run = start_run("camara_despesas_bulk", "camara.cotas.anuais")
    out = bronze_dir("camara_despesas_bulk")
    wanted: set[str] = set()
    if GOLD.exists():
        kb = json.loads(GOLD.read_text(encoding="utf-8"))
        for e in kb.get("entidades") or []:
            if e.get("id", "").startswith("p_cam_"):
                wanted.add(e["id"])

    all_rows: list[dict] = []
    files_meta = []
    for ano in anos():
        print(f"baixando Ano-{ano}.csv.zip …", flush=True)
        raw = download_ano(ano)
        if not raw:
            continue
        (out / f"Ano-{ano}.csv.zip").write_bytes(raw)
        files_meta.append({"file": f"Ano-{ano}.csv.zip", "bytes": len(raw), "sha1": sha1_bytes(raw)})
        rows = parse_zip(raw)
        print(f"  {ano}: {len(rows)} linhas", flush=True)
        all_rows.extend(rows)

    agg = aggregate(all_rows, wanted)
    write_json(out / "despesas_por_pessoa.json", {k: v for k, v in list(agg.items())[:5]})
    write_jsonl(
        out / "despesas_por_pessoa.jsonl",
        [{"person_id": k, **v} for k, v in agg.items()],
    )
    write_manifest(out, "camara_despesas_bulk", files_meta, extra={"pessoas": len(agg), "anos": anos()})
    mark_ingested(
        "camara_despesas_bulk",
        run_id=run["ingestion_run_id"],
        counts={"pessoas": len(agg), "linhas": len(all_rows)},
        ok=True,
    )

    # mescla no bronze de perfis (se existir) sem apagar outros campos
    day_dirs = sorted((LAKE / "bronze" / "perfis_enriquecidos").glob("*"), reverse=True)
    for d in day_dirs:
        if d.is_dir() and (d / "perfis.jsonl").exists():
            perfis = []
            for line in (d / "perfis.jsonl").read_text(encoding="utf-8").splitlines():
                if line.strip():
                    perfis.append(json.loads(line))
            by = {p["entity_id"]: p for p in perfis if p.get("entity_id")}
            for pid, block in agg.items():
                p = by.setdefault(pid, {"entity_id": pid, "fetched_at": utc_now(), "fontes": []})
                p["despesas"] = block["despesas"]
                p["despesas_por_ano"] = block["despesas_por_ano"]
                fonte = (block.get("despesas") or {}).get("fonte_url")
                if fonte and fonte not in (p.get("fontes") or []):
                    p.setdefault("fontes", []).append(fonte)
            write_jsonl(d / "perfis.jsonl", list(by.values()))
            print(f"perfis bronze atualizados: {d}")
            break

    n_p, n_f = patch_gold(agg)
    print(f"OK camara_despesas_bulk: pessoas={len(agg)} gold_patch={n_p} forn_rels={n_f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
