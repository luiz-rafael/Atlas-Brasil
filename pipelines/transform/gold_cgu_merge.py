#!/usr/bin/env python3
"""Merge silver CGU (sanções + emendas) na KB — foco políticos/CNPJs já conhecidos."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
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


def _norm(s: str | None) -> str:
    s = (s or "").upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def _doc(titulo: str, url: str) -> dict:
    h = hashlib.sha1(f"cgu|{url}|{titulo}".encode()).hexdigest()[:12]
    return {
        "id": f"doc_cgu_{h}",
        "tipo": "dados_abertos",
        "titulo": titulo[:200],
        "nivel_fonte": "1_primaria",
        "orgao": "cgu_portal",
        "url": url,
        "casos": [],
    }


def main() -> int:
    if not GOLD.exists():
        print("gold ausente", file=sys.stderr)
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}

    sancoes = _load_jsonl(LAKE / "silver" / "sancoes" / "sancoes_latest.jsonl")
    emendas = _load_jsonl(LAKE / "silver" / "emendas" / "emendas_latest.jsonl")
    emenda_links = _load_jsonl(
        next(
            (
                p
                for p in sorted(
                    (LAKE / "bronze" / "cgu_portal").glob("*/emenda_links.jsonl"),
                    reverse=True,
                )
                if p.is_file()
            ),
            Path("/nonexistent"),
        )
    ) if (LAKE / "bronze" / "cgu_portal").exists() else []

    # fallback: day folder
    if not emenda_links:
        day_dirs = sorted(
            [
                p
                for p in (LAKE / "bronze" / "cgu_portal").iterdir()
                if p.is_dir() and (p / "emenda_links.jsonl").exists()
            ],
            key=lambda p: p.name,
            reverse=True,
        ) if (LAKE / "bronze" / "cgu_portal").exists() else []
        if day_dirs:
            emenda_links = _load_jsonl(day_dirs[0] / "emenda_links.jsonl")

    pessoas_by_name: dict[str, list[str]] = {}
    for e in ents.values():
        if e.get("tipo") != "pessoa" or not e["id"].startswith(("p_cam_", "p_sen_")):
            continue
        for n in [e.get("nome"), *(e.get("aliases") or [])]:
            nn = _norm(n)
            if nn:
                pessoas_by_name.setdefault(nn, []).append(e["id"])

    n_sanc = 0
    n_pncp_cross = 0
    for s in sancoes:
        sid = f"san_{hashlib.sha1(s['id_externo'].encode()).hexdigest()[:12]}"
        cnpj = s.get("cnpj")
        nome = (s.get("nome") or sid)[:160]
        ents[sid] = {
            "id": sid,
            "tipo": "sancao",
            "nome": f"{s.get('cadastro')}: {nome}"[:160],
            "tags": ["coletado", "cgu_portal", s.get("cadastro") or "", "onda_f2"],
            "cnpj": cnpj,
            "tipo_sancao": s.get("tipo_sancao"),
            "periodo": f"{s.get('inicio') or ''}–{s.get('fim') or ''}",
            "source_ids": [s["id_externo"]],
        }
        did = _doc(f"{s.get('cadastro')} {nome}", "https://portaldatransparencia.gov.br/sancoes")
        docs[did["id"]] = did
        cnpj_digits = re.sub(r"\D", "", str(cnpj or ""))
        if len(cnpj_digits) == 11:
            ents[sid]["cpf"] = cnpj_digits
            n_sanc += 1
            continue
        if len(cnpj_digits) >= 14:
            cnpj14 = cnpj_digits.zfill(14)[-14:]
            ents[sid]["cnpj"] = cnpj14
            eid = f"e_cnpj_{cnpj14}"
            if eid not in ents:
                ents[eid] = {
                    "id": eid,
                    "tipo": "empresa",
                    "nome": nome,
                    "tags": ["coletado", "cgu_portal", "sancionada"],
                    "cnpj": cnpj14,
                    "source_ids": [f"cgu_cnpj:{cnpj14}"],
                }
            else:
                tags = list(ents[eid].get("tags") or [])
                if "sancionada" not in tags:
                    tags.append("sancionada")
                ents[eid]["tags"] = tags
                ents[eid]["sancao_resumo"] = {
                    "cadastro": s.get("cadastro"),
                    "tipo": s.get("tipo_sancao"),
                    "periodo": ents[sid]["periodo"],
                }
                if ents[eid]["nome"].startswith("CNPJ"):
                    ents[eid]["nome"] = nome
            rid = f"r_{eid}_{sid}_sancao"
            rels[rid] = {
                "id": rid,
                "origem": eid,
                "destino": sid,
                "tipo": "sancionada_em",
                "periodo": s.get("inicio"),
                "contexto": s.get("tipo_sancao"),
                "justificativa_documental": (
                    f"Registro {s.get('cadastro')} no Portal da Transparência"
                ),
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [did["id"]],
                "fontes": ["cgu_portal"],
            }
            # cruzar com contratos PNCP já no grafo (mesmo CNPJ, só dígitos)
            for ctr in list(ents.values()):
                if ctr.get("tipo") != "contrato":
                    continue
                ctr_c = re.sub(r"\D", "", str(ctr.get("cnpj") or ""))
                if len(ctr_c) >= 14:
                    ctr_c = ctr_c[-14:]
                else:
                    ctr_c = ctr_c.zfill(14) if ctr_c else ""
                if ctr_c != cnpj14:
                    continue
                crid = f"r_{ctr['id']}_{sid}_ctr_sancao"
                if crid in rels:
                    continue
                rels[crid] = {
                    "id": crid,
                    "origem": ctr["id"],
                    "destino": sid,
                    "tipo": "contrato_com_empresa_sancionada",
                    "periodo": s.get("inicio"),
                    "contexto": "Mesmo CNPJ em contrato PNCP e sanção CGU",
                    "justificativa_documental": (
                        f"CNPJ {cnpj14} figura em contrato PNCP e em {s.get('cadastro')}"
                    ),
                    "grau_confirmacao": "fato_documentado",
                    "fonte_ids": [did["id"]],
                    "fontes": ["cgu_portal", "pncp"],
                    "nota": "Correlação por CNPJ — não prova vínculo causal com o contrato.",
                }
                # marca empresa se existir via contrato
                if eid in ents:
                    tags2 = list(ents[eid].get("tags") or [])
                    if "contrato_pncp" not in tags2:
                        tags2.append("contrato_pncp")
                    ents[eid]["tags"] = tags2
                n_pncp_cross += 1
        n_sanc += 1

    # mapa codigo emenda -> person_id (coleta focada)
    by_cod = {x["codigoEmenda"]: x["person_id"] for x in emenda_links if x.get("codigoEmenda")}

    n_em = 0
    n_link = 0
    for em in emendas:
        codigo = em.get("codigo") or (em.get("id_externo") or "").split(":")[-1]
        eid = f"em_{hashlib.sha1(em['id_externo'].encode()).hexdigest()[:12]}"
        autor = em.get("autor") or "Autor"
        ents[eid] = {
            "id": eid,
            "tipo": "emenda",
            "nome": f"Emenda {codigo} — {autor}"[:160],
            "tags": ["coletado", "cgu_portal", "onda_f2"],
            "valor": em.get("valor_pago") or em.get("valor_empenhado"),
            "source_ids": [em["id_externo"]],
            "autor": autor,
            "localidade": em.get("localidade"),
            "funcao": em.get("funcao"),
            "ano": em.get("ano"),
            "codigo": codigo,
        }
        did = _doc(f"Emenda {codigo}", "https://portaldatransparencia.gov.br/emendas")
        docs[did["id"]] = did

        pid = em.get("person_id") or by_cod.get(str(codigo))
        if not pid:
            hits = pessoas_by_name.get(_norm(autor)) or []
            if len(hits) == 1:
                pid = hits[0]
        if pid and pid in ents:
            rid = f"r_{pid}_{eid}_autor"
            rels[rid] = {
                "id": rid,
                "origem": pid,
                "destino": eid,
                "tipo": "autor_de_emenda",
                "periodo": str(em.get("ano") or ""),
                "contexto": em.get("localidade"),
                "justificativa_documental": (
                    f"Autor da emenda {codigo} no Portal da Transparência"
                ),
                "grau_confirmacao": "fato_documentado" if by_cod.get(str(codigo)) else "hipotese_forte",
                "fonte_ids": [did["id"]],
                "fontes": ["cgu_portal"],
            }
            # agrega no perfil
            pessoa = ents[pid]
            lista = list(pessoa.get("emendas_resumo") or [])
            lista.append(
                {
                    "codigo": codigo,
                    "valor": ents[eid].get("valor"),
                    "localidade": em.get("localidade"),
                    "ano": em.get("ano"),
                    "emenda_id": eid,
                }
            )
            pessoa["emendas_resumo"] = lista[:40]
            tags = list(pessoa.get("tags") or [])
            if "tem_emendas_cgu" not in tags:
                tags.append("tem_emendas_cgu")
            pessoa["tags"] = tags
            n_link += 1
        n_em += 1

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["cgu_gold"] = {
        "em": utc_now(),
        "sancoes": n_sanc,
        "emendas": n_em,
        "emendas_ligadas_pessoa": n_link,
        "contratos_pncp_x_sancao": n_pncp_cross,
    }

    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)

    print(
        f"OK gold CGU: sancoes={n_sanc} emendas={n_em} "
        f"ligadas={n_link} pncp_x_sancao={n_pncp_cross}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
