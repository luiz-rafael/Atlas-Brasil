#!/usr/bin/env python3
"""Gera o mock Investigações BETA — cluster INQ 3989 (DEMO_MOCK / notícias STF).

Fonte de verdade: constantes Python abaixo → JSON em data/mocks/.
Processo ≠ culpa. Sem CONVICTED automático. Preferir desfechos favoráveis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "data" / "mocks" / "investigacoes_beta_lava_jato.json"

# ---------------------------------------------------------------------------
# IDs de pessoas (manter atlas_ids conhecidos)
# ---------------------------------------------------------------------------

# PT — INQ 4325
PT_CHARGED_2017 = [
    "mock_lula",
    "mock_dilma",
    "mock_palocci",
    "mock_mantega",
    "p_cam_107283",  # Gleisi
    "mock_paulo_bernardo",
    "mock_vaccari",
    "mock_edinho",
]
PT_INVESTIGATED_ONLY = [
    "mock_berzoini",
    "p_sen_581",  # Jaques Wagner
]
PT_CHARGE_REJECTED_2023 = ["p_cam_107283", "mock_paulo_bernardo"]

# PMDB Senado — INQ 4326
SEN_CHARGED_2017 = [
    "p_sen_35",  # Jader Barbalho
    "p_sen_70",  # Renan Calheiros
    "mock_edison_lobao",
    "mock_romero_juca",
    "mock_jose_sarney",
    "p_tse_22030015100004",  # Valdir Raupp
    "mock_sergio_machado",
]
SEN_REMITTED_13VF = [
    "mock_silas_rondeau",
    "mock_milton_lyra",
    "mock_jorge_luz",
]

# PP — INQ 3989
PP_CHARGED_2017 = [
    "p_cam_160527",  # Aguinaldo Ribeiro
    "p_cam_160541",  # Arthur Lira
    "mock_benedito_lira",
    "p_sen_739",  # Ciro Nogueira
    "mock_eduardo_fonte",
    "mock_dornelles",
    "mock_pizzolatti",
    "mock_germano",
    "mock_luiz_fernando",
    "mock_negromonte",
    "mock_meurer",
    "mock_pedro_henry",
]
PP_ARCHIVED_2017 = [
    "mock_jeronimo",
    "mock_gladson",
    "mock_roberto_britto",
    "mock_sperafico",
    "mock_heinze",
    "mock_molling",
    "mock_lazaro",
    "mock_olimpio",
    "mock_balestra",
    "mock_sessim",
    "mock_waldir",
    "mock_negromonte_jr",
    "mock_hamm",
    "mock_joao_leao",
]
PP_PARTIAL_RECEIVED_THEN_REJECTED = [
    "p_cam_160527",
    "p_cam_160541",
    "mock_eduardo_fonte",
    "p_sen_739",
]

# Queiroz Galvão — INQ 4631
QG_ARCHIVED = [
    "mock_sessim",
    "mock_balestra",
    "mock_jeronimo",
    "mock_eduardo_fonte",
    "p_cam_160527",
    "mock_negromonte_jr",
    "mock_waldir",
]
QG_CONTINUITY = [
    "p_cam_160527",
    "p_cam_160541",
    "p_sen_739",
    "mock_eduardo_fonte",
]
QG_REMITTED_TRF2 = ["mock_dornelles"]

# PMDB Câmara — INQ 4327
CAM_AUTHORITIES = [
    "p_cam_73552",  # Temer
    "p_cam_73892",  # Padilha
    "mock_moreira",
]
CAM_OTHERS = [
    "p_cam_74173",  # Eduardo Cunha
    "mock_henrique_alves",
    "p_cam_74544",  # Geddel
    "mock_rocha_loures",
    "mock_joesley",
    "mock_saud",
    "mock_andre_esteves",
]

ALL_CASES = [
    "stf_inq_3989",
    "stf_inq_4325",
    "stf_inq_4326",
    "stf_inq_4327",
    "stf_inq_4631",
]


def part(
    pid: str,
    cid: str,
    status: str,
    *,
    valid_from: str | None = None,
    valid_to: str | None = None,
    note: str | None = None,
    source_id: str = "stf_public",
) -> dict[str, Any]:
    key = f"{pid}_{cid}_{status}_{valid_from or 'x'}".replace("-", "")
    return {
        "id": f"cp_{key}",
        "person_id": pid,
        "case_id": cid,
        "status": status,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "source_id": source_id,
        "note": note,
    }


def build_participations() -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []

    # --- INQ 4325 PT ---
    for pid in PT_CHARGED_2017 + PT_INVESTIGATED_ONLY:
        parts.append(part(pid, "stf_inq_4325", "INVESTIGATED", valid_from="2016"))
    for pid in PT_CHARGED_2017:
        parts.append(
            part(
                pid,
                "stf_inq_4325",
                "CHARGED",
                valid_from="2017-09",
                note="Denúncia PGR (era Janot) — org. criminosa alegada via Petrobras/BNDES/Planejamento.",
                source_id="src_cluster_stf",
            )
        )
    for pid in PT_CHARGE_REJECTED_2023:
        parts.append(
            part(
                pid,
                "stf_inq_4325",
                "CHARGE_REJECTED",
                valid_from="2023-06",
                note="Plenário STF rejeita denúncia (Fachin; PGR: falta de justa causa).",
                source_id="src_gleisi_2023",
            )
        )

    # --- INQ 4326 PMDB Senado ---
    for pid in SEN_CHARGED_2017 + SEN_REMITTED_13VF:
        parts.append(part(pid, "stf_inq_4326", "INVESTIGATED", valid_from="2016"))
    for pid in SEN_CHARGED_2017:
        parts.append(
            part(
                pid,
                "stf_inq_4326",
                "CHARGED",
                valid_from="2017",
                note="Denúncia PGR — alegados contratos Petrobras/Transpetro (~R$864M no noticiário STF).",
                source_id="src_mdb_2023",
            )
        )
        parts.append(
            part(
                pid,
                "stf_inq_4326",
                "CHARGE_REJECTED",
                valid_from="2023-08-14",
                note="Plenário STF rejeita denúncia (Fachin; manifestação Lindôra Araújo/PGR).",
                source_id="src_mdb_2023",
            )
        )
    for pid in SEN_REMITTED_13VF:
        parts.append(
            part(
                pid,
                "stf_inq_4326",
                "JURISDICTION_CHANGED",
                valid_from="2017",
                note="Remetidos à 13ª Vara Federal de Curitiba (sem foro no STF).",
                source_id="src_mdb_2023",
            )
        )

    # --- INQ 3989 PP ---
    for pid in PP_CHARGED_2017:
        parts.append(part(pid, "stf_inq_3989", "INVESTIGATED", valid_from="2016"))
        parts.append(
            part(
                pid,
                "stf_inq_3989",
                "CHARGED",
                valid_from="2017-09",
                note="Denúncia PGR (12 parlamentares/ex-parlamentares do PP).",
                source_id="src_pp_2021",
            )
        )
    for pid in PP_ARCHIVED_2017:
        parts.append(part(pid, "stf_inq_3989", "INVESTIGATED", valid_from="2016"))
        parts.append(
            part(
                pid,
                "stf_inq_3989",
                "ARCHIVED",
                valid_from="2017",
                note="Arquivamento por insuficiência de provas na mesma ocasião da denúncia.",
                source_id="src_pp_2021",
            )
        )
    for pid in PP_PARTIAL_RECEIVED_THEN_REJECTED:
        parts.append(
            part(
                pid,
                "stf_inq_3989",
                "CHARGE_REJECTED",
                valid_from="2021-03-02",
                note="2ª Turma acolhe embargos e rejeita denúncia (Gilmar Mendes; fatos já arquivados/rejeitados alhures).",
                source_id="src_pp_2021",
            )
        )

    # --- INQ 4631 Queiroz Galvão ---
    for pid in QG_ARCHIVED:
        parts.append(
            part(
                pid,
                "stf_inq_4631",
                "ARCHIVED",
                valid_from="2017",
                note="Arquivamento parcial — alegados ~R$1,6M via diretório nacional do PP (2010).",
                source_id="src_4631",
            )
        )
    for pid in QG_CONTINUITY:
        parts.append(
            part(
                pid,
                "stf_inq_4631",
                "INVESTIGATED",
                valid_from="2017",
                note="Continuidade de apuração sobre outro objeto (não implica culpa).",
                source_id="src_4631",
            )
        )
    for pid in QG_REMITTED_TRF2:
        parts.append(
            part(
                pid,
                "stf_inq_4631",
                "JURISDICTION_CHANGED",
                valid_from="2017",
                note="Remessa ao TRF-2 (desmembramento).",
                source_id="src_4631",
            )
        )

    # --- INQ 4327 PMDB Câmara ---
    for pid in CAM_AUTHORITIES + CAM_OTHERS:
        parts.append(part(pid, "stf_inq_4327", "INVESTIGATED", valid_from="2016"))
    for pid in CAM_AUTHORITIES:
        parts.append(
            part(
                pid,
                "stf_inq_4327",
                "SUSPENDED",
                valid_from="2017",
                note="Câmara negou autorização → suspensão enquanto no cargo.",
                source_id="src_temer_2019",
            )
        )
    for pid in [
        "p_cam_74173",
        "mock_henrique_alves",
        "p_cam_74544",
        "mock_rocha_loures",
        "mock_joesley",
        "mock_saud",
    ]:
        parts.append(
            part(
                pid,
                "stf_inq_4327",
                "JURISDICTION_CHANGED",
                valid_from="2017",
                note="Desmembramento à 10ª VF DF / JFDF (sem foro no STF).",
                source_id="src_temer_2019",
            )
        )
    parts.append(
        part(
            "mock_andre_esteves",
            "stf_inq_4327",
            "ARCHIVED",
            valid_from="2018-12-05",
            note="Plenário arquiva investigação (HC de ofício, Marco Aurélio).",
            source_id="src_esteves_2018",
        )
    )
    for pid in CAM_AUTHORITIES:
        parts.append(
            part(
                pid,
                "stf_inq_4327",
                "JURISDICTION_CHANGED",
                valid_from="2019-01",
                note="Fim do mandato — Fachin determina baixa a instâncias ordinárias (10ª VF DF / TRE-SP conforme o caso).",
                source_id="src_temer_2019",
            )
        )

    return parts


def build_people() -> list[dict[str, Any]]:
    return [
        # PT
        {"id": "mock_lula", "name": "Luiz Inácio Lula da Silva", "party_id": "party_pt"},
        {"id": "mock_dilma", "name": "Dilma Rousseff", "party_id": "party_pt"},
        {"id": "mock_palocci", "name": "Antônio Palocci", "party_id": "party_pt"},
        {"id": "mock_mantega", "name": "Guido Mantega", "party_id": "party_pt"},
        {
            "id": "p_cam_107283",
            "name": "Gleisi Hoffmann",
            "atlas_id": "p_cam_107283",
            "party_id": "party_pt",
        },
        {"id": "mock_paulo_bernardo", "name": "Paulo Bernardo Silva", "party_id": "party_pt"},
        {"id": "mock_vaccari", "name": "João Vaccari Neto", "party_id": "party_pt"},
        {"id": "mock_edinho", "name": "Edinho Silva", "party_id": "party_pt"},
        {"id": "mock_berzoini", "name": "Ricardo Berzoini", "party_id": "party_pt"},
        {
            "id": "p_sen_581",
            "name": "Jaques Wagner",
            "atlas_id": "p_sen_581",
            "party_id": "party_pt",
        },
        # PMDB Senado
        {"id": "mock_edison_lobao", "name": "Edison Lobão", "party_id": "party_pmdb"},
        {
            "id": "p_sen_70",
            "name": "José Renan Vasconcelos Calheiros",
            "atlas_id": "p_sen_70",
            "party_id": "party_pmdb",
        },
        {"id": "mock_romero_juca", "name": "Romero Jucá", "party_id": "party_pmdb"},
        {
            "id": "p_tse_22030015100004",
            "name": "Valdir Raupp de Matos",
            "atlas_id": "p_tse_22030015100004",
            "party_id": "party_pmdb",
        },
        {
            "id": "p_sen_35",
            "name": "Jader Fontenelle Barbalho",
            "atlas_id": "p_sen_35",
            "party_id": "party_pmdb",
        },
        {"id": "mock_jose_sarney", "name": "José Sarney", "party_id": "party_pmdb"},
        {
            "id": "mock_sergio_machado",
            "name": "Sérgio Machado",
            "party_id": "party_pmdb",
            "role_hint": "TRANSPETRO_EX_DIR",
        },
        {"id": "mock_silas_rondeau", "name": "Silas Rondeau"},
        {"id": "mock_milton_lyra", "name": "Milton Lyra"},
        {"id": "mock_jorge_luz", "name": "Jorge Luz"},
        # PP
        {
            "id": "p_cam_160527",
            "name": "Aguinaldo Ribeiro",
            "atlas_id": "p_cam_160527",
            "party_id": "party_pp",
        },
        {
            "id": "p_cam_160541",
            "name": "Arthur Lira",
            "atlas_id": "p_cam_160541",
            "party_id": "party_pp",
        },
        {"id": "mock_benedito_lira", "name": "Benedito de Lira", "party_id": "party_pp"},
        {
            "id": "p_sen_739",
            "name": "Ciro Nogueira Lima Filho",
            "atlas_id": "p_sen_739",
            "party_id": "party_pp",
        },
        {"id": "mock_eduardo_fonte", "name": "Eduardo da Fonte", "party_id": "party_pp"},
        {"id": "mock_dornelles", "name": "Francisco Dornelles", "party_id": "party_pp"},
        {"id": "mock_pizzolatti", "name": "João Pizzolatti Júnior", "party_id": "party_pp"},
        {"id": "mock_germano", "name": "José Otávio Germano", "party_id": "party_pp"},
        {"id": "mock_luiz_fernando", "name": "Luiz Fernando Faria", "party_id": "party_pp"},
        {"id": "mock_negromonte", "name": "Mário Negromonte", "party_id": "party_pp"},
        {"id": "mock_meurer", "name": "Nelson Meurer", "party_id": "party_pp"},
        {"id": "mock_pedro_henry", "name": "Pedro Henry", "party_id": "party_pp"},
        {"id": "mock_jeronimo", "name": "Jerônimo Goergen", "party_id": "party_pp"},
        {"id": "mock_gladson", "name": "Gladson Cameli", "party_id": "party_pp"},
        {"id": "mock_roberto_britto", "name": "Roberto Britto", "party_id": "party_pp"},
        {"id": "mock_sperafico", "name": "Dilceu Sperafico", "party_id": "party_pp"},
        {"id": "mock_heinze", "name": "Luis Carlos Heinze", "party_id": "party_pp"},
        {"id": "mock_molling", "name": "Renato Molling", "party_id": "party_pp"},
        {"id": "mock_lazaro", "name": "Lázaro Botelho", "party_id": "party_pp"},
        {"id": "mock_olimpio", "name": "José Olímpio", "party_id": "party_pp"},
        {"id": "mock_balestra", "name": "Roberto Balestra", "party_id": "party_pp"},
        {"id": "mock_sessim", "name": "Simão Sessim", "party_id": "party_pp"},
        {"id": "mock_waldir", "name": "Waldir Maranhão", "party_id": "party_pp"},
        {"id": "mock_negromonte_jr", "name": "Mário Negromonte Jr.", "party_id": "party_pp"},
        {"id": "mock_hamm", "name": "José Hamm", "party_id": "party_pp"},
        {"id": "mock_joao_leao", "name": "João Leão", "party_id": "party_pp"},
        # PMDB Câmara
        {
            "id": "p_cam_73552",
            "name": "Michel Temer",
            "atlas_id": "p_cam_73552",
            "party_id": "party_pmdb",
        },
        {
            "id": "p_cam_73892",
            "name": "Eliseu Padilha",
            "atlas_id": "p_cam_73892",
            "party_id": "party_pmdb",
        },
        {"id": "mock_moreira", "name": "Moreira Franco", "party_id": "party_pmdb"},
        {
            "id": "p_cam_74173",
            "name": "Eduardo Cunha",
            "atlas_id": "p_cam_74173",
            "party_id": "party_pmdb",
        },
        {"id": "mock_henrique_alves", "name": "Henrique Eduardo Alves", "party_id": "party_pmdb"},
        {
            "id": "p_cam_74544",
            "name": "Geddel Vieira Lima",
            "atlas_id": "p_cam_74544",
            "party_id": "party_pmdb",
        },
        {"id": "mock_rocha_loures", "name": "Rodrigo Rocha Loures", "party_id": "party_pmdb"},
        {"id": "mock_joesley", "name": "Joesley Batista", "role_hint": "JBS_CONTEXT"},
        {"id": "mock_saud", "name": "Ricardo Saud"},
        {"id": "mock_andre_esteves", "name": "André Esteves", "role_hint": "BTG_CONTEXT"},
        # Atores institucionais (não réus)
        {
            "id": "person_teori_zavascki",
            "name": "Teori Zavascki",
            "role_hint": "STF_JUSTICE",
        },
        {
            "id": "person_edson_fachin",
            "name": "Edson Fachin",
            "role_hint": "STF_JUSTICE",
        },
        {
            "id": "person_gilmar_mendes",
            "name": "Gilmar Mendes",
            "role_hint": "STF_JUSTICE",
        },
        {
            "id": "person_marco_aurelio",
            "name": "Marco Aurélio",
            "role_hint": "STF_JUSTICE",
        },
        {
            "id": "person_rodrigo_janot",
            "name": "Rodrigo Janot",
            "role_hint": "PGR",
        },
        {
            "id": "person_lindora_araujo",
            "name": "Lindôra Araújo",
            "role_hint": "PGR",
        },
    ]


def build_companies() -> list[dict[str, Any]]:
    return [
        {
            "id": "co_petrobras",
            "name": "Petrobras",
            "type": "company",
            "note": "Citada no contexto alegado de contratos/org. criminosa (documental).",
        },
        {
            "id": "co_transpetro",
            "name": "Transpetro",
            "type": "company",
            "note": "Citada no INQ 4326 (~R$864M em notícia STF) — contexto contratual, não culpa automática.",
        },
        {
            "id": "co_bndes",
            "name": "BNDES",
            "type": "company",
            "note": "Citado no contexto alegado do núcleo PT (INQ 4325).",
        },
        {
            "id": "co_queiroz_galvao",
            "name": "Grupo Queiroz Galvão",
            "type": "company",
            "note": "Objeto contextual do INQ 4631 (desdobramento do 3989).",
        },
        {
            "id": "co_jbs",
            "name": "JBS",
            "type": "company",
            "note": "Contexto Joesley Batista no INQ 4327 — menção documental.",
        },
        {
            "id": "co_btg",
            "name": "BTG Pactual",
            "type": "company",
            "note": "Contexto André Esteves no INQ 4327 — menção documental.",
        },
        {
            "id": "org_planejamento",
            "name": "Ministério do Planejamento",
            "type": "government_org",
            "note": "Órgão citado no contexto alegado do INQ 4325.",
        },
        {
            "id": "org_camara",
            "name": "Câmara dos Deputados",
            "type": "legislature",
            "note": "Negou autorização → suspensão quanto a autoridades no INQ 4327.",
        },
    ]


def build_courts() -> list[dict[str, Any]]:
    return [
        {"id": "court_stf", "name": "Supremo Tribunal Federal", "type": "court"},
        {"id": "court_stf_2turma", "name": "STF 2ª Turma", "type": "court_body"},
        {"id": "court_stf_plenario", "name": "STF Plenário", "type": "court_body"},
        {
            "id": "court_13vf_curitiba",
            "name": "13ª Vara Federal de Curitiba",
            "type": "court",
        },
        {"id": "court_10vf_df", "name": "10ª Vara Federal do DF", "type": "court"},
        {"id": "court_jfdf", "name": "Justiça Federal do Distrito Federal", "type": "court"},
        {"id": "court_trf2", "name": "TRF-2", "type": "court"},
    ]


def build_case_company_links() -> list[dict[str, Any]]:
    """Arestas documentais caso→empresa/órgão (NÃO culpa)."""
    return [
        {
            "case_id": "stf_inq_4325",
            "company_id": "co_petrobras",
            "relation": "contrato_contexto",
            "note": "Alegação de org. criminosa via contratos Petrobras (notícia STF).",
        },
        {
            "case_id": "stf_inq_4325",
            "company_id": "co_bndes",
            "relation": "mentioned_in_context",
            "note": "BNDES citado no contexto do núcleo PT.",
        },
        {
            "case_id": "stf_inq_4325",
            "company_id": "org_planejamento",
            "relation": "orgao_contexto",
            "note": "Ministério do Planejamento citado no contexto alegado.",
        },
        {
            "case_id": "stf_inq_4326",
            "company_id": "co_petrobras",
            "relation": "contrato_contexto",
            "note": "Alegados contratos Petrobras/Transpetro (~R$864M).",
        },
        {
            "case_id": "stf_inq_4326",
            "company_id": "co_transpetro",
            "relation": "contrato_contexto",
            "note": "Transpetro no contexto do 'Quadrilhão' PMDB Senado.",
        },
        {
            "case_id": "stf_inq_4631",
            "company_id": "co_queiroz_galvao",
            "relation": "mentioned_in_context",
            "note": "Desmembramento Queiroz Galvão / PP (~R$1,6M alegados).",
        },
        {
            "case_id": "stf_inq_3989",
            "company_id": "co_queiroz_galvao",
            "relation": "mentioned_in_context",
            "note": "Peças que originaram o INQ 4631.",
        },
        {
            "case_id": "stf_inq_4327",
            "company_id": "co_jbs",
            "relation": "mentioned_in_context",
            "note": "Contexto Joesley Batista — menção documental.",
        },
        {
            "case_id": "stf_inq_4327",
            "company_id": "co_btg",
            "relation": "mentioned_in_context",
            "note": "Contexto André Esteves — menção documental.",
        },
        {
            "case_id": "stf_inq_4327",
            "company_id": "org_camara",
            "relation": "orgao_contexto",
            "note": "Câmara negou autorização para processar autoridades.",
        },
        {
            "case_id": "stf_inq_4326",
            "company_id": "court_13vf_curitiba",
            "relation": "orgao_contexto",
            "note": "Destino de remessa (Silas Rondeau, Milton Lyra, Jorge Luz).",
        },
        {
            "case_id": "stf_inq_4327",
            "company_id": "court_10vf_df",
            "relation": "orgao_contexto",
            "note": "Destino de desmembramento / baixa pós-mandato.",
        },
        {
            "case_id": "stf_inq_4325",
            "company_id": "court_jfdf",
            "relation": "orgao_contexto",
            "note": "Mar/2018: sem foro → JFDF 1ª instância.",
        },
        {
            "case_id": "stf_inq_4631",
            "company_id": "court_trf2",
            "relation": "orgao_contexto",
            "note": "Remessa de Dornelles e outros ao TRF-2.",
        },
    ]


def build_sources() -> list[dict[str, Any]]:
    return [
        {
            "id": "src_gleisi_2023",
            "title": "A pedido da PGR, STF rejeita denúncia contra deputada Gleisi Hoffmann relacionada à Lava Jato",
            "url": "https://noticias.stf.jus.br/postsnoticias/a-pedido-da-pgr-stf-rejeita-denuncia-contra-deputada-gleisi-hoffmann-relacionada-a-lava-jato/",
            "publisher": "STF Notícias",
            "case_ids": ["stf_inq_4325"],
            "at": "2023-06",
        },
        {
            "id": "src_mdb_2023",
            "title": "STF atende a manifestação da PGR e rejeita denúncia na Lava Jato contra políticos do MDB",
            "url": "https://noticias.stf.jus.br/postsnoticias/stf-atende-a-manifestacao-da-pgr-e-rejeita-denuncia-na-lava-jato-contra-politicos-do-mdb/",
            "publisher": "STF Notícias",
            "case_ids": ["stf_inq_4326"],
            "at": "2023-08-14",
        },
        {
            "id": "src_pp_2021",
            "title": "2ª Turma acolhe recurso e rejeita denúncia contra parlamentares do PP por organização criminosa",
            "url": "https://noticias.stf.jus.br/postsnoticias/2a-turma-acolhe-recurso-e-rejeita-denuncia-contra-parlamentares-do-pp-por-organizacao-criminosa/",
            "publisher": "STF Notícias",
            "case_ids": ["stf_inq_3989"],
            "at": "2021-03-02",
        },
        {
            "id": "src_4631",
            "title": "Desmembrado inquérito que investiga políticos do PP por organização criminosa",
            "url": "https://noticias.stf.jus.br/postsnoticias/desmembrado-inquerito-que-investiga-politicos-do-pp-por-organizacao-criminosa/",
            "publisher": "STF Notícias",
            "case_ids": ["stf_inq_3989", "stf_inq_4631"],
            "at": "2017",
        },
        {
            "id": "src_esteves_2018",
            "title": "Plenário determina arquivamento de investigação contra banqueiro André Esteves",
            "url": "https://noticias.stf.jus.br/postsnoticias/plenario-determina-arquivamento-de-investigacao-contra-banqueiro-andre-esteves/",
            "publisher": "STF Notícias",
            "case_ids": ["stf_inq_4327"],
            "at": "2018-12-05",
        },
        {
            "id": "src_temer_2019",
            "title": "Ministro Fachin determina baixa de inquéritos envolvendo ex-presidente Temer a instâncias ordinárias",
            "url": "https://noticias.stf.jus.br/postsnoticias/ministro-fachin-determina-baixa-de-inqueritos-envolvendo-ex-presidente-temer-a-instancias-ordinarias/",
            "publisher": "STF Notícias",
            "case_ids": ["stf_inq_4327"],
            "at": "2019-01",
        },
        {
            "id": "src_cluster_stf",
            "title": "Conjunto de notícias STF — cluster INQ 3989 / desmembramentos 4325–4327 / 4631",
            "url": "https://noticias.stf.jus.br/",
            "publisher": "STF Notícias",
            "case_ids": ALL_CASES,
            "at": None,
            "note": "Marco geral DEMO_MOCK; fatos nominais citados nas URLs específicas acima.",
        },
    ]


def build_case_events() -> list[dict[str, Any]]:
    return [
        {
            "id": "ev_split_2016",
            "case_id": "stf_inq_3989",
            "type": "CASE_SPLIT",
            "at": "2016",
            "actor_id": "person_teori_zavascki",
            "summary": "Teori Zavascki determina abertura de INQ 4325 (PT), 4326 (PMDB Senado) e 4327 (PMDB Câmara), mantendo PP no INQ 3989.",
            "children": ["stf_inq_4325", "stf_inq_4326", "stf_inq_4327"],
            "source_url": "https://noticias.stf.jus.br/",
            "highlight": True,
        },
        {
            "id": "ev_4631_from_3989",
            "case_id": "stf_inq_3989",
            "type": "CASE_SPLIT",
            "at": "2017",
            "actor_id": "person_edson_fachin",
            "summary": "Peças do INQ 3989 originam o INQ 4631 (Queiroz Galvão / PP); arquivamentos parciais e continuidade parcial.",
            "children": ["stf_inq_4631"],
            "source_url": "https://noticias.stf.jus.br/postsnoticias/desmembrado-inquerito-que-investiga-politicos-do-pp-por-organizacao-criminosa/",
            "highlight": True,
        },
        {
            "id": "ev_relator_fachin",
            "case_id": "stf_inq_3989",
            "type": "RELATOR_CHANGED",
            "at": "2017-02",
            "actor_id": "person_edson_fachin",
            "summary": "Edson Fachin assume relatoria da Lava Jato no STF (após Teori Zavascki).",
            "source_url": "https://noticias.stf.jus.br/",
        },
        # 4325
        {
            "id": "ev_charge_4325_2017",
            "case_id": "stf_inq_4325",
            "type": "CHARGE_FILED",
            "at": "2017-09",
            "actor_id": "person_rodrigo_janot",
            "summary": "PGR (era Janot) denuncia oito: Lula, Dilma, Palocci, Mantega, Gleisi, Paulo Bernardo, Vaccari, Edinho. Berzoini e Jaques Wagner investigados sem essa denúncia.",
            "person_ids": PT_CHARGED_2017,
            "source_url": "https://noticias.stf.jus.br/postsnoticias/a-pedido-da-pgr-stf-rejeita-denuncia-contra-deputada-gleisi-hoffmann-relacionada-a-lava-jato/",
        },
        {
            "id": "ev_split_4325_jfdf_2018",
            "case_id": "stf_inq_4325",
            "type": "JURISDICTION_CHANGED",
            "at": "2018-03",
            "summary": "Desmembramento: sem foro → JFDF 1ª instância; notícia STF registra posterior ausência de justa causa / absolvição na linha remanescente citada.",
            "source_url": "https://noticias.stf.jus.br/postsnoticias/a-pedido-da-pgr-stf-rejeita-denuncia-contra-deputada-gleisi-hoffmann-relacionada-a-lava-jato/",
        },
        {
            "id": "ev_reject_gleisi_2023",
            "case_id": "stf_inq_4325",
            "type": "CHARGE_REJECTED",
            "at": "2023-06",
            "actor_id": "person_edson_fachin",
            "body": "STF Plenário",
            "summary": "Plenário rejeita denúncia remanescente contra Gleisi Hoffmann e Paulo Bernardo (Fachin; PGR: falta de justa causa).",
            "person_ids": PT_CHARGE_REJECTED_2023,
            "source_url": "https://noticias.stf.jus.br/postsnoticias/a-pedido-da-pgr-stf-rejeita-denuncia-contra-deputada-gleisi-hoffmann-relacionada-a-lava-jato/",
            "highlight": True,
        },
        # 4326
        {
            "id": "ev_charge_4326_2017",
            "case_id": "stf_inq_4326",
            "type": "CHARGE_FILED",
            "at": "2017",
            "actor_id": "person_rodrigo_janot",
            "summary": "Denúncia contra Jader Barbalho, Renan Calheiros, Edison Lobão, Romero Jucá, José Sarney, Valdir Raupp e Sérgio Machado (Transpetro). Remessa à 13ª VF Curitiba: Silas Rondeau, Milton Lyra, Jorge Luz.",
            "person_ids": SEN_CHARGED_2017,
            "source_url": "https://noticias.stf.jus.br/postsnoticias/stf-atende-a-manifestacao-da-pgr-e-rejeita-denuncia-na-lava-jato-contra-politicos-do-mdb/",
        },
        {
            "id": "ev_reject_4326_2023",
            "case_id": "stf_inq_4326",
            "type": "CHARGE_REJECTED",
            "at": "2023-08-14",
            "actor_id": "person_edson_fachin",
            "body": "STF Plenário",
            "summary": "Plenário rejeita denúncia (Fachin; Lindôra Araújo/PGR). Sessão encerrada em 14/8/2023.",
            "person_ids": SEN_CHARGED_2017,
            "source_url": "https://noticias.stf.jus.br/postsnoticias/stf-atende-a-manifestacao-da-pgr-e-rejeita-denuncia-na-lava-jato-contra-politicos-do-mdb/",
            "highlight": True,
        },
        # 3989
        {
            "id": "ev_charge_3989_2017",
            "case_id": "stf_inq_3989",
            "type": "CHARGE_FILED",
            "at": "2017-09",
            "actor_id": "person_rodrigo_janot",
            "summary": "Denúncia contra 12 do PP; arquivamento por insuficiência de provas quanto a outro conjunto (Goergen, Cameli, Britto, Sperafico, Heinze, Molling, Botelho, Olímpio, Balestra, Sessim, Waldir Maranhão, Negromonte Jr, Hamm, João Leão).",
            "person_ids": PP_CHARGED_2017,
            "source_url": "https://noticias.stf.jus.br/postsnoticias/2a-turma-acolhe-recurso-e-rejeita-denuncia-contra-parlamentares-do-pp-por-organizacao-criminosa/",
        },
        {
            "id": "ev_3989_partial_receive",
            "case_id": "stf_inq_3989",
            "type": "CHARGE_RECEIVED_PARTIAL",
            "at": "2017",
            "body": "STF 2ª Turma",
            "summary": "2ª Turma recebe parcialmente denúncia quanto a Aguinaldo Ribeiro, Arthur Lira, Eduardo da Fonte e Ciro Nogueira (recebimento ≠ condenação).",
            "person_ids": PP_PARTIAL_RECEIVED_THEN_REJECTED,
            "source_url": "https://noticias.stf.jus.br/postsnoticias/2a-turma-acolhe-recurso-e-rejeita-denuncia-contra-parlamentares-do-pp-por-organizacao-criminosa/",
        },
        {
            "id": "ev_reject_3989_2021",
            "case_id": "stf_inq_3989",
            "type": "CHARGE_REJECTED",
            "at": "2021-03-02",
            "actor_id": "person_gilmar_mendes",
            "body": "STF 2ª Turma",
            "summary": "2ª Turma acolhe embargos e rejeita denúncia contra os quatro (Gilmar Mendes; fatos já arquivados/rejeitados em outras frentes).",
            "person_ids": PP_PARTIAL_RECEIVED_THEN_REJECTED,
            "source_url": "https://noticias.stf.jus.br/postsnoticias/2a-turma-acolhe-recurso-e-rejeita-denuncia-contra-parlamentares-do-pp-por-organizacao-criminosa/",
            "highlight": True,
        },
        # 4631
        {
            "id": "ev_4631_split_archive",
            "case_id": "stf_inq_4631",
            "type": "CASE_SPLIT",
            "at": "2017",
            "summary": "INQ 4631 (Queiroz Galvão): arquivamento quanto a Sessim, Balestra, Goergen, Eduardo da Fonte, Aguinaldo, Negromonte Jr, Waldir Maranhão; continuidade quanto a Aguinaldo, Arthur Lira, Ciro Nogueira, Eduardo da Fonte; remessa TRF-2 (ex.: Dornelles).",
            "source_url": "https://noticias.stf.jus.br/postsnoticias/desmembrado-inquerito-que-investiga-politicos-do-pp-por-organizacao-criminosa/",
            "highlight": True,
        },
        # 4327
        {
            "id": "ev_4327_camara_deny",
            "case_id": "stf_inq_4327",
            "type": "AUTHORIZATION_DENIED",
            "at": "2017",
            "actor_id": "org_camara",
            "summary": "Câmara nega autorização → suspensão quanto a Temer, Padilha e Moreira Franco enquanto no cargo. Desmembramento à 10ª VF DF / JFDF para demais.",
            "person_ids": CAM_AUTHORITIES,
            "source_url": "https://noticias.stf.jus.br/postsnoticias/ministro-fachin-determina-baixa-de-inqueritos-envolvendo-ex-presidente-temer-a-instancias-ordinarias/",
        },
        {
            "id": "ev_archive_andre_2018",
            "case_id": "stf_inq_4327",
            "type": "ARCHIVED",
            "at": "2018-12-05",
            "actor_id": "person_marco_aurelio",
            "body": "STF Plenário",
            "summary": "Plenário determina arquivamento da investigação quanto a André Esteves (HC de ofício, Marco Aurélio).",
            "person_ids": ["mock_andre_esteves"],
            "source_url": "https://noticias.stf.jus.br/postsnoticias/plenario-determina-arquivamento-de-investigacao-contra-banqueiro-andre-esteves/",
            "highlight": True,
        },
        {
            "id": "ev_jurisdiction_temer_2019",
            "case_id": "stf_inq_4327",
            "type": "JURISDICTION_CHANGED",
            "at": "2019-01",
            "actor_id": "person_edson_fachin",
            "summary": "Fim do mandato: Fachin determina baixa dos inquéritos envolvendo Temer (e autoridades) a instâncias ordinárias (10ª VF DF / TRE-SP conforme o caso).",
            "person_ids": CAM_AUTHORITIES,
            "source_url": "https://noticias.stf.jus.br/postsnoticias/ministro-fachin-determina-baixa-de-inqueritos-envolvendo-ex-presidente-temer-a-instancias-ordinarias/",
            "highlight": True,
        },
    ]


def build_decisions() -> list[dict[str, Any]]:
    """Tabela 'quem julgou / arquivou / rejeitou' para a UI."""
    return [
        {
            "at": "2016",
            "actor_id": "person_teori_zavascki",
            "body": "STF",
            "action": "CASE_SPLIT",
            "case_id": "stf_inq_3989",
            "summary": "Desmembra em 4325/4326/4327; mantém PP no 3989.",
            "source_id": "src_cluster_stf",
        },
        {
            "at": "2017-09",
            "actor_id": "person_rodrigo_janot",
            "body": "PGR",
            "action": "FILED_CHARGE",
            "case_id": "stf_inq_4325",
            "summary": "Oferece denúncia (8) no núcleo PT.",
            "source_id": "src_gleisi_2023",
        },
        {
            "at": "2017-09",
            "actor_id": "person_rodrigo_janot",
            "body": "PGR",
            "action": "FILED_CHARGE",
            "case_id": "stf_inq_3989",
            "summary": "Oferece denúncia (12) no núcleo PP; arquiva outro conjunto.",
            "source_id": "src_pp_2021",
        },
        {
            "at": "2018-12-05",
            "actor_id": "person_marco_aurelio",
            "body": "STF Plenário",
            "action": "ARCHIVED",
            "case_id": "stf_inq_4327",
            "person_ids": ["mock_andre_esteves"],
            "summary": "Arquiva investigação quanto a André Esteves.",
            "source_id": "src_esteves_2018",
        },
        {
            "at": "2019-01",
            "actor_id": "person_edson_fachin",
            "body": "STF",
            "action": "JURISDICTION_CHANGED",
            "case_id": "stf_inq_4327",
            "person_ids": CAM_AUTHORITIES,
            "summary": "Baixa a instâncias ordinárias após fim do mandato.",
            "source_id": "src_temer_2019",
        },
        {
            "at": "2021-03-02",
            "actor_id": "person_gilmar_mendes",
            "body": "STF 2ª Turma",
            "action": "CHARGE_REJECTED",
            "case_id": "stf_inq_3989",
            "person_ids": PP_PARTIAL_RECEIVED_THEN_REJECTED,
            "summary": "Rejeita denúncia contra Aguinaldo, Arthur Lira, Eduardo da Fonte e Ciro Nogueira.",
            "source_id": "src_pp_2021",
        },
        {
            "at": "2023-06",
            "actor_id": "person_edson_fachin",
            "body": "STF Plenário",
            "action": "CHARGE_REJECTED",
            "case_id": "stf_inq_4325",
            "person_ids": PT_CHARGE_REJECTED_2023,
            "summary": "Rejeita denúncia contra Gleisi e Paulo Bernardo (PGR: falta justa causa).",
            "source_id": "src_gleisi_2023",
        },
        {
            "at": "2023-08-14",
            "actor_id": "person_edson_fachin",
            "body": "STF Plenário",
            "action": "CHARGE_REJECTED",
            "case_id": "stf_inq_4326",
            "person_ids": SEN_CHARGED_2017,
            "summary": "Rejeita denúncia do 'Quadrilhão' (manifestação Lindôra Araújo/PGR).",
            "source_id": "src_mdb_2023",
        },
        {
            "at": "2023-08-14",
            "actor_id": "person_lindora_araujo",
            "body": "PGR",
            "action": "OPINED_REJECT",
            "case_id": "stf_inq_4326",
            "summary": "Manifestação pela rejeição da denúncia (acolhida pelo Plenário).",
            "source_id": "src_mdb_2023",
        },
    ]


def build_mock() -> dict[str, Any]:
    return {
        "meta": {
            "id": "mock_lava_jato_beta_inq3989",
            "title": "Investigações BETA — cluster INQ 3989 (Lava Jato / STF)",
            "version": "2.0",
            "kind": "DEMO_MOCK",
            "disclaimer": (
                "DEMO_MOCK do cluster INQ 3989 e desdobramentos (4325, 4326, 4327, 4631) — "
                "não é a Lava Jato nacional inteira. Baseado em notícias públicas do STF. "
                "INVESTIGATED / CHARGED ≠ condenação. Processo ≠ culpa. "
                "Desfechos (rejeição, arquivamento, mudança de jurisdição) têm igual ou maior destaque."
            ),
            "model": "CaseParticipation + LegalCaseEvent (temporal). Sem arestas acusatórias inventadas.",
            "sources_note": (
                "Notícias STF: denúncias 2017; desmembramento Teori 2016; "
                "rejeições 2021/2023; arquivamentos Esteves 2018; baixa Temer 2019; INQ 4631."
            ),
            "created_for": "guia /investigacoes-beta",
            "scope": "INQ_3989_CLUSTER_ONLY",
        },
        "operation": {
            "id": "operation_lava_jato",
            "name": "Operação Lava Jato (cluster STF INQ 3989)",
            "started_at": "2014-03-17",
            "country": "BR",
            "scope_note": "Este mock cobre apenas o cluster de inquéritos do STF ligados ao INQ 3989.",
        },
        "organizations": [
            {"id": "org_stf", "name": "Supremo Tribunal Federal", "type": "COURT"},
            {"id": "org_pgr", "name": "Procuradoria-Geral da República", "type": "PROSECUTION"},
            {"id": "org_mpf", "name": "Ministério Público Federal", "type": "PROSECUTION"},
            {"id": "org_pf", "name": "Polícia Federal", "type": "POLICE"},
            {"id": "org_jfdf", "name": "Justiça Federal do Distrito Federal", "type": "COURT"},
        ],
        "parties": [
            {"id": "party_pt", "name": "Partido dos Trabalhadores", "abbreviation": "PT"},
            {"id": "party_pp", "name": "Progressistas", "abbreviation": "PP"},
            {"id": "party_pmdb", "name": "PMDB/MDB", "abbreviation": "PMDB/MDB"},
        ],
        "institutions_roles": [
            {
                "actor_id": "org_pf",
                "role": "PERFORMED_DILIGENCE",
                "target_type": "INVESTIGATION",
                "note": "Diligências policiais — não confundir com julgamento nem com culpa.",
            },
            {
                "actor_id": "org_pgr",
                "role": "PROSECUTION_AUTHORITY",
                "target_type": "INQUIRY",
                "note": "PGR promoveu atos ministeriais / denúncias nestes INQs.",
            },
            {
                "actor_id": "org_pgr",
                "role": "FILED_CHARGE",
                "target_type": "CHARGE",
                "note": "Oferecimento de denúncia (quando houve) — denúncia ≠ condenação.",
            },
            {
                "actor_id": "org_stf",
                "role": "PROCESSED",
                "target_type": "CASE",
                "note": "STF processou/julgou inquéritos e denúncias sob foro — não 'juiz investigou político' como aresta direta.",
            },
        ],
        "people": build_people(),
        "companies": build_companies(),
        "courts": build_courts(),
        "sources": build_sources(),
        "case_company_links": build_case_company_links(),
        "cases": [
            {
                "id": "stf_inq_3989",
                "number": "INQ 3989",
                "title": "Inquérito matriz — organização criminosa / núcleo PP",
                "nucleus": "PP",
                "parent_id": None,
                "operation_id": "operation_lava_jato",
            },
            {
                "id": "stf_inq_4325",
                "number": "INQ 4325",
                "title": "Núcleo relacionado ao PT",
                "nucleus": "PT",
                "parent_id": "stf_inq_3989",
                "operation_id": "operation_lava_jato",
            },
            {
                "id": "stf_inq_4326",
                "number": "INQ 4326",
                "title": "Núcleo PMDB Senado ('Quadrilhão')",
                "nucleus": "PMDB_SENADO",
                "parent_id": "stf_inq_3989",
                "operation_id": "operation_lava_jato",
            },
            {
                "id": "stf_inq_4327",
                "number": "INQ 4327",
                "title": "Núcleo relacionado ao PMDB na Câmara",
                "nucleus": "PMDB_CAMARA",
                "parent_id": "stf_inq_3989",
                "operation_id": "operation_lava_jato",
            },
            {
                "id": "stf_inq_4631",
                "number": "INQ 4631",
                "title": "Queiroz Galvão / desdobramento PP",
                "nucleus": "PP",
                "parent_id": "stf_inq_3989",
                "operation_id": "operation_lava_jato",
            },
        ],
        "case_events": build_case_events(),
        "participations": build_participations(),
        "decisions": build_decisions(),
        "reporters": [
            {
                "person_id": "person_teori_zavascki",
                "case_ids": [
                    "stf_inq_3989",
                    "stf_inq_4325",
                    "stf_inq_4326",
                    "stf_inq_4327",
                ],
                "valid_from": None,
                "valid_to": "2017-01",
                "role": "RELATOR",
            },
            {
                "person_id": "person_edson_fachin",
                "case_ids": ALL_CASES,
                "valid_from": "2017-02",
                "valid_to": None,
                "role": "RELATOR",
            },
        ],
        "dual_rails": [
            {
                "person_id": "p_cam_160541",
                "name": "Arthur Lira",
                "political": [
                    {"at": "eleições", "label": "Eleito Deputado Federal", "source": "TSE/Câmara"},
                    {"at": "mandatos", "label": "Mandatos na Câmara", "source": "Câmara"},
                    {
                        "at": "presidência",
                        "label": "Presidência da Câmara (quando aplicável)",
                        "source": "Câmara",
                    },
                ],
                "legal": [
                    {
                        "at": "2017-09",
                        "label": "CHARGED — INQ 3989 (denúncia registrada)",
                        "status": "CHARGED",
                    },
                    {
                        "at": "2021-03-02",
                        "label": "CHARGE_REJECTED — 2ª Turma (embargos)",
                        "status": "CHARGE_REJECTED",
                    },
                    {
                        "at": "INQ 4631",
                        "label": "Continuidade parcial / objetos distintos (não culpa)",
                        "status": "INVESTIGATED",
                    },
                ],
            },
            {
                "person_id": "p_cam_73552",
                "name": "Michel Temer",
                "political": [
                    {"at": "deputado", "label": "Deputado Federal", "source": "Câmara"},
                    {"at": "2011-2016", "label": "Vice-Presidente", "source": "Planalto"},
                    {"at": "2016-2018", "label": "Presidente da República", "source": "Planalto"},
                ],
                "legal": [
                    {
                        "at": "INQ 4327",
                        "label": "INVESTIGATED no núcleo PMDB-Câmara",
                        "status": "INVESTIGATED",
                    },
                    {
                        "at": "Câmara",
                        "label": "Suspensão — Câmara negou autorização",
                        "status": "SUSPENDED",
                    },
                    {
                        "at": "2019-01",
                        "label": "Fim do mandato → mudança de jurisdição",
                        "status": "JURISDICTION_CHANGED",
                    },
                ],
            },
            {
                "person_id": "p_cam_107283",
                "name": "Gleisi Hoffmann",
                "political": [
                    {"at": "Senado/Câmara", "label": "Mandatos legislativos", "source": "TSE"},
                    {"at": "PT", "label": "Presidência nacional do PT (quando aplicável)", "source": "PT"},
                ],
                "legal": [
                    {
                        "at": "2017-09",
                        "label": "CHARGED — INQ 4325",
                        "status": "CHARGED",
                    },
                    {
                        "at": "2023-06",
                        "label": "CHARGE_REJECTED — Plenário (falta de justa causa)",
                        "status": "CHARGE_REJECTED",
                    },
                ],
            },
        ],
        "anti_patterns": [
            "Este mock NÃO cobre a Lava Jato nacional inteira — só o cluster INQ 3989.",
            "Não desenhar Lula—Temer—Lira—Renan como clique de culpa.",
            "Não criar Sérgio Moro → INVESTIGOU → político nestes INQs do STF.",
            "Não gerar CONVICTED_IN automático a partir de denúncia.",
            "Empresa citada em contexto contratual ≠ culpa da empresa nem da pessoa.",
            "Trajetória política vem de TSE/Casa; jurídica de STF/PGR — cruzam por person_id.",
        ],
    }


def main() -> int:
    data = build_mock()
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "OK",
        f"people={len(data['people'])}",
        f"companies={len(data['companies'])}",
        f"courts={len(data['courts'])}",
        f"participations={len(data['participations'])}",
        f"events={len(data['case_events'])}",
        f"sources={len(data['sources'])}",
        f"decisions={len(data['decisions'])}",
        f"links={len(data['case_company_links'])}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
