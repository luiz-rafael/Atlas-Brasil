"""Cliente OpenSearch + índice atlas-docs."""

from __future__ import annotations

import os
from typing import Any

import httpx

INDEX = os.getenv("OPENSEARCH_INDEX", "atlas-docs")


def os_url() -> str:
    return os.getenv("OPENSEARCH_URL", "http://localhost:9200").rstrip("/")


def ping_opensearch() -> bool:
    try:
        r = httpx.get(f"{os_url()}/", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def ensure_index() -> None:
    mapping = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "titulo": {"type": "text", "analyzer": "portuguese"},
                "orgao": {"type": "keyword"},
                "nivel_fonte": {"type": "keyword"},
                "tipo": {"type": "keyword"},
                "data": {"type": "keyword"},
                "url": {"type": "keyword"},
                "casos": {"type": "keyword"},
                "corpo": {"type": "text", "analyzer": "portuguese"},
                "fonte": {"type": "keyword"},
            }
        },
    }
    with httpx.Client(timeout=30.0) as client:
        exists = client.head(f"{os_url()}/{INDEX}")
        if exists.status_code == 404:
            client.put(f"{os_url()}/{INDEX}", json=mapping)


def index_document(doc: dict[str, Any]) -> bool:
    ensure_index()
    body = {
        "id": doc.get("id"),
        "titulo": doc.get("titulo") or doc.get("nome") or "",
        "orgao": doc.get("orgao"),
        "nivel_fonte": doc.get("nivel_fonte"),
        "tipo": doc.get("tipo"),
        "data": doc.get("data"),
        "url": doc.get("url") or doc.get("url_ref"),
        "casos": doc.get("casos") or [],
        "corpo": doc.get("corpo") or doc.get("nota") or doc.get("titulo") or "",
        "fonte": doc.get("fonte") or "kb",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.put(f"{os_url()}/{INDEX}/_doc/{body['id']}", json=body)
        return r.status_code in (200, 201)


def search_docs(q: str, size: int = 10) -> list[dict[str, Any]]:
    if not q.strip():
        return []
    ensure_index()
    query = {
        "size": size,
        "query": {
            "multi_match": {
                "query": q,
                "fields": ["titulo^3", "corpo", "orgao", "casos"],
                "type": "best_fields",
            }
        },
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(f"{os_url()}/{INDEX}/_search", json=query)
            r.raise_for_status()
            hits = r.json().get("hits", {}).get("hits", [])
            return [
                {**h.get("_source", {}), "_score": h.get("_score")} for h in hits
            ]
    except Exception:
        return []
