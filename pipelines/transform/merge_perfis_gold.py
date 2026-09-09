#!/usr/bin/env python3
"""Aplica bronze/perfis_enriquecidos no gold atual (patch seguro, sem recoleta)."""

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


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    if not GOLD.exists():
        print("gold ausente", file=sys.stderr)
        return 1
    # bronze do dia ou latest checkpoint
    day_dirs = sorted(
        (LAKE / "bronze" / "perfis_enriquecidos").glob("*"),
        reverse=True,
    ) if (LAKE / "bronze" / "perfis_enriquecidos").exists() else []
    perfis_path = None
    for d in day_dirs:
        if d.is_dir() and (d / "perfis.jsonl").exists():
            perfis_path = d / "perfis.jsonl"
            break
    if not perfis_path:
        print("perfis.jsonl ausente — rode enrich_perfis.py", file=sys.stderr)
        return 1

    perfis = _load_jsonl(perfis_path)
    by_id = {p["entity_id"]: p for p in perfis if p.get("entity_id")}
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}
    fotos = 0
    n_forn = 0
    for eid, p in by_id.items():
        e = ents.get(eid)
        if not e:
            continue
        cam = p.get("camara") or {}
        sen = p.get("senado") or {}
        photo = p.get("foto_url") or cam.get("foto_url") or sen.get("foto_url")
        if photo:
            e["foto_url"] = photo
            fotos += 1
        e["email"] = cam.get("email") or sen.get("email") or e.get("email")
        e["nome_civil"] = cam.get("nome") or sen.get("nome") or e.get("nome")
        e["data_nascimento"] = cam.get("data_nascimento") or sen.get("data_nascimento")
        e["escolaridade"] = cam.get("escolaridade") or e.get("escolaridade")
        e["municipio_nascimento"] = (
            cam.get("municipio_nascimento") or sen.get("naturalidade") or e.get("municipio_nascimento")
        )
        e["uf_nascimento"] = cam.get("uf_nascimento") or sen.get("uf_naturalidade") or e.get("uf_nascimento")
        e["redes_sociais"] = cam.get("rede_social") or e.get("redes_sociais") or []
        e["gabinete"] = cam.get("gabinete") or e.get("gabinete")
        e["pagina_oficial"] = cam.get("uri") or sen.get("pagina") or e.get("pagina_oficial")
        partido = (cam.get("partido") or sen.get("partido") or "").strip() or None
        if partido:
            e["partido"] = partido.upper() if len(partido) <= 12 else partido
        uf = cam.get("uf") or sen.get("uf")
        if uf:
            e["uf"] = str(uf).upper()[:2]
        if p.get("despesas"):
            e["despesas_resumo"] = p["despesas"]
        if p.get("despesas_por_ano"):
            e["despesas_por_ano"] = p["despesas_por_ano"]
        e["perfil_fontes"] = p.get("fontes") or e.get("perfil_fontes") or []
        e["perfil_atualizado_em"] = utc_now()
        tags = [t for t in (e.get("tags") or []) if not str(t).startswith("partido:")]
        if "perfil_enriquecido" not in tags:
            tags.append("perfil_enriquecido")
        if photo and "tem_foto" not in tags:
            tags.append("tem_foto")
        if partido:
            tags.append(f"partido:{(e.get('partido') or partido)}")
        e["tags"] = tags

        # POLÍTICO → DESPESA → FORNECEDOR (empresa) — evidência Câmara
        desp = p.get("despesas") or {}
        fonte = desp.get("fonte_url") or f"https://dadosabertos.camara.leg.br/api/v2/deputados/despesas"
        did = f"doc_desp_{eid}_{desp.get('ano') or 'x'}"
        if did not in docs:
            docs[did] = {
                "id": did,
                "tipo": "dados_abertos",
                "titulo": f"Despesas cota parlamentar {desp.get('ano')}",
                "nivel_fonte": "1_primaria",
                "orgao": "camara",
                "url": fonte,
                "casos": [],
            }
        for forn in desp.get("fornecedores") or []:
            cnpj = "".join(ch for ch in str(forn.get("cnpj") or "") if ch.isdigit())
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
                    "tags": ["coletado", "despesa_parlamentar", "onda_dinheiro"],
                    "cnpj": cnpj if len(cnpj) == 14 else None,
                    "source_ids": [f"camara_forn:{cnpj or nome_f}"],
                }
            else:
                if nome_f and str(ents[emp_id].get("nome") or "").startswith("CNPJ"):
                    ents[emp_id]["nome"] = nome_f
                tags_e = list(ents[emp_id].get("tags") or [])
                if "despesa_parlamentar" not in tags_e:
                    tags_e.append("despesa_parlamentar")
                ents[emp_id]["tags"] = tags_e
            rid = f"r_{eid}_{emp_id}_desp_forn"
            rels[rid] = {
                "id": rid,
                "origem": eid,
                "destino": emp_id,
                "tipo": "pagou_despesa_parlamentar_a",
                "periodo": str(desp.get("ano") or ""),
                "contexto": f"Cota parlamentar {desp.get('ano')}",
                "justificativa_documental": (
                    f"Fornecedor nas despesas da cota parlamentar ({desp.get('ano')}): "
                    f"{nome_f or cnpj} · R$ {forn.get('valor')}"
                ),
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [did],
                "fontes": ["camara_despesas"],
                "nota": "Pagamento de cota parlamentar — não implica irregularidade.",
            }
            n_forn += 1
            if "tem_fornecedor_cota" not in tags:
                tags.append("tem_fornecedor_cota")
            e["tags"] = tags

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["perfil_enrich"] = {
        "em": utc_now(),
        "perfis": len(by_id),
        "com_foto": fotos,
        "rels_fornecedor_cota": n_forn,
        "via": "merge_perfis_gold",
    }
    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)
    print(f"OK merge_perfis_gold: {len(by_id)} perfis fotos={fotos} forn_rels={n_forn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
