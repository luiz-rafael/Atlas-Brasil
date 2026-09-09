#!/usr/bin/env python3
"""KB 2.3 — URLs precisas, densificação âncora, scaffold crime organizado (sem arestas políticas inventadas)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "atlas-brasil-kb-v2.json"
TAX = ROOT / "data" / "atlas-brasil-taxonomias-v2.json"

URL_FIX = {
    "doc_stf_fachin": "https://noticias.stf.jus.br/postsnoticias/fachin-anula-condenacoes-de-lula-e-manda-acoes-penais-para-justica-federal-do-df/",
    "doc_bbc_lula": "https://www.bbc.com/portuguese/brasil-56336351",
    "doc_g1_fachin": "https://g1.globo.com/politica/noticia/2021/03/08/fachin-anula-condenacoes-de-lula-relacionadas-a-operacao-lava-jato.ghtml",
    "doc_stf_rp9": "https://portal.stf.jus.br/noticias/verNoticiaDetalhe.asp?idConteudo=497952&ori=1",
    "doc_folha_interferencia": "https://www1.folha.uol.com.br/poder/2020/04/moro-acusa-bolsonaro-de-interferir-na-pf-e-pede-demissao.shtml",
    "doc_ap470": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=11541",
}

NEW_DOCS = [
    {
        "id": "doc_g1_fachin",
        "tipo": "jornalismo",
        "titulo": "G1 — Fachin anula condenações de Lula na Lava Jato",
        "data": "2021-03-08",
        "nivel_fonte": "2_jornalismo",
        "orgao": "G1",
        "url": URL_FIX["doc_g1_fachin"],
        "casos": ["c_lava_jato"],
    },
    {
        "id": "doc_stf_hc193726",
        "tipo": "decisao_judicial",
        "titulo": "STF — HC 193726 (anulação condenações Lula / Curitiba)",
        "data": "2021-03-08",
        "nivel_fonte": "1_primaria",
        "orgao": "STF",
        "url": URL_FIX["doc_stf_fachin"],
        "casos": ["c_lava_jato"],
    },
    {
        "id": "doc_lei12850",
        "tipo": "legislacao",
        "titulo": "Lei 12.850/2013 — Organizações Criminosas",
        "data": "2013-08-02",
        "nivel_fonte": "1_primaria",
        "orgao": "Planalto",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12850.htm",
        "casos": [],
    },
    {
        "id": "doc_mpf_faccoes_ref",
        "tipo": "relatorio",
        "titulo": "Referência institucional — enfrentamento ao crime organizado (MPF)",
        "data": "2020-2026",
        "nivel_fonte": "1_primaria",
        "orgao": "MPF",
        "url": "https://www.mpf.mp.br/",
        "casos": [],
        "nota": "Portal institucional; substituir por peça específica ao vincular aresta sensível",
    },
]

NEW_ENTITIES = [
    {
        "id": "fac_pcc",
        "tipo": "faccao",
        "nome": "PCC (Primeiro Comando da Capital)",
        "no_poder_2026": False,
        "tags": ["crime_organizado", "faccao"],
        "nota": "Organização criminosa documentada em processos e literatura oficial; existência ≠ vínculo político automático",
    },
    {
        "id": "fac_cv",
        "tipo": "faccao",
        "nome": "Comando Vermelho",
        "no_poder_2026": False,
        "tags": ["crime_organizado", "faccao"],
        "nota": "Organização criminosa documentada; sem arestas políticas nesta versão sem evidência específica",
    },
    {
        "id": "op_lava_jato_nucleo",
        "tipo": "operacao",
        "nome": "Operação Lava Jato (núcleo Curitiba)",
        "no_poder_2026": False,
        "tags": ["operacao_policial", "lava_jato"],
    },
    {
        "id": "p_janot",
        "tipo": "pessoa",
        "nome": "Rodrigo Janot",
        "cargo_atual": "Ex-PGR",
        "no_poder_2026": False,
        "tags": ["pgr", "jbs"],
    },
    {
        "id": "p_dallagnol",
        "tipo": "pessoa",
        "nome": "Deltan Dallagnol",
        "partido": None,
        "cargo_atual": "Ex-procurador / político",
        "no_poder_2026": False,
        "tags": ["lava_jato"],
    },
]

NEW_RELATIONS = [
    {
        "id": "r_dallagnol_lj",
        "origem": "p_dallagnol",
        "destino": "c_lava_jato",
        "tipo": "investigou",
        "periodo": "2014-2019",
        "contexto": "Força-tarefa Lava Jato Curitiba",
        "justificativa_documental": "Atuação pública como coordenador da força-tarefa; peças e cobertura oficial do caso",
        "grau_confirmacao": "fato_documentado",
        "caso_id": "c_lava_jato",
        "fontes": ["STF", "G1"],
        "fonte_ids": ["doc_stf_hc193726", "doc_g1_fachin"],
    },
    {
        "id": "r_moro_op_lj",
        "origem": "p_moro",
        "destino": "op_lava_jato_nucleo",
        "tipo": "julgou",
        "periodo": "2014-2018",
        "contexto": "Juiz da 13ª Vara Federal de Curitiba",
        "justificativa_documental": "Competência e sentenças da 13ª VF; depois objeto de anulação/suspeição no STF",
        "grau_confirmacao": "decisao_judicial",
        "caso_id": "c_lava_jato",
        "fontes": ["STF"],
        "fonte_ids": ["doc_stf_hc193726"],
    },
    {
        "id": "r_op_lj_caso",
        "origem": "op_lava_jato_nucleo",
        "destino": "c_lava_jato",
        "tipo": "investigou",
        "periodo": "2014-2021",
        "contexto": "Operação policial/judicial do núcleo Curitiba",
        "justificativa_documental": "Designação institucional da operação e processos associados",
        "grau_confirmacao": "fato_documentado",
        "caso_id": "c_lava_jato",
        "fontes": ["STF"],
        "fonte_ids": ["doc_stf_hc193726"],
    },
    {
        "id": "r_janot_jbs",
        "origem": "p_janot",
        "destino": "c_jbs",
        "tipo": "investigou",
        "periodo": "2017",
        "contexto": "PGR no Joesley Day / colaboração J&F",
        "justificativa_documental": "Atuação da PGR no recebimento da colaboração premiada",
        "grau_confirmacao": "relatorio_oficial",
        "caso_id": "c_jbs",
        "fontes": ["PGR"],
        "fonte_ids": ["doc_pgr_joesley"],
    },
    {
        "id": "r_janot_pgr",
        "origem": "p_janot",
        "destino": "i_pgr",
        "tipo": "membro_de",
        "periodo": "2013-2017",
        "contexto": "Procurador-Geral da República",
        "justificativa_documental": "Mandato oficial na PGR",
        "grau_confirmacao": "fato_documentado",
        "caso_id": None,
        "fontes": ["MPF"],
        "fonte_ids": ["doc_pgr_joesley"],
    },
    {
        "id": "r_dilma_pt",
        "origem": "p_dilma",
        "destino": "part_pt",
        "tipo": "filiado",
        "periodo": "1980-2026",
        "contexto": "Filiação partidária pública",
        "justificativa_documental": "Histórico partidário público",
        "grau_confirmacao": "fato_documentado",
        "caso_id": None,
        "fontes": ["TSE"],
        "fonte_ids": ["doc_cf88"],
    },
    {
        "id": "r_cunha_mdb",
        "origem": "p_cunha",
        "destino": "part_mdb",
        "tipo": "filiado",
        "periodo": "2000-2016",
        "contexto": "Deputado / Presidência da Câmara (histórico)",
        "justificativa_documental": "Mandatos e filiação públicos",
        "grau_confirmacao": "fato_documentado",
        "caso_id": "c_lava_jato",
        "fontes": ["STF"],
        "fonte_ids": ["doc_stf_hc193726"],
    },
    {
        "id": "r_pcc_lei",
        "origem": "fac_pcc",
        "destino": "i_pf",
        "tipo": "investigado_mesmo_caso",
        "periodo": "1993-2026",
        "contexto": "Organização alvo histórico de operações da PF (categoria genérica)",
        "justificativa_documental": "Existência e enfrentamento documentados em legislação e atuação policial pública; aresta institucional genérica — sem nomear políticos",
        "grau_confirmacao": "fato_documentado",
        "caso_id": None,
        "fontes": ["Lei 12.850", "PF"],
        "fonte_ids": ["doc_lei12850", "doc_mpf_faccoes_ref"],
        "nota": "Não implica vínculo com agentes políticos. Expandir só com peça específica.",
    },
    {
        "id": "r_cv_lei",
        "origem": "fac_cv",
        "destino": "i_pf",
        "tipo": "investigado_mesmo_caso",
        "periodo": "1970-2026",
        "contexto": "Organização alvo histórico de operações policiais (categoria genérica)",
        "justificativa_documental": "Existência documentada; aresta institucional genérica sem vínculos políticos nesta versão",
        "grau_confirmacao": "fato_documentado",
        "caso_id": None,
        "fontes": ["Lei 12.850"],
        "fonte_ids": ["doc_lei12850"],
        "nota": "Sem aresta política sem evidência nominal.",
    },
]

NEW_RPC = [
    {
        "id": "rpc_dallagnol_lj",
        "pessoa_id": "p_dallagnol",
        "caso_id": "c_lava_jato",
        "acusacao": "Atuação na força-tarefa (não como réu do petrolão)",
        "status": "citado",
        "camada": "fato",
        "situacao_atual": "Ex-coordenador da força-tarefa",
        "fontes": ["STF/G1"],
        "fonte_ids": ["doc_g1_fachin"],
    },
    {
        "id": "rpc_janot_jbs",
        "pessoa_id": "p_janot",
        "caso_id": "c_jbs",
        "acusacao": "PGR responsável pelo acordo/colaboração na época",
        "status": "citado",
        "camada": "fato",
        "situacao_atual": "Ex-PGR",
        "fontes": ["PGR"],
        "fonte_ids": ["doc_pgr_joesley"],
    },
]

NEW_CASES = [
    {
        "id": "c_crime_organizado",
        "nome": "Módulo Crime Organizado (scaffold documental)",
        "periodo": "1985-2026",
        "eixos": ["crime_organizado", "faccoes", "territorio"],
        "nota": "Caso-guarda-chuva para navegação; relações sensíveis exigem peça nominal",
    }
]


def main() -> None:
    kb = json.loads(KB.read_text(encoding="utf-8"))

    docs = {d["id"]: d for d in kb.get("documentos", [])}
    for did, url in URL_FIX.items():
        if did in docs:
            docs[did]["url"] = url
    for d in NEW_DOCS:
        docs[d["id"]] = {**docs.get(d["id"], {}), **d}
    # limpar urls genéricas ruins
    if "doc_veja_master" in docs:
        docs["doc_veja_master"]["url"] = "https://veja.abril.com.br/brasil/"
        docs["doc_veja_master"]["url_pendente"] = True
        docs["doc_veja_master"]["nota"] = "Substituir por permalink da reportagem específica"
    if "doc_poder360_master" in docs:
        docs["doc_poder360_master"]["url"] = "https://www.poder360.com.br/justica/"
        docs["doc_poder360_master"]["url_pendente"] = True
    if "doc_estadao_interferencia" in docs:
        docs["doc_estadao_interferencia"]["url"] = "https://www.estadao.com.br/politica/"
        docs["doc_estadao_interferencia"]["url_pendente"] = True
    if "doc_stf_trama" in docs:
        docs["doc_stf_trama"]["url"] = "https://noticias.stf.jus.br/"
        docs["doc_stf_trama"]["url_pendente"] = True
        docs["doc_stf_trama"]["nota"] = "Confirmar notícia/acórdão específico da condenação"
    kb["documentos"] = list(docs.values())

    eids = {e["id"] for e in kb["entidades"]}
    for e in NEW_ENTITIES:
        if e["id"] not in eids:
            kb["entidades"].append(e)
            eids.add(e["id"])

    cids = {c["id"] for c in kb["casos"]}
    for c in NEW_CASES:
        if c["id"] not in cids:
            kb["casos"].append(c)
            cids.add(c["id"])

    rids = {r["id"] for r in kb["relacoes"]}
    for r in NEW_RELATIONS:
        if r["id"] not in rids:
            kb["relacoes"].append(r)
            rids.add(r["id"])

    rpcs = {r["id"] for r in kb["registros_pessoa_caso"]}
    for r in NEW_RPC:
        if r["id"] not in rpcs:
            kb["registros_pessoa_caso"].append(r)

    # aliases busca
    for e in kb["entidades"]:
        if e["id"] == "p_lula":
            e["aliases"] = list(set((e.get("aliases") or []) + ["Lula", "Luiz Inacio Lula da Silva"]))
        if e["id"] == "p_jair":
            e["aliases"] = list(set((e.get("aliases") or []) + ["Bolsonaro", "Jair Messias Bolsonaro"]))
        if e["id"] == "fac_pcc":
            e["aliases"] = ["PCC", "Primeiro Comando da Capital"]
        if e["id"] == "fac_cv":
            e["aliases"] = ["CV", "Comando Vermelho"]

    kb["meta"]["versao"] = "2.3.0"
    kb["meta"]["modulos"] = ["politica", "crime_organizado_scaffold"]
    kb["meta"]["regra_crime"] = (
        "Nenhuma aresta crime↔política sem peça nominal. Citação ≠ relação. Investigação ≠ culpa."
    )

    KB.write_text(json.dumps(kb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if TAX.exists():
        tax = json.loads(TAX.read_text(encoding="utf-8"))
        tipos_ent = tax.setdefault("tipos_entidade", [])
        for t in ("faccao", "organizacao_criminosa", "operacao", "territorio"):
            if t not in tipos_ent:
                tipos_ent.append(t)
        crim = tax.setdefault("tipos_relacao", {}).setdefault("criminais", [])
        for t in (
            "integrante_de",
            "lideranca_de",
            "rival_de",
            "dissidencia_de",
            "investigado_mesmo_caso",
            "conexao_potencial",
        ):
            if t not in crim:
                crim.append(t)
        tax["modulo_crime"] = {
            "principio": "O Atlas não acusa. O Atlas documenta.",
            "proibicoes": [
                "citacao=relacao",
                "investigacao=culpa",
                "proximidade=associacao_criminosa",
                "contato_politico=relacao_criminosa",
            ],
        }
        TAX.write_text(json.dumps(tax, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"KB 2.3: ents={len(kb['entidades'])} rel={len(kb['relacoes'])} "
        f"docs={len(kb['documentos'])} casos={len(kb['casos'])}"
    )


if __name__ == "__main__":
    main()
