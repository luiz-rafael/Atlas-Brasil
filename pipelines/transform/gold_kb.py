#!/usr/bin/env python3
"""
Silver -> gold KB (entidades + relações + documentos).
Entity resolution entre Câmara / Senado / TSE por nome normalizado + UF + partido.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json  # noqa: E402

SILVER_LATEST = LAKE / "silver" / "politicos" / "politicos_latest.jsonl"
GOLD_DIR = LAKE / "gold"
OUT_KB = ROOT / "data" / "atlas-brasil-kb-gold.json"
REPORT = ROOT / "pipelines" / "reports" / "onda1_coverage.json"


def _norm_name(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    # remove partículas comuns
    stop = {"de", "da", "do", "das", "dos", "e"}
    parts = [p for p in re.split(r"\s+", s) if p and p not in stop]
    return " ".join(parts)


def _doc_id(source: str, url: str) -> str:
    h = hashlib.sha1(f"{source}|{url}".encode()).hexdigest()[:12]
    return f"doc_{source}_{h}"


def load_silver() -> list[dict]:
    if not SILVER_LATEST.exists():
        return []
    rows = []
    for line in SILVER_LATEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def resolve_clusters(rows: list[dict]) -> list[list[dict]]:
    """Agrupa registros que parecem a mesma pessoa."""
    # índice por (norm_name, uf)
    by_key: dict[tuple[str, str | None], list[dict]] = defaultdict(list)
    for r in rows:
        key = (_norm_name(r.get("nome") or ""), r.get("uf"))
        if not key[0]:
            continue
        by_key[key].append(r)

    clusters: list[list[dict]] = []
    used = set()

    # 1) mesmo nome+UF: fundir fontes diferentes
    for key, group in by_key.items():
        fontes = {g["fonte"] for g in group}
        if len(group) == 1:
            continue
        # se há cam+sen ou cam+tse etc, cluster
        if len(fontes) > 1 or len(group) > 1:
            clusters.append(group)
            for g in group:
                used.add(id(g))

    # 2) fuzzy só entre casas legislativas (mais confiável)
    legis = [r for r in rows if r["fonte"] in ("camara_v2", "senado_legis") and id(r) not in used]
    for i, a in enumerate(legis):
        if id(a) in used:
            continue
        cluster = [a]
        used.add(id(a))
        na = _norm_name(a["nome"])
        for b in legis[i + 1 :]:
            if id(b) in used:
                continue
            if a.get("uf") and b.get("uf") and a["uf"] != b["uf"]:
                continue
            nb = _norm_name(b["nome"])
            if na == nb or SequenceMatcher(None, na, nb).ratio() >= 0.94:
                # partido ajuda
                pa, pb = a.get("partido_sigla"), b.get("partido_sigla")
                if pa and pb and pa != pb and SequenceMatcher(None, na, nb).ratio() < 0.98:
                    continue
                cluster.append(b)
                used.add(id(b))
        clusters.append(cluster)

    # 3) restantes sozinhos
    for r in rows:
        if id(r) not in used:
            clusters.append([r])
            used.add(id(r))

    return clusters


def pick_canonical_id(cluster: list[dict]) -> str:
    # preferência: camara > senado > tse
    order = {"camara_v2": 0, "senado_legis": 1, "tse_ckan": 2, "tse_divulga": 3}
    best = sorted(cluster, key=lambda r: order.get(r["fonte"], 9))[0]
    ext = best["id_externo"]
    if ext.startswith("cam:"):
        return f"p_cam_{ext.split(':', 1)[1]}"
    if ext.startswith("sen:"):
        return f"p_sen_{ext.split(':', 1)[1]}"
    if ext.startswith("tse:"):
        return f"p_tse_{ext.split(':', 1)[1]}"
    return f"p_{hashlib.sha1(ext.encode()).hexdigest()[:12]}"


def build_gold(rows: list[dict]) -> dict:
    clusters = resolve_clusters(rows)
    entidades = []
    relacoes = []
    documentos = []
    doc_seen = set()
    partidos: dict[str, dict] = {}

    for cluster in clusters:
        pid = pick_canonical_id(cluster)
        # preferir registro em exercício com cargo legislativo
        primary = sorted(
            cluster,
            key=lambda r: (
                0 if r["fonte"] in ("camara_v2", "senado_legis") else 1,
                0 if r.get("cargo") else 1,
            ),
        )[0]
        aliases = []
        source_ids = []
        tags = ["coletado", "onda1"]
        for r in cluster:
            source_ids.append(r["id_externo"])
            if r.get("nome_urna") and r["nome_urna"] != primary.get("nome"):
                aliases.append(r["nome_urna"])
            if r.get("nome") and r["nome"] != primary.get("nome"):
                aliases.append(r["nome"])
            url = r.get("url_fonte")
            if url:
                did = _doc_id(r["fonte"], url)
                if did not in doc_seen:
                    doc_seen.add(did)
                    documentos.append(
                        {
                            "id": did,
                            "tipo": "dados_abertos",
                            "titulo": f"Fonte {r['fonte']}: {r.get('nome')}",
                            "data": (r.get("fetched_at") or "")[:10],
                            "nivel_fonte": "1_primaria",
                            "orgao": r["fonte"],
                            "url": url,
                            "casos": [],
                        }
                    )

        sigla = primary.get("partido_sigla")
        if sigla:
            tags.append(f"partido:{sigla}")
            pt_id = f"pt_{sigla}"
            if pt_id not in partidos:
                partidos[pt_id] = {
                    "id": pt_id,
                    "tipo": "partido",
                    "nome": sigla,
                    "tags": ["coletado", "onda1"],
                    "aliases": [],
                    "source_ids": [],
                    "no_poder_2026": True,
                }

        cargo = primary.get("cargo")
        if primary.get("fonte") == "camara_v2":
            no_poder = bool(primary.get("em_exercicio"))
        elif primary.get("fonte") == "senado_legis":
            no_poder = True
        else:
            no_poder = False

        entidades.append(
            {
                "id": pid,
                "tipo": "pessoa",
                "nome": primary.get("nome") or primary.get("nome_urna") or pid,
                "partido": sigla,
                "cargo_atual": cargo,
                "uf": primary.get("uf"),
                "tags": list(dict.fromkeys(tags)),
                "aliases": list(dict.fromkeys(aliases))[:12],
                "source_ids": source_ids,
                "no_poder_2026": bool(no_poder),
                "isolada": False,
                "foto_url": next((r.get("url_foto") for r in cluster if r.get("url_foto")), None),
                "email": next((r.get("email") for r in cluster if r.get("email")), None),
                "pagina_oficial": primary.get("url_fonte"),
                "data_nascimento": primary.get("data_nascimento"),
                "sexo": primary.get("sexo"),
            }
        )

        # relação filiação partido
        if sigla:
            pt_id = f"pt_{sigla}"
            fonte_docs = [
                _doc_id(r["fonte"], r["url_fonte"])
                for r in cluster
                if r.get("url_fonte")
            ]
            if not fonte_docs:
                fonte_docs = [f"doc_meta_{pid}"]
            rid = f"r_{pid}_{pt_id}_filiado"
            relacoes.append(
                {
                    "id": rid,
                    "origem": pid,
                    "destino": pt_id,
                    "tipo": "filiado_a",
                    "periodo": str(primary.get("eleicao_ano") or primary.get("legislatura") or ""),
                    "contexto": f"Filiação/legenda declarada em dados abertos ({primary['fonte']})",
                    "justificativa_documental": (
                        f"Registro oficial em {primary['fonte']} lista partido {sigla} "
                        f"para {primary.get('nome')}"
                    ),
                    "grau_confirmacao": "fato_documentado",
                    "fonte_ids": list(dict.fromkeys(fonte_docs))[:8],
                    "fontes": [primary["fonte"]],
                }
            )

        # relação exerce cargo / instituição
        if cargo and no_poder:
            casa = "inst_camara" if primary["fonte"] == "camara_v2" else "inst_senado"
            rid = f"r_{pid}_{casa}_mandato"
            fonte_docs = [
                _doc_id(r["fonte"], r["url_fonte"])
                for r in cluster
                if r.get("url_fonte")
            ]
            relacoes.append(
                {
                    "id": rid,
                    "origem": pid,
                    "destino": casa,
                    "tipo": "exerce_cargo",
                    "periodo": str(primary.get("legislatura") or "atual"),
                    "contexto": cargo,
                    "justificativa_documental": (
                        f"Mandato atual listado em {primary['fonte']} como {cargo}"
                    ),
                    "grau_confirmacao": "fato_documentado",
                    "fonte_ids": list(dict.fromkeys(fonte_docs))[:8],
                    "fontes": [primary["fonte"]],
                }
            )

    # instituições Casa
    entidades.extend(
        [
            {
                "id": "inst_camara",
                "tipo": "instituicao",
                "nome": "Câmara dos Deputados",
                "uf": "DF",
                "tags": ["coletado", "onda1", "poder_legislativo"],
                "aliases": ["Camara"],
                "source_ids": ["camara_v2"],
                "no_poder_2026": True,
            },
            {
                "id": "inst_senado",
                "tipo": "instituicao",
                "nome": "Senado Federal",
                "uf": "DF",
                "tags": ["coletado", "onda1", "poder_legislativo"],
                "aliases": ["Senado"],
                "source_ids": ["senado_legis"],
                "no_poder_2026": True,
            },
            {
                "id": "inst_tse",
                "tipo": "instituicao",
                "nome": "Tribunal Superior Eleitoral",
                "uf": "DF",
                "tags": ["coletado", "onda1"],
                "aliases": ["TSE"],
                "source_ids": ["tse_ckan"],
                "no_poder_2026": True,
            },
        ]
    )
    entidades.extend(partidos.values())

    # docs meta fallback
    for r in relacoes:
        for fid in r.get("fonte_ids") or []:
            if fid.startswith("doc_meta_") and fid not in doc_seen:
                doc_seen.add(fid)
                documentos.append(
                    {
                        "id": fid,
                        "tipo": "metadado_coleta",
                        "titulo": "Proveniência interna da coleta Onda 1",
                        "nivel_fonte": "1_primaria",
                        "orgao": "atlas_pipeline",
                        "url": "https://dadosabertos.camara.leg.br/api/v2",
                    }
                )

    kb = {
        "meta": {
            "versao": "5.0.0-gold",
            "nome": "ATLAS BRASIL Knowledge Base (coletada)",
            "produto": "ATLAS BRASIL",
            "gerado_em": utc_now(),
            "pipeline": "onda1_oficial",
            "fontes": sorted({r["fonte"] for r in rows}),
            "regra_ouro": "Nenhuma relação no grafo sem justificativa documental.",
            "aviso": "Status e mandatos vêm de dados abertos oficiais. Path ≠ culpa.",
            "alimenta": ["site", "api", "grafo", "timeline", "busca"],
        },
        "entidades": entidades,
        "relacoes": relacoes,
        "documentos": documentos,
        "casos": [],
        "timeline": [],
        "registros_pessoa_caso": [],
        "fluxos_financeiros": [],
    }
    return kb, clusters


def main() -> int:
    rows = load_silver()
    if not rows:
        print("silver vazio — rode silver_politicos.py primeiro", file=sys.stderr)
        return 1

    kb, clusters = build_gold(rows)
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    write_json(GOLD_DIR / "kb.json", kb)
    write_json(OUT_KB, kb)

    pessoas = [e for e in kb["entidades"] if e["tipo"] == "pessoa"]
    partidos = [e for e in kb["entidades"] if e["tipo"] == "partido"]
    report = {
        "gerado_em": utc_now(),
        "silver_rows": len(rows),
        "clusters": len(clusters),
        "pessoas": len(pessoas),
        "partidos": len(partidos),
        "relacoes": len(kb["relacoes"]),
        "documentos": len(kb["documentos"]),
        "por_fonte_silver": {},
        "por_cargo": {},
        "gold_path": str(OUT_KB),
    }
    for r in rows:
        report["por_fonte_silver"][r["fonte"]] = report["por_fonte_silver"].get(r["fonte"], 0) + 1
    for e in pessoas:
        c = e.get("cargo_atual") or "?"
        report["por_cargo"][c] = report["por_cargo"].get(c, 0) + 1

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    write_json(REPORT, report)
    print(f"OK gold: {len(pessoas)} pessoas, {len(kb['relacoes'])} relações -> {OUT_KB}")
    print(f"relatório -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
