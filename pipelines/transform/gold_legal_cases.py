#!/usr/bin/env python3
"""
Gold: LEGAL_CASE a partir de documentos CGU públicos.
Fontes: leniência, CEAF, CEPIM, operações especiais, sanções CEIS/CNEP.
Apenas relação mentioned_in — nunca investigated_in automático.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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


def latest_legal() -> Path | None:
    base = LAKE / "bronze" / "cgu_legal"
    if not base.exists():
        return None
    days = [p for p in base.iterdir() if p.is_dir()]
    return max(days, key=lambda p: p.name) if days else None


def _doc(did: str, titulo: str, url: str, caso_id: str) -> dict:
    return {
        "id": did,
        "tipo": "dados_abertos",
        "titulo": titulo[:200],
        "nivel_fonte": "1_primaria",
        "orgao": "cgu_portal",
        "url": url,
        "casos": [caso_id],
    }


def _mention(
    rels: dict,
    origem: str,
    caso_id: str,
    periodo: str,
    contexto: str,
    justificativa: str,
    fonte_id: str,
) -> None:
    rel_id = f"r_{origem}_{caso_id}_mentioned"
    rels[rel_id] = {
        "id": rel_id,
        "origem": origem,
        "destino": caso_id,
        "tipo": "mentioned_in",
        "periodo": periodo,
        "contexto": contexto,
        "justificativa_documental": justificativa,
        "grau_confirmacao": "fato_documentado",
        "fonte_ids": [fonte_id],
        "fontes": ["cgu_portal"],
        "nota": "Menção documental ≠ investigado/acusado/condenado.",
    }


def main() -> int:
    if not GOLD.exists():
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}
    casos = {c["id"]: c for c in kb.get("casos") or []}

    n_case = 0
    n_mention = 0
    day = latest_legal()

    def add_caso(
        cid: str,
        nome: str,
        periodo: str,
        tags: list[str],
        eixos: list[str],
        source_ids: list[str],
    ) -> None:
        nonlocal n_case
        casos[cid] = {
            "id": cid,
            "nome": nome[:160],
            "periodo": periodo,
            "eixos": eixos,
            "tags": tags,
        }
        ents[cid] = {
            "id": cid,
            "tipo": "caso",
            "nome": nome[:160],
            "tags": ["coletado", "cgu_portal", "legal_case", "mentioned_only", *tags],
            "source_ids": source_ids,
        }
        n_case += 1

    if day:
        # 1) Leniência
        for row in _load_jsonl(day / "acordos_leniencia_kb.jsonl"):
            rid = str(row.get("id") or row.get("uuid") or hashlib.sha1(
                json.dumps(row, sort_keys=True, default=str).encode()
            ).hexdigest()[:12])
            cid = f"c_cgu_len_{rid}"
            titulo = (
                row.get("nomeEmpresa")
                or row.get("razaoSocial")
                or row.get("nome")
                or f"Acordo de leniência {rid}"
            )
            add_caso(
                cid,
                f"Acordo de leniência — {titulo}",
                str(row.get("dataInicio") or row.get("data") or ""),
                ["cgu", "acordo_leniencia", "legal_case"],
                ["transparencia", "cgu"],
                [f"cgu_leniencia:{rid}"],
            )
            did = _doc(
                f"doc_cgu_len_{rid}",
                casos[cid]["nome"],
                "https://portaldatransparencia.gov.br/",
                cid,
            )
            docs[did["id"]] = did
            eid = row.get("_atlas_entity_id")
            if not eid and row.get("_atlas_match_cnpj"):
                eid = f"e_cnpj_{row['_atlas_match_cnpj']}"
            if eid and eid in ents:
                _mention(
                    rels,
                    eid,
                    cid,
                    casos[cid]["periodo"],
                    "Acordo de leniência (CGU)",
                    "Empresa/pessoa citada em registro público de acordo de leniência.",
                    did["id"],
                )
                n_mention += 1

        # 2) CEAF
        for row in _load_jsonl(day / "ceaf_kb.jsonl"):
            rid = str(row.get("id") or "")
            cid = f"c_cgu_ceaf_{rid}"
            pes = row.get("pessoa") or {}
            pun = row.get("punicao") or {}
            tip = (row.get("tipoPunicao") or {}).get("descricao") or "Punição CEAF"
            nome_p = pes.get("nome") or pun.get("nomePunido") or rid
            add_caso(
                cid,
                f"CEAF — {tip}: {nome_p}",
                str(row.get("dataPublicacao") or ""),
                ["cgu", "ceaf", "legal_case", "administrativo"],
                ["sancao_administrativa", "cgu"],
                [f"cgu_ceaf:{rid}"],
            )
            did = _doc(
                f"doc_cgu_ceaf_{rid}",
                casos[cid]["nome"],
                "https://portaldatransparencia.gov.br/ceaf",
                cid,
            )
            docs[did["id"]] = did
            eid = row.get("_atlas_entity_id")
            if eid and eid in ents:
                _mention(
                    rels,
                    eid,
                    cid,
                    casos[cid]["periodo"],
                    tip,
                    "Registro CEAF (expulsão/punição administrativa). Não é processo criminal.",
                    did["id"],
                )
                n_mention += 1

        # 3) CEPIM
        for row in _load_jsonl(day / "cepim_kb.jsonl"):
            rid = str(row.get("id") or "")
            cid = f"c_cgu_cepim_{rid}"
            pj = row.get("pessoaJuridica") or {}
            nome_e = pj.get("nome") or rid
            add_caso(
                cid,
                f"CEPIM — {nome_e}",
                str(row.get("dataReferencia") or ""),
                ["cgu", "cepim", "legal_case", "administrativo"],
                ["sancao_administrativa", "cgu"],
                [f"cgu_cepim:{rid}"],
            )
            did = _doc(
                f"doc_cgu_cepim_{rid}",
                casos[cid]["nome"],
                "https://portaldatransparencia.gov.br/cepim",
                cid,
            )
            docs[did["id"]] = did
            eid = row.get("_atlas_entity_id")
            if eid and eid in ents:
                _mention(
                    rels,
                    eid,
                    cid,
                    casos[cid]["periodo"],
                    row.get("motivo") or "CEPIM",
                    "Entidade em CEPIM (impedimento). Menção administrativa documentada.",
                    did["id"],
                )
                n_mention += 1

        # 4) Operações especiais CGU
        for row in _load_jsonl(day / "operacoes_kb.jsonl"):
            nome = row.get("nome") or "Operação CGU"
            h = hashlib.sha1(f"{nome}|{row.get('data')}|{row.get('url')}".encode()).hexdigest()[
                :12
            ]
            cid = f"c_cgu_op_{h}"
            kind = row.get("kind") or "operacao"
            add_caso(
                cid,
                nome,
                str(row.get("data") or ""),
                ["cgu", "operacao_especial", "legal_case", kind],
                ["auditoria", "operacao_cgu"],
                [f"cgu_operacao:{h}"],
            )
            url = row.get("url") or (
                "https://www.gov.br/cgu/pt-br/assuntos/auditoria-e-fiscalizacao/"
                "operacoes-especiais/operacoes-especiais"
            )
            did = _doc(f"doc_cgu_op_{h}", nome, url, cid)
            docs[did["id"]] = did
            for m in row.get("_atlas_mentions") or []:
                eid = m.get("entity_id")
                if eid and eid in ents:
                    _mention(
                        rels,
                        eid,
                        cid,
                        casos[cid]["periodo"],
                        "Citado em publicação CGU sobre operação/notícia",
                        (
                            "Nome/CNPJ aparece em texto público da CGU sobre a operação. "
                            "Menção ≠ investigado."
                        ),
                        did["id"],
                    )
                    n_mention += 1

    # 5) Sanções CEIS/CNEP já no gold → caso + mentioned_in empresa
    for e in list(ents.values()):
        if e.get("tipo") != "sancao":
            continue
        cnpj = re.sub(r"\D", "", str(e.get("cnpj") or ""))
        if len(cnpj) < 14:
            continue
        cnpj14 = cnpj.zfill(14)[-14:]
        cid = f"c_cgu_san_{e['id']}"
        if cid in casos:
            continue
        add_caso(
            cid,
            f"Sanção administrativa — {e.get('nome', '')}",
            e.get("periodo") or "",
            ["cgu", "ceis_cnep", "legal_case"],
            ["sancao_administrativa", "cgu"],
            e.get("source_ids") or [],
        )
        eid = f"e_cnpj_{cnpj14}"
        if eid in ents:
            did = _doc(
                f"doc_{e['id']}_caso",
                casos[cid]["nome"],
                "https://portaldatransparencia.gov.br/sancoes",
                cid,
            )
            docs[did["id"]] = did
            _mention(
                rels,
                eid,
                cid,
                e.get("periodo") or "",
                e.get("tipo_sancao") or "CEIS/CNEP",
                (
                    "Empresa constando em CEIS/CNEP. Sanção administrativa documentada; "
                    "não implica automaticamente crime ou ligação a político."
                ),
                did["id"],
            )
            n_mention += 1

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb["casos"] = list(casos.values())
    kb.setdefault("meta", {})["legal_cases_cgu"] = {
        "em": utc_now(),
        "casos_novos_rodada": n_case,
        "mentioned_in_novos_rodada": n_mention,
        "nota": "Somente mentioned_in; investigated_in exige peça nominal (DataJud/OBS).",
    }

    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)

    print(f"OK legal_cases CGU: casos={n_case} mentioned_in={n_mention}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
