"""Métricas Prometheus (Fase 4)."""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REQUESTS = Counter(
    "atlas_http_requests_total",
    "Total de requisições HTTP",
    ["method", "path", "status"],
)
LATENCY = Histogram(
    "atlas_http_request_duration_seconds",
    "Latência HTTP",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
KB_ENTIDADES = Gauge("atlas_kb_entidades", "Entidades na KB")
KB_RELACOES = Gauge("atlas_kb_relacoes", "Relações na KB")
DEP_UP = Gauge("atlas_dependency_up", "Dependência saudável (1/0)", ["name"])


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in ("/metrics", "/live"):
            return await call_next(request)
        path = request.url.path
        # agrupa ids dinâmicos
        for prefix in ("/v1/grafo/subgrafo", "/v1/ia/ask"):
            if path.startswith(prefix):
                path = prefix
                break
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
            REQUESTS.labels(request.method, path, str(status)).inc()


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def refresh_kb_gauges(kb: dict) -> None:
    KB_ENTIDADES.set(len(kb.get("entidades") or []))
    KB_RELACOES.set(len(kb.get("relacoes") or []))


def set_dep(name: str, ok: bool) -> None:
    DEP_UP.labels(name).set(1 if ok else 0)
