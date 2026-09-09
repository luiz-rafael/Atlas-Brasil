#!/usr/bin/env python3
"""
Plug demo — liga políticos Atlas a processos públicos via OFFICIAL_REFERENCE (STF).

Fontes oficiais (portal/notícias STF), NÃO busca por nome no DataJud.
STF não tem índice na API pública DataJud → casos curados a partir do portal STF.

Demo 1: Gleisi Hoffmann (p_cam_107283) — AP 1003 — absolvida (2ª Turma)
Demo 2: Kim Kataguiri (p_cam_204536) — MS 36248 — impetrante (não réu)

Editorial: processo ≠ culpa; desfecho favorável com destaque.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.legal.discovery import decide_ingest, make_discovery  # noqa: E402
from pipelines.legal.npu import digits_only  # noqa: E402

QUEUE = ROOT / "data" / "lake" / "queues" / "datajud_discovery.jsonl"
SILVER = LAKE / "silver" / "legal"
GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
WEB = ROOT / "data" / "atlas-brasil-kb-web.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"

# Curadoria verificada no portal STF (classe+número → número único).
DEMOS = [
    {
        "person_id": "p_cam_107283",
        "person_name": "Gleisi Hoffmann",
        "stf_class": "AP",
        "stf_number": "1003",
        "process_number": "0000031-09.2015.1.00.0000",
        "case_id": "case_stf_ap_1003",
        "court": "STF",
        "procedural_class": "Ação Penal",
        "role_flags": {
            "reu": "sim",
            "absolvido": "sim",
            "investigado": "histórico",
            "condenado": "não",
        },
        "situacao_atual": "Absolvida pela 2ª Turma do STF (AP 1003). Processo ≠ culpa.",
        "status": "absolvido",
        "outcome_note": (
            "2ª Turma julgou improcedente a ação penal; absolveu Gleisi Hoffmann "
            "e Paulo Bernardo. Destacar desfecho favorável."
        ),
        "portal_url": "https://portal.stf.jus.br/processos/listarProcessos.asp?classe=AP&numeroProcesso=1003",
        "news_url": (
            "https://noticias.stf.jus.br/postsnoticias/"
            "2a-turma-julga-improcedente-acao-penal-contra-senadora-gleisi-hoffmann/"
        ),
        "discovery_reference": "stf_portal_ap_1003|noticias_stf_absolvicao",
        "periodo": "2015-2018",
    },
    {
        "person_id": "p_cam_204536",
        "person_name": "Kim Kataguiri",
        "stf_class": "MS",
        "stf_number": "36248",
        "process_number": "0016597-91.2019.1.00.0000",
        "case_id": "case_stf_ms_36248",
        "court": "STF",
        "procedural_class": "Mandado de Segurança",
        "role_flags": {
            "reu": "não",
            "absolvido": None,
            "investigado": "não",
            "condenado": "não",
            "acusacao": None,
        },
        "situacao_atual": (
            "Impetrante do MS 36248 (candidatura à Presidência da Câmara). "
            "Liminar indeferida; mérito prejudicado. Não é ação penal."
        ),
        "status": "prejudicado",
        "outcome_note": (
            "Mandado de segurança preventivo sobre elegibilidade/idade. "
            "Kim figura como IMPETRANTE, não como réu. Baixa ao arquivo em 2019."
        ),
        "portal_url": "https://portal.stf.jus.br/processos/listarProcessos.asp?classe=MS&numeroProcesso=36248",
        "news_url": (
            "https://noticias.stf.jus.br/postsnoticias/"
            "ministro-nega-liminar-em-ms-que-discute-candidatura-de-kim-kataguiri-a-presidencia-da-camara/"
        ),
        "discovery_reference": "stf_portal_ms_36248|noticias_stf_liminar",
        "periodo": "2019",
        "extra_role": "IMPETRANTE",
    },
]


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def upsert_queue(demos: list[dict]) -> int:
    existing = _load_jsonl(QUEUE)
    by_digits = {
        (r.get("process_number_normalized") or digits_only(r.get("process_number") or "")): r
        for r in existing
    }
    now = utc_now()
    n_new = 0
    for d in demos:
        disc = make_discovery(
            d["process_number"],
            discovered_by_source="stf_portal",
            discovery_type="OFFICIAL_REFERENCE",
            discovered_by_entity_id=d["person_id"],
            discovery_reference=d["discovery_reference"],
            discovered_at=now,
            case_id=d["case_id"],
        )
        disc = decide_ingest(disc, entity_exists=True)
        disc["tribunal_alias"] = None  # STF fora da API DataJud pública
        disc["datajud_skip_reason"] = "STF_NOT_IN_DATAJUD_PUBLIC_API"
        disc["portal_url"] = d["portal_url"]
        disc["news_url"] = d["news_url"]
        dig = disc["process_number_normalized"]
        prev = by_digits.get(dig)
        if prev and prev.get("discovered_by_entity_id") == d["person_id"]:
            by_digits[dig] = {**prev, **disc}
        else:
            by_digits[dig] = disc
            n_new += 1
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(QUEUE, list(by_digits.values()))
    return n_new


def write_silver(demos: list[dict]) -> None:
    SILVER.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    cases = {c.get("case_id"): c for c in _load_jsonl(SILVER / "legal_cases_latest.jsonl") if c.get("case_id")}
    discs = {
        x.get("id"): x for x in _load_jsonl(SILVER / "case_discovery_latest.jsonl") if x.get("id")
    }
    regs = {
        r.get("id"): r
        for r in _load_jsonl(SILVER / "person_case_registers_latest.jsonl")
        if r.get("id")
    }

    for d in demos:
        dig = digits_only(d["process_number"])
        cases[d["case_id"]] = {
            "case_id": d["case_id"],
            "process_number": d["process_number"],
            "process_number_normalized": dig,
            "court": d["court"],
            "procedural_class": d["procedural_class"],
            "stf_class": d["stf_class"],
            "stf_number": d["stf_number"],
            "jurisdiction_degree": "STF",
            "source_id": "stf_portal",
            "dataset_id": "stf.official_reference_demo",
            "seed_entity_id": d["person_id"],
            "seed_source_id": "stf_portal",
            "retrieved_at": now,
            "portal_url": d["portal_url"],
            "news_url": d["news_url"],
            "outcome_note": d["outcome_note"],
            "notes": (
                "OFFICIAL_REFERENCE curada do portal STF. "
                "DataJud público não indexa STF — capa via portal oficial."
            ),
            "editorial_disclaimer": "Processo ≠ culpa. Desfecho com igual ou maior destaque.",
        }
        disc = make_discovery(
            d["process_number"],
            discovered_by_source="stf_portal",
            discovery_type="OFFICIAL_REFERENCE",
            discovered_by_entity_id=d["person_id"],
            discovery_reference=d["discovery_reference"],
            discovered_at=now,
            case_id=d["case_id"],
        )
        disc = decide_ingest(disc, entity_exists=True)
        discs[disc["id"]] = disc

        rid = f"rpc_{d['person_id']}_{d['case_id']}"
        reg = {
            "id": rid,
            "pessoa_id": d["person_id"],
            "caso_id": d["case_id"],
            "status": d["status"],
            "situacao_atual": d["situacao_atual"],
            "camada": "oficial_stf",
            "fontes": ["stf_portal", "noticias_stf"],
            "fonte_urls": [d["portal_url"], d["news_url"]],
            "papel_processual": d.get("extra_role") or ("REU" if d["role_flags"].get("reu") == "sim" else None),
            "outcome_note": d["outcome_note"],
            "updated_at": now,
        }
        for k, v in d["role_flags"].items():
            if v is not None:
                reg[k] = v
        regs[rid] = reg

    write_jsonl(SILVER / "legal_cases_latest.jsonl", list(cases.values()))
    write_jsonl(SILVER / "case_discovery_latest.jsonl", list(discs.values()))
    write_jsonl(SILVER / "person_case_registers_latest.jsonl", list(regs.values()))
    write_json(
        SILVER / "meta_demo_politician_cases.json",
        {
            "em": now,
            "n_cases": len(DEMOS),
            "persons": [d["person_id"] for d in demos],
            "note": "STF via portal oficial; sem DataJud",
        },
    )


def patch_kb(path: Path, demos: list[dict]) -> dict:
    if not path.exists():
        return {"path": str(path), "ok": False, "reason": "missing"}
    kb = json.loads(path.read_text(encoding="utf-8"))
    ents = {e["id"]: e for e in kb.get("entidades") or []}
    rels = {r["id"]: r for r in kb.get("relacoes") or []}
    casos = {c["id"]: c for c in kb.get("casos") or []}
    regs = {r["id"]: r for r in kb.get("registros_pessoa_caso") or []}
    now = utc_now()
    linked = 0

    for d in demos:
        pid = d["person_id"]
        if pid not in ents:
            continue
        cid = d["case_id"]
        casos[cid] = {
            "id": cid,
            "nome": f"{d['stf_class']} {d['stf_number']} — {d['procedural_class']}",
            "periodo": d["periodo"],
            "eixos": ["judiciario"],
            "tags": ["stf", "official_reference", "demo_link", "processo_nao_e_culpa"],
            "cnj_number": d["process_number"],
            "court": "STF",
            "source": "stf_portal",
            "resumo": d["outcome_note"],
            "attrs": {
                "portal_url": d["portal_url"],
                "news_url": d["news_url"],
                "stf_class": d["stf_class"],
                "stf_number": d["stf_number"],
            },
        }
        ents[cid] = {
            "id": cid,
            "tipo": "caso",
            "nome": casos[cid]["nome"],
            "tags": ["stf", "legal_case", "official_reference"],
            "source_ids": ["stf_portal"],
            "attrs": {
                "process_number": d["process_number"],
                "court": "STF",
                "classe": d["procedural_class"],
                "portal_url": d["portal_url"],
            },
        }
        rid = f"r_{pid}_{cid}_mentioned"
        rels[rid] = {
            "id": rid,
            "origem": pid,
            "destino": cid,
            "tipo": "mentioned_in",
            "periodo": d["periodo"],
            "contexto": (
                f"Ligação OFFICIAL_REFERENCE: portal STF {d['stf_class']} {d['stf_number']} "
                f"↔ {d['person_name']} ({pid})."
            ),
            "justificativa_documental": (
                f"NPU {d['process_number']} no portal STF; notícia oficial: {d['news_url']}. "
                f"{d['outcome_note']}"
            ),
            "grau_confirmacao": "fato_documentado",
            "fonte_ids": ["stf_portal", "noticias_stf"],
            "fontes": ["stf_portal", "noticias_stf"],
            "caso_id": cid,
            "nota": (
                "MENTIONED_IN documental. Sem CONVICTED_IN automático. "
                "Processo ≠ culpa."
            ),
        }
        rpc_id = f"rpc_{pid}_{cid}"
        rpc = {
            "id": rpc_id,
            "pessoa_id": pid,
            "caso_id": cid,
            "status": d["status"],
            "situacao_atual": d["situacao_atual"],
            "camada": "oficial_stf",
            "fontes": ["stf_portal", "noticias_stf"],
            "updated_at": now,
        }
        for k, v in d["role_flags"].items():
            if v is not None:
                rpc[k] = v
        if d.get("extra_role"):
            rpc["cargo"] = d["extra_role"]
        regs[rpc_id] = rpc
        linked += 1

    kb["entidades"] = list(ents.values())
    kb["relacoes"] = list(rels.values())
    kb["casos"] = list(casos.values())
    kb["registros_pessoa_caso"] = list(regs.values())
    write_json(path, kb)
    return {"path": str(path), "ok": True, "linked": linked, "casos": len(casos), "regs": len(regs)}


def main() -> int:
    n_q = upsert_queue(DEMOS)
    write_silver(DEMOS)
    results = []
    for path in (WEB, GOLD, ACTIVE):
        if path.exists():
            results.append(patch_kb(path, DEMOS))
    meta = {
        "em": utc_now(),
        "queue_new_or_updated": n_q,
        "demos": [
            {
                "person_id": d["person_id"],
                "case_id": d["case_id"],
                "npu": d["process_number"],
                "status": d["status"],
            }
            for d in DEMOS
        ],
        "kb_patches": results,
        "disclaimer": "Processo != culpa. STF fora do DataJud publico.",
    }
    write_json(SILVER / "meta_demo_politician_cases.json", meta)
    print(json.dumps(meta, ensure_ascii=True, indent=2))
    print("OK plug_demo_politician_cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
