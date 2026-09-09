#!/usr/bin/env python3
"""
CEAPS — Cotas para Exercício da Atividade Parlamentar (Senado).

Fonte anual:
  https://www.senado.gov.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv

Atualiza gold: despesas_resumo + fornecedores + pagou_despesa_parlamentar_a
para pessoas p_sen_*.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
import unicodedata
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
BASE = "https://www.senado.gov.br/transparencia/LAI/verba"


def anos() -> list[int]:
    raw = os.getenv("CEAPS_ANOS", os.getenv("COTA_ANOS", "")).strip()
    if raw:
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]
    y = datetime.now().year
    return [y - 1, y]


def norm_name(s: str | None) -> str:
    s = (s or "").upper()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def only_digits(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def money(s: str | None) -> float:
    if s is None or s == "":
        return 0.0
    t = str(s).strip()
    if "," in t and t.rfind(",") > t.rfind("."):
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def download_ano(ano: int) -> bytes | None:
    url = f"{BASE}/despesa_ceaps_{ano}.csv"
    try:
        req = Request(url, headers={"User-Agent": "AtlasBrasil/1.0"})
        with urlopen(req, timeout=180) as r:
            return r.read()
    except Exception as e:
        print(f"  fail download {ano}: {e}", file=sys.stderr)
        return None


def parse_csv(raw: bytes) -> list[dict]:
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("latin-1", errors="replace")
    # primeira linha costuma ser ULTIMA ATUALIZACAO
    lines = text.splitlines()
    if lines and "ULTIMA ATUALIZACAO" in lines[0].upper():
        lines = lines[1:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=";")
    return [row for row in reader if row]


def load_senadores() -> tuple[dict[str, str], dict[str, list[tuple[str, str]]]]:
    """exact nome_norm -> pid ; sobrenome -> [(nome_norm, pid)]"""
    if not GOLD.exists():
        return {}, {}
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    exact: dict[str, str] = {}
    by_sobre: dict[str, list[tuple[str, str]]] = {}
    for e in kb.get("entidades") or []:
        if not str(e.get("id") or "").startswith("p_sen_"):
            continue
        pid = e["id"]
        names = [norm_name(e.get("nome"))]
        names.extend(norm_name(a) for a in (e.get("aliases") or []))
        for nn in names:
            if not nn:
                continue
            exact[nn] = pid
            sobre = nn.split()[-1]
            by_sobre.setdefault(sobre, []).append((nn, pid))
    return exact, by_sobre


def match_senador(
    nome_csv: str,
    exact: dict[str, str],
    by_sobre: dict[str, list[tuple[str, str]]],
) -> str | None:
    nn = norm_name(nome_csv)
    if not nn:
        return None
    if nn in exact:
        return exact[nn]
    ta = set(nn.split())
    sobre = nn.split()[-1]
    cands = by_sobre.get(sobre) or []
    hits: list[str] = []
    for pessoa_nn, pid in cands:
        tb = set(pessoa_nn.split())
        if ta <= tb or tb <= ta:
            hits.append(pid)
            continue
        # prenome curto CEAPS + sobrenome (ex.: HAMILTON MOURAO ⊂ ANTONIO HAMILTON … MOURAO)
        if sobre in tb and len(ta & tb) >= 1:
            hits.append(pid)
    hits = list(dict.fromkeys(hits))
    if len(hits) == 1:
        return hits[0]
    # desempate: mais tokens em comum
    if hits:
        scored = []
        for pid in hits:
            # recupera nome
            for pessoa_nn, p2 in cands:
                if p2 == pid:
                    scored.append((len(ta & set(pessoa_nn.split())), pid))
                    break
        scored.sort(reverse=True)
        if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return scored[0][1]
    return None


def aggregate(
    rows: list[dict],
    exact: dict[str, str],
    by_sobre: dict[str, list[tuple[str, str]]],
) -> tuple[dict[str, dict], int, int]:
    by: dict[str, dict[int, dict]] = defaultdict(
        lambda: defaultdict(
            lambda: {
                "total": 0.0,
                "qtd": 0,
                "por_tipo": defaultdict(float),
                "por_forn": {},
            }
        )
    )
    n_matched = 0
    n_skip = 0
    for row in rows:
        pid = match_senador(row.get("SENADOR") or "", exact, by_sobre)
        if not pid:
            n_skip += 1
            continue
        n_matched += 1
        try:
            ano = int(float(str(row.get("ANO") or "0")))
        except ValueError:
            continue
        if not ano:
            continue
        v = money(row.get("VALOR_REEMBOLSADO"))
        tipo = (row.get("TIPO_DESPESA") or "Outros").strip()
        nome_f = (row.get("FORNECEDOR") or "").strip()
        cnpj = only_digits(row.get("CNPJ_CPF"))
        slot = by[pid][ano]
        slot["total"] += v
        slot["qtd"] += 1
        slot["por_tipo"][tipo] += v
        if len(cnpj) >= 11 or nome_f:
            key = cnpj if len(cnpj) >= 11 else f"nome:{nome_f.upper()}"
            forn = slot["por_forn"].setdefault(
                key,
                {
                    "cnpj": cnpj if len(cnpj) in (11, 14) else None,
                    "nome": nome_f or None,
                    "valor": 0.0,
                    "qtd": 0,
                },
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
                    "fonte": "senado_ceaps",
                    "fonte_url": f"{BASE}/despesa_ceaps_{ano}.csv",
                    "completo": True,
                }
            )
        escolhido = next(
            (d for d in reversed(por_ano) if d.get("qtd_lancamentos")),
            por_ano[-1] if por_ano else None,
        )
        out[pid] = {"despesas": escolhido, "despesas_por_ano": por_ano}
    return out, n_matched, n_skip


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
        did = f"doc_ceaps_{pid}_{desp.get('ano')}"
        docs[did] = {
            "id": did,
            "tipo": "dados_abertos",
            "titulo": f"CEAPS {desp.get('ano')} (Senado)",
            "nivel_fonte": "1_primaria",
            "orgao": "senado",
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
                    "tags": ["coletado", "despesa_parlamentar", "ceaps"],
                    "cnpj": cnpj if len(cnpj) == 14 else None,
                    "source_ids": [f"ceaps:{cnpj or nome_f}"],
                }
            else:
                if nome_f and str(ents[emp_id].get("nome") or "").startswith("CNPJ"):
                    ents[emp_id]["nome"] = nome_f
                tags_e = list(ents[emp_id].get("tags") or [])
                if "ceaps" not in tags_e:
                    tags_e.append("ceaps")
                ents[emp_id]["tags"] = tags_e
            rid = f"r_{pid}_{emp_id}_ceaps_forn"
            rels[rid] = {
                "id": rid,
                "origem": pid,
                "destino": emp_id,
                "tipo": "pagou_despesa_parlamentar_a",
                "periodo": str(desp.get("ano") or ""),
                "contexto": f"CEAPS {desp.get('ano')}",
                "justificativa_documental": (
                    f"Fornecedor CEAPS ({desp.get('ano')}): "
                    f"{nome_f or cnpj} · R$ {forn.get('valor')}"
                ),
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [did],
                "fontes": ["senado_ceaps"],
                "nota": "Pagamento de cota parlamentar (Senado) — não implica irregularidade.",
            }
            n_f += 1
            if "tem_fornecedor_cota" not in tags:
                tags.append("tem_fornecedor_cota")
        if "tem_ceaps" not in tags:
            tags.append("tem_ceaps")
        e["tags"] = tags

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["ceaps_gold"] = {
        "em": utc_now(),
        "pessoas": n_p,
        "rels_fornecedor": n_f,
    }
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    return n_p, n_f


def main() -> int:
    run = start_run("senado_ceaps", "senado.ceaps")
    out = bronze_dir("senado_ceaps")
    exact, by_sobre = load_senadores()
    print(f"senadores gold: {len(exact)} nomes · anos={anos()}")

    all_rows: list[dict] = []
    for ano in anos():
        print(f"baixando CEAPS {ano} …", flush=True)
        raw = download_ano(ano)
        if not raw:
            continue
        (out / f"despesa_ceaps_{ano}.csv").write_bytes(raw)
        write_json(
            out / f"meta_{ano}.json",
            {
                "ano": ano,
                "sha1": sha1_bytes(raw),
                "bytes": len(raw),
                "url": f"{BASE}/despesa_ceaps_{ano}.csv",
                "fetched_at": utc_now(),
            },
        )
        rows = parse_csv(raw)
        print(f"  {ano}: {len(rows)} linhas")
        all_rows.extend(rows)

    write_jsonl(out / "lancamentos_sample.jsonl", all_rows[:50])
    write_manifest(
        out,
        "senado_ceaps",
        [{"anos": anos(), "linhas": len(all_rows)}],
        extra={"ingestion_run_id": run["ingestion_run_id"]},
    )

    if not all_rows:
        print("CEAPS vazio", file=sys.stderr)
        mark_ingested("senado_ceaps", run_id=run["ingestion_run_id"], counts={}, ok=False)
        return 1

    agg, n_matched, n_skip = aggregate(all_rows, exact, by_sobre)
    print(f"match linhas={n_matched} skip={n_skip} pessoas={len(agg)}")
    n_p, n_f = patch_gold(agg)
    mark_ingested(
        "senado_ceaps",
        run_id=run["ingestion_run_id"],
        counts={"linhas": len(all_rows), "pessoas": n_p, "fornecedores": n_f},
        ok=True,
    )
    print(f"OK CEAPS: pessoas={n_p} forn_rels={n_f}")
    return 0 if n_p else 1


if __name__ == "__main__":
    raise SystemExit(main())
