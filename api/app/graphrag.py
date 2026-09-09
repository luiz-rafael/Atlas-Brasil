"""GraphRAG: pergunta → grafo + OpenSearch + documentos → resposta com evidências."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from app.graph_ops import meeting_points, shortest_paths, subgraph
from app.kb_loader import load_kb
from app.opensearch_client import search_docs
from app.entity_resolution import resolve as er_resolve
from app.semantic import search as semantic_search

DISCLAIMER = (
    "Resposta baseada em evidências indexadas. Não constitui acusação nem parecer jurídico. "
    "Sempre verifique as fontes."
)


def _find_entity_ids(question: str) -> list[str]:
    # Fase 3: entity resolution + substring clássico
    resolved = er_resolve(question, limit=6)
    ids = [r["entity_id"] for r in resolved if r.get("score", 0) >= 0.82]
    if ids:
        return ids[:4]
    kb = load_kb()
    q = question.lower()
    found: list[tuple[int, str]] = []
    for e in kb.get("entidades", []):
        if e.get("isolada"):
            continue
        names = [e.get("nome", "")] + list(e.get("aliases") or [])
        for name in names:
            if not name or len(name) < 3:
                continue
            if name.lower() in q:
                found.append((len(name), e["id"]))
                break
    for c in kb.get("casos", []):
        if c.get("nome", "").lower() in q or any(
            x in q for x in (c.get("eixos") or [])
        ):
            found.append((len(c.get("nome", "")), c["id"]))
    found.sort(key=lambda x: -x[0])
    seen = set()
    out = []
    for _, i in found:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out[:4]


def _graph_context(entity_ids: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"subgrafos": [], "caminhos": [], "encontros": None}
    for eid in entity_ids[:2]:
        out["subgrafos"].append(subgraph(eid, 1))
    if len(entity_ids) >= 2:
        out["caminhos"] = shortest_paths(entity_ids[0], entity_ids[1], 6)
        out["encontros"] = meeting_points(entity_ids[0], entity_ids[1], 2)
    return out


def _docs_fallback(q: str) -> list[dict]:
    kb = load_kb()
    s = q.lower()
    hits = []
    for d in kb.get("documentos") or []:
        blob = f"{d.get('titulo','')} {d.get('orgao','')} {' '.join(d.get('casos') or [])}".lower()
        if any(tok in blob for tok in s.split() if len(tok) > 3):
            hits.append(d)
    return hits[:8]


def _synthesize_local(question: str, evidence: dict[str, Any]) -> str:
    parts = [f"Pergunta: {question}", "", "Síntese documental (sem LLM externo):", ""]
    ents = evidence.get("entidades_detectadas") or []
    if ents:
        parts.append("Entidades reconhecidas: " + ", ".join(ents))
    docs = evidence.get("documentos") or []
    if docs:
        parts.append("Documentos relevantes:")
        for d in docs[:5]:
            parts.append(
                f"- {d.get('titulo')} ({d.get('orgao') or d.get('nivel_fonte')}) "
                f"{d.get('url') or ''}"
            )
    paths = (evidence.get("grafo") or {}).get("caminhos") or {}
    if paths.get("found"):
        p0 = paths["paths"][0]
        chain = " → ".join(n.get("nome", n.get("id")) for n in p0.get("nos", []))
        parts.append(f"Caminho no grafo: {chain}")
        parts.append("(Caminho ≠ culpa.)")
    enc = (evidence.get("grafo") or {}).get("encontros")
    if enc and enc.get("total"):
        parts.append(f"Pontos de encontro estruturais: {enc['total']} (interseção ≠ aliança).")
    if not docs and not ents:
        parts.append(
            "Não há evidência suficiente indexada para responder com segurança. "
            "Refine a pergunta ou rode os ingestores STF/TSE."
        )
    parts.append("")
    parts.append(DISCLAIMER)
    return "\n".join(parts)


def _synthesize_llm(question: str, evidence: dict[str, Any]) -> str | None:
    key = os.getenv("OPENAI_API_KEY") or os.getenv("ATLAS_LLM_API_KEY")
    base = os.getenv("ATLAS_LLM_BASE", "https://api.openai.com/v1")
    model = os.getenv("ATLAS_LLM_MODEL", "gpt-4o-mini")
    if not key:
        return None
    prompt = (
        "Você é o assistente do ATLAS BRASIL. Responda em português com base APENAS "
        "nas evidências. Não acuse. Cite fontes/URLs. Se faltar evidência, diga.\n\n"
        f"PERGUNTA: {question}\n\nEVIDÊNCIAS JSON (resumo):\n{str(evidence)[:12000]}"
    )
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": DISCLAIMER},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
            )
            if r.status_code >= 400:
                return None
            return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


def answer(question: str) -> dict[str, Any]:
    entity_ids = _find_entity_ids(question)
    kb = load_kb()
    id_to_nome = {
        e["id"]: e["nome"] for e in kb.get("entidades", [])
    }
    id_to_nome.update({c["id"]: c["nome"] for c in kb.get("casos", [])})

    docs = search_docs(question, size=8)
    if not docs:
        docs = _docs_fallback(question)
    # Fase 3: enriquecer com busca semântica
    sem = semantic_search(question, size=5)
    if sem.get("hits"):
        seen = {d.get("id") for d in docs}
        for h in sem["hits"]:
            did = h.get("doc_id")
            if did and did not in seen and not str(did).startswith("ent:"):
                docs.append(
                    {
                        "id": did,
                        "titulo": h.get("titulo") or did,
                        "orgao": "semantico",
                        "url": None,
                        "_score": h.get("score"),
                    }
                )
                seen.add(did)

    grafo = _graph_context(entity_ids)
    evidence = {
        "entidades_detectadas": [id_to_nome.get(i, i) for i in entity_ids],
        "entity_ids": entity_ids,
        "documentos": docs,
        "grafo": grafo,
    }
    llm = _synthesize_llm(question, evidence)
    return {
        "pergunta": question,
        "resposta": llm or _synthesize_local(question, evidence),
        "modo": "llm" if llm else "local_graph_rag",
        "evidencias": evidence,
        "disclaimer": DISCLAIMER,
    }
