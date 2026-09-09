#!/usr/bin/env python3
"""
Gold: proposições + autoria + resumo legislativo/frequência/remuneração no perfil.
Não cria aresta por voto (volume); votos ficam agregados + silver.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    if not GOLD.exists():
        print("gold ausente", file=sys.stderr)
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}

    sil = LAKE / "silver" / "legislativo"
    props = load_jsonl(sil / "proposicoes_latest.jsonl")
    autores = load_jsonl(sil / "autores_latest.jsonl")
    resumos = load_jsonl(sil / "resumo_pessoa_latest.jsonl")
    rem_path = sil / "remuneracao_macro.json"
    rem = json.loads(rem_path.read_text(encoding="utf-8")) if rem_path.exists() else {}
    series = rem.get("series") or []

    n_prop = 0
    n_aut = 0
    max_props = int(os.getenv("LEG_GOLD_MAX_PROPS", "25000"))

    for p in props[:max_props]:
        raw_id = str(p.get("id_proposicao") or "")
        if not raw_id:
            continue
        hid = hashlib.sha1(raw_id.encode()).hexdigest()[:12]
        eid = f"prop_{hid}"
        nome = f"{p.get('sigla_tipo') or 'PROP'} {p.get('numero') or ''}/{p.get('ano') or ''}".strip()
        ents[eid] = {
            "id": eid,
            "tipo": "proposicao",
            "nome": nome[:160],
            "tags": ["coletado", "legislativo", p.get("casa") or ""],
            "ementa": p.get("ementa"),
            "sigla_tipo": p.get("sigla_tipo"),
            "numero": p.get("numero"),
            "ano": p.get("ano"),
            "casa": p.get("casa"),
            "uri": p.get("uri"),
            "source_ids": [f"prop:{raw_id}"],
            "id_externo": raw_id,
        }
        n_prop += 1

    prop_by_ext = {e.get("id_externo"): e["id"] for e in ents.values() if e.get("tipo") == "proposicao"}

    for a in autores:
        pid = a.get("person_id")
        ext = str(a.get("id_proposicao") or "")
        prop_id = prop_by_ext.get(ext)
        if not pid or pid not in ents or not prop_id:
            continue
        rid = f"r_{pid}_{prop_id}_autor"
        rels[rid] = {
            "id": rid,
            "origem": pid,
            "destino": prop_id,
            "tipo": "autor_de_proposicao",
            "periodo": str(a.get("ano") or ""),
            "contexto": a.get("casa"),
            "justificativa_documental": "Autoria registrada nos dados abertos da Casa Legislativa",
            "grau_confirmacao": "fato_documentado",
            "fonte_ids": [],
            "fontes": ["camara_legislativo" if a.get("casa") == "camara" else "senado_legislativo"],
        }
        n_aut += 1

    # remuneração macro index
    rem_idx: dict[tuple[str, int], dict] = {}
    for s in series:
        try:
            rem_idx[(s["cargo"], int(s["ano"]))] = s
        except Exception:
            continue

    n_perf = 0
    for r in resumos:
        pid = r.get("person_id")
        if not pid or pid not in ents:
            continue
        pessoa = ents[pid]
        freq = r.get("frequencia") or {}
        cargo = "deputado_federal" if pid.startswith("p_cam_") else "senador"
        # série salarial do cargo
        hist = [rem_idx[k] for k in sorted(rem_idx) if k[0] == cargo]
        pessoa["legislativo_resumo"] = {
            "qtd_proposicoes": r.get("qtd_proposicoes") or 0,
            "qtd_projetos": r.get("qtd_projetos") or 0,
            "por_tipo": r.get("por_tipo") or {},
            "proposicoes_sample": (r.get("proposicoes_sample") or [])[:12],
            "proposicoes_lista": (r.get("proposicoes_lista") or r.get("proposicoes_sample") or [])[
                :80
            ],
            "proposicao_ids": (r.get("proposicao_ids") or [])[:80],
            "votacoes_nominais": freq.get("total_votacoes_nominais") or 0,
            "votos_registrados": freq.get("votos_registrados"),
            "presente": freq.get("presente") or 0,
            "ausente": freq.get("ausente") or 0,
            "taxa_presenca": freq.get("taxa_presenca"),
            "metodo_presenca": freq.get("metodo_presenca"),
            "aviso_presenca": freq.get("aviso_presenca"),
            "por_voto": freq.get("por_voto") or {},
            "por_ano": freq.get("por_ano") or {},
            "votos_projetos": (freq.get("amostra_votos_projetos") or [])[:24],
            "votos_por_proposicao": (freq.get("votos_por_proposicao") or [])[:30],
            "ano_inicio_atividade": r.get("ano_inicio_atividade"),
            "ano_fim_atividade": r.get("ano_fim_atividade"),
            "anos_atividade": r.get("anos_atividade"),
            "atualizado_em": utc_now(),
        }
        pessoa["remuneracao"] = {
            "cargo": cargo,
            "serie_subsidio": [
                {
                    "ano": s["ano"],
                    "subsidio_mensal": s["subsidio_mensal"],
                    "fonte_url": s.get("fonte_url"),
                    "nota": s.get("nota"),
                }
                for s in hist
            ],
            "aviso": (rem.get("cobertura") or {}).get("aviso"),
            "micro_holerite": False,
            "frequencia_fonte": "votacoes_nominais",
        }
        tags = list(pessoa.get("tags") or [])
        if "tem_legislativo" not in tags:
            tags.append("tem_legislativo")
        pessoa["tags"] = tags
        n_perf += 1

    # documento âncora
    did = "doc_legislativo_casas"
    docs[did] = {
        "id": did,
        "tipo": "dados_abertos",
        "titulo": "Proposicoes e votações — Câmara/Senado Dados Abertos",
        "nivel_fonte": "1_primaria",
        "orgao": "camara_senado",
        "url": "https://dadosabertos.camara.leg.br/",
        "casos": [],
    }

    # macro no meta (visão nacional)
    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["legislativo"] = {
        "em": utc_now(),
        "proposicoes": n_prop,
        "autorias": n_aut,
        "perfis": n_perf,
        "remuneracao_macro_pontos": len(series),
    }
    kb.setdefault("meta", {})["remuneracao_macro"] = {
        "series": series,
        "cobertura": rem.get("cobertura"),
        "em": utc_now(),
    }

    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)

    print(f"OK gold legislativo: props={n_prop} autorias={n_aut} perfis={n_perf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
