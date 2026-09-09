#!/usr/bin/env python3
"""Merge silver F1 (bens, contratos, orgaos) na KB gold existente."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json  # noqa: E402

GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"
REPORT = ROOT / "pipelines" / "reports" / "coverage_f1.json"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _doc(source: str, url: str, titulo: str) -> dict:
    h = hashlib.sha1(f"{source}|{url}".encode()).hexdigest()[:12]
    return {
        "id": f"doc_{source}_{h}",
        "tipo": "dados_abertos",
        "titulo": titulo,
        "nivel_fonte": "1_primaria",
        "orgao": source,
        "url": url,
        "casos": [],
    }


def main() -> int:
    if not GOLD.exists():
        print("gold ausente — rode gold_kb.py antes", file=sys.stderr)
        return 1
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    docs = {d["id"]: d for d in kb.get("documentos") or []}

    bens = _load_jsonl(LAKE / "silver" / "bens" / "bens_latest.jsonl")
    contratos = _load_jsonl(LAKE / "silver" / "contratos" / "contratos_latest.jsonl")
    orgaos = _load_jsonl(LAKE / "silver" / "orgaos" / "orgaos_latest.jsonl")
    membros = _load_jsonl(LAKE / "silver" / "orgaos" / "membros_latest.jsonl")
    transf = _load_jsonl(LAKE / "silver" / "transferencias" / "transferencias_latest.jsonl")
    empresas = _load_jsonl(LAKE / "silver" / "empresas" / "empresas_latest.jsonl")

    # Bens -> perfil + aresta DECLARED
    bens_por_pessoa: dict[str, list] = {}
    for b in bens:
        pid = b.get("person_id")
        if not pid:
            continue
        bens_por_pessoa.setdefault(pid, []).append(b)
        if pid not in ents:
            continue
        rid = f"r_{pid}_asset_{b['id_externo']}"
        did = _doc("tse_bens", "https://dadosabertos.tse.jus.br/", f"Bem TSE {b.get('tipo_bem')}")
        docs[did["id"]] = did
        asset_id = f"asset_{hashlib.sha1(b['id_externo'].encode()).hexdigest()[:12]}"
        ents[asset_id] = {
            "id": asset_id,
            "tipo": "ativo",
            "nome": (b.get("descricao") or b.get("tipo_bem") or asset_id)[:120],
            "tags": ["coletado", "tse_bens", "onda_f1"],
            "valor": b.get("valor"),
            "source_ids": [b["id_externo"]],
        }
        rels[rid] = {
            "id": rid,
            "origem": pid,
            "destino": asset_id,
            "tipo": "declarou_bem",
            "periodo": "2022",
            "contexto": b.get("tipo_bem"),
            "justificativa_documental": f"Bem declarado no TSE ({b.get('tipo_bem')})",
            "grau_confirmacao": "fato_documentado",
            "fonte_ids": [did["id"]],
            "fontes": ["tse_bens"],
        }

    for pid, blist in bens_por_pessoa.items():
        if pid not in ents:
            continue
        total = sum(x.get("valor") or 0 for x in blist)
        ents[pid]["bens_declarados"] = {
            "qtd": len(blist),
            "valor_total": round(total, 2),
            "amostra": [
                {"tipo": x.get("tipo_bem"), "valor": x.get("valor")} for x in blist[:5]
            ],
            "fonte": "tse_bens",
        }

    # Contratos + empresas + licitação (compra PNCP) + órgão
    n_lic = 0
    n_org = 0
    for c in contratos:
        cid = f"ctr_{hashlib.sha1(c['id_externo'].encode()).hexdigest()[:12]}"
        ents[cid] = {
            "id": cid,
            "tipo": "contrato",
            "nome": (c.get("objeto") or c.get("numero") or cid)[:160],
            "tags": ["coletado", "pncp", "onda_f1"]
            + (["emenda_parlamentar"] if c.get("emenda_parlamentar") else []),
            "valor": c.get("valor"),
            "uf": c.get("uf"),
            "source_ids": [c["id_externo"]],
            "cnpj": c.get("cnpj"),
            "compra_pncp": c.get("compra_pncp"),
            "orgao": c.get("orgao"),
        }
        did = _doc("pncp", "https://pncp.gov.br/", f"Contrato PNCP {c.get('numero')}")
        docs[did["id"]] = did

        # órgão contratante
        org_id = None
        if c.get("orgao_cnpj") and len(str(c["orgao_cnpj"])) == 14:
            org_id = f"o_cnpj_{c['orgao_cnpj']}"
        elif c.get("orgao"):
            org_id = f"o_nome_{hashlib.sha1(str(c['orgao']).upper().encode()).hexdigest()[:12]}"
        if org_id:
            if org_id not in ents:
                ents[org_id] = {
                    "id": org_id,
                    "tipo": "instituicao",
                    "nome": c.get("orgao") or org_id,
                    "tags": ["coletado", "pncp", "orgao_contratante"],
                    "cnpj": c.get("orgao_cnpj"),
                    "source_ids": [f"pncp_org:{c.get('orgao_cnpj') or c.get('orgao')}"],
                }
                n_org += 1
            rid_o = f"r_{org_id}_{cid}_contratou"
            rels[rid_o] = {
                "id": rid_o,
                "origem": org_id,
                "destino": cid,
                "tipo": "orgao_contratou",
                "periodo": str(c.get("data") or "")[:10],
                "contexto": "Órgão contratante no PNCP",
                "justificativa_documental": f"Contrato PNCP {c.get('numero')} · órgão {c.get('orgao')}",
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [did["id"]],
                "fontes": ["pncp"],
            }

        # licitação / compra PNCP
        compra = c.get("compra_pncp")
        lic_id = None
        if compra:
            lic_id = f"lic_{hashlib.sha1(str(compra).encode()).hexdigest()[:12]}"
            if lic_id not in ents:
                ents[lic_id] = {
                    "id": lic_id,
                    "tipo": "licitacao",
                    "nome": f"Compra PNCP {compra}",
                    "tags": ["coletado", "pncp"],
                    "source_ids": [f"pncp_compra:{compra}"],
                    "numero": str(compra),
                }
                n_lic += 1
            rid_l = f"r_{lic_id}_{cid}_gerou"
            rels[rid_l] = {
                "id": rid_l,
                "origem": lic_id,
                "destino": cid,
                "tipo": "licitacao_gerou_contrato",
                "periodo": str(c.get("data") or "")[:10],
                "contexto": "Compra PNCP → contrato",
                "justificativa_documental": f"numeroControlePncpCompra={compra}",
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [did["id"]],
                "fontes": ["pncp"],
            }
            if org_id:
                rid_ol = f"r_{org_id}_{lic_id}_abriu"
                rels[rid_ol] = {
                    "id": rid_ol,
                    "origem": org_id,
                    "destino": lic_id,
                    "tipo": "orgao_abriu_licitacao",
                    "periodo": str(c.get("data") or "")[:10],
                    "contexto": "Órgão → licitação PNCP",
                    "justificativa_documental": f"Compra {compra} do órgão {c.get('orgao')}",
                    "grau_confirmacao": "fato_documentado",
                    "fonte_ids": [did["id"]],
                    "fontes": ["pncp"],
                }

        cnpj = c.get("cnpj")
        if cnpj and len(cnpj) >= 8:
            eid = f"e_cnpj_{cnpj}"
            if eid not in ents:
                ents[eid] = {
                    "id": eid,
                    "tipo": "empresa",
                    "nome": c.get("nome_fornecedor") or f"CNPJ {cnpj}",
                    "tags": ["coletado", "pncp", "onda_f1"],
                    "cnpj": cnpj,
                    "source_ids": [f"pncp_cnpj:{cnpj}"],
                }
            elif c.get("nome_fornecedor") and str(ents[eid].get("nome") or "").startswith("CNPJ"):
                ents[eid]["nome"] = c["nome_fornecedor"]
            rid = f"r_{cid}_{eid}_fornecedor"
            rels[rid] = {
                "id": rid,
                "origem": cid,
                "destino": eid,
                "tipo": "fornecido_por",
                "periodo": str(c.get("data") or "")[:10],
                "contexto": "Contrato PNCP",
                "justificativa_documental": f"Fornecedor CNPJ {cnpj} no contrato PNCP {c.get('numero')}",
                "grau_confirmacao": "fato_documentado",
                "fonte_ids": [did["id"]],
                "fontes": ["pncp"],
            }

    # Enriquece nós empresa a partir do silver/empresas
    for emp in empresas:
        cnpj = emp.get("cnpj")
        if not cnpj:
            continue
        eid = f"e_cnpj_{cnpj}"
        if eid not in ents:
            ents[eid] = {
                "id": eid,
                "tipo": "empresa",
                "nome": emp.get("nome") or f"CNPJ {cnpj}",
                "tags": ["coletado", "pncp", "onda_f2"],
                "cnpj": cnpj,
                "source_ids": [emp.get("id_externo") or f"cnpj:{cnpj}"],
            }
        ents[eid]["contratos_count"] = emp.get("contratos")
        ents[eid]["valor_contratos"] = emp.get("valor_total")
        ents[eid]["rfb_status"] = emp.get("rfb_status")
        tags = list(ents[eid].get("tags") or [])
        if "onda_f2" not in tags:
            tags.append("onda_f2")
        ents[eid]["tags"] = tags

    # Orgaos / frentes
    for o in orgaos:
        oid = o["id_externo"].replace(":", "_")
        ents[oid] = {
            "id": oid,
            "tipo": "instituicao",
            "nome": o.get("nome") or oid,
            "tags": ["coletado", "camara_orgaos", "onda_f1", o.get("tipo") or ""],
            "source_ids": [o["id_externo"]],
        }
    for m in membros:
        pid = m.get("person_id")
        oid = (m.get("org_id") or "").replace(":", "_")
        if not pid or pid not in ents or not oid or oid not in ents:
            continue
        rid = f"r_{pid}_{oid}_membro"
        did = _doc(
            "camara_orgaos",
            "https://dadosabertos.camara.leg.br/api/v2/frentes",
            f"Membro frente {m.get('titulo')}",
        )
        docs[did["id"]] = did
        rels[rid] = {
            "id": rid,
            "origem": pid,
            "destino": oid,
            "tipo": "membro_de",
            "periodo": "atual",
            "contexto": m.get("titulo"),
            "justificativa_documental": f"Membro da frente/órgão na Câmara: {m.get('titulo')}",
            "grau_confirmacao": "fato_documentado",
            "fonte_ids": [did["id"]],
            "fontes": ["camara_orgaos"],
        }

    # Transferencias (nós leves)
    for t in transf[:200]:
        tid = f"tr_{hashlib.sha1(t['id_externo'].encode()).hexdigest()[:12]}"
        ents[tid] = {
            "id": tid,
            "tipo": "transferencia",
            "nome": (t.get("nome") or tid)[:160],
            "tags": ["coletado", "transferegov", "onda_f1"],
            "valor": t.get("valor"),
            "uf": t.get("uf"),
            "cnpj": t.get("cnpj"),
            "source_ids": [t["id_externo"]],
        }

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["documentos"] = list(docs.values())
    kb.setdefault("meta", {})["onda_f1"] = {
        "em": utc_now(),
        "bens": len(bens),
        "contratos": len(contratos),
        "licitacoes": n_lic,
        "orgaos_pncp": n_org,
        "orgaos": len(orgaos),
        "membros": len(membros),
        "transferencias": len(transf),
    }
    kb["meta"]["pipeline"] = "onda1_oficial+f1"

    write_json(GOLD, kb)
    write_json(LAKE / "gold" / "kb.json", kb)
    write_json(ACTIVE, kb)
    write_json(V2, kb)

    from pipelines.registry import coverage_report

    cov = coverage_report()
    cov["gold"] = {
        "entidades": len(kb["entidades"]),
        "relacoes": len(kb["relacoes"]),
        "documentos": len(kb["documentos"]),
        "bens_silver": len(bens),
        "contratos_silver": len(contratos),
        "licitacoes": n_lic,
    }
    write_json(REPORT, cov)
    print(
        f"OK gold F1 merge: ents={len(ents)} rels={len(rels)} "
        f"bens={len(bens)} contratos={len(contratos)} licitacoes={n_lic}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
