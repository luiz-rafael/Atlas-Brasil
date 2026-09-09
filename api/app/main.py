from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.cache import cache_get, cache_set
from app.db import get_conn, ping_postgres
from app.graph_ops import (
    communities,
    hubs,
    meeting_points,
    shortest_paths,
    subgraph,
)
from app.graphrag import answer as graphrag_answer
from app.kb_loader import load_kb
from app import serving_indicadores as serving_ind
from app import serving_contas as serving_contas
from app import serving_pessoas as serving_pessoas
from app import serving_administrations as serving_adm
from app import serving_territorio as serving_terr
from app import serving_empresas as serving_empresas
from app import serving_casos as serving_casos
from app import serving_dinheiro as serving_dinheiro
from app import serving_magistrados as serving_mag
from app.neo4j_client import ping_neo4j, count_nodes as neo4j_count
from app.opensearch_client import ping_opensearch, search_docs
from app.entity_resolution import resolve as er_resolve, recent_batch as er_batch
from app.semantic import search as semantic_search, reload_index as semantic_reload
from app.gds_lite import louvain as gds_louvain
from app.dense_search import search as dense_search, reload as dense_reload
from app.metrics import MetricsMiddleware, metrics_response, refresh_kb_gauges, set_dep


@asynccontextmanager
async def lifespan(_app: FastAPI):
    kb = load_kb()
    refresh_kb_gauges(kb)
    yield


app = FastAPI(
    title="ATLAS BRASIL API",
    version="4.0.0",
    description="API unificada — Fases 1–4 (web). Mobile adiado.",
    lifespan=lifespan,
)

origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MetricsMiddleware)

DISCLAIMER = (
    "Compartilhar nó ou caminho não implica culpa, aliança ilícita ou responsabilidade criminal. "
    "O Atlas documenta; não acusa."
)
REGION = os.getenv("ATLAS_REGION", "local")


class CorrecaoIn(BaseModel):
    mensagem: str = Field(min_length=10)
    entidade_id: str | None = None
    relacao_id: str | None = None
    email: str | None = None


class TrilhaIn(BaseModel):
    titulo: str | None = None
    passos: list[str]
    modo: str = "leigo"


@app.get("/live")
def live() -> dict[str, Any]:
    return {"status": "alive", "region": REGION}


@app.get("/ready")
def ready() -> dict[str, Any]:
    pg = ping_postgres()
    os_ok = ping_opensearch()
    redis_ok = cache_get("_ping") is not None or cache_set("_ping", "1", 30)
    set_dep("postgres", pg)
    set_dep("opensearch", os_ok)
    set_dep("redis", bool(redis_ok))
    ok = pg  # mínimo: postgres
    body = {
        "status": "ready" if ok else "degraded",
        "region": REGION,
        "postgres": pg,
        "redis": bool(redis_ok),
        "opensearch": os_ok,
    }
    if not ok:
        raise HTTPException(503, detail=body)
    return body


@app.get("/metrics")
def metrics() -> Any:
    return metrics_response()


@app.get("/health")
def health() -> dict[str, Any]:
    kb = load_kb()
    refresh_kb_gauges(kb)
    root = Path(__file__).resolve().parents[2]
    emb_ok = (root / "data" / "nlp" / "embeddings.jsonl").exists()
    dense_ok = (root / "data" / "nlp" / "embeddings_dense.jsonl").exists()
    pg = ping_postgres()
    os_ok = ping_opensearch()
    redis_ok = cache_get("_ping") is not None or cache_set("_ping", "1", 30)
    set_dep("postgres", pg)
    set_dep("opensearch", os_ok)
    set_dep("redis", bool(redis_ok))
    return {
        "ok": True,
        "produto": "ATLAS BRASIL",
        "api": "4.0.0",
        "fase": 4,
        "region": REGION,
        "superficie": "web",
        "mobile": "adiado",
        "kb": kb.get("meta", {}).get("versao"),
        "postgres": pg,
        "redis": bool(redis_ok),
        "opensearch": os_ok,
        "neo4j_env": bool(os.getenv("NEO4J_URI")),
        "kafka_bootstrap": os.getenv("KAFKA_BOOTSTRAP"),
        "embeddings": emb_ok,
        "embeddings_dense": dense_ok,
        "observabilidade": {
            "metrics": "/metrics",
            "prometheus": "http://localhost:9090",
            "grafana": "http://localhost:3002",
        },
        "disclaimer": DISCLAIMER,
    }


@app.get("/v1/meta")
def meta() -> dict[str, Any]:
    kb = load_kb()
    return {
        "meta": kb.get("meta"),
        "modulos": [
            "grafo",
            "hubs",
            "comunidades",
            "caminho",
            "encontros",
            "ia",
            "busca_opensearch",
            "entity_resolution",
            "busca_semantica",
            "gds_lite",
            "busca_densa",
            "observabilidade",
            "timeline",
            "fontes",
            "fontes_registry",
            "fontes_coverage",
            "dinheiro",
            "crime_organizado",
            "investigar",
            "comparar",
        ],
        "camadas": ["fato", "acusacao", "hipotese"],
        "disclaimer": DISCLAIMER,
    }


@app.get("/v1/busca")
def busca(q: str = Query("")) -> dict[str, Any]:
    key = f"busca:{q.lower()}"
    hit = cache_get(key)
    if hit:
        return hit
    kb = load_kb()
    s = q.strip().lower()
    out: dict[str, list] = {
        "pessoas": [],
        "empresas": [],
        "partidos": [],
        "instituicoes": [],
        "casos": [],
        "documentos": [],
        "faccoes": [],
        "operacoes": [],
    }
    if not s:
        return out

    def score(nome: str, extra: list[str]) -> int:
        n = nome.lower()
        if n == s:
            return 100
        if n.startswith(s):
            return 80
        if s in n:
            return 60
        for a in extra:
            if s in a.lower():
                return 50
        return 0

    scored: list[tuple[int, str, dict]] = []
    for e in kb.get("entidades", []):
        if e.get("isolada"):
            continue
        sc = score(
            e.get("nome", ""),
            [e.get("partido") or "", *(e.get("tags") or []), *(e.get("aliases") or [])],
        )
        if sc:
            scored.append((sc, e.get("tipo", ""), e))
    for c in kb.get("casos", []):
        sc = score(c.get("nome", ""), c.get("eixos") or [])
        if sc:
            scored.append((sc, "caso", c))
    for d in kb.get("documentos", []):
        sc = score(d.get("titulo", ""), [d.get("orgao") or ""])
        if sc:
            scored.append((sc, "documento", d))
    scored.sort(key=lambda x: -x[0])
    map_tipo = {
        "pessoa": "pessoas",
        "empresa": "empresas",
        "partido": "partidos",
        "instituicao": "instituicoes",
        "caso": "casos",
        "documento": "documentos",
        "faccao": "faccoes",
        "operacao": "operacoes",
    }
    for sc, tipo, item in scored:
        bucket = map_tipo.get(tipo)
        if bucket:
            out[bucket].append(item)
    cache_set(key, out, 60)
    return out


@app.get("/v1/grafo")
def grafo(
    centro_id: str | None = None,
    profundidade: int = 1,
    de: str | None = None,
    ate: str | None = None,
) -> dict[str, Any]:
    if not centro_id or centro_id == "macro":
        return {**subgraph(None, 0), "modo": "macro", "disclaimer": DISCLAIMER}
    return {
        **subgraph(centro_id, min(3, max(1, profundidade)), de=de, ate=ate),
        "disclaimer": DISCLAIMER,
    }


@app.get("/v1/grafo/caminho")
def caminho(a: str, b: str, max: int = 6) -> dict[str, Any]:
    return {**shortest_paths(a, b, max), "disclaimer": DISCLAIMER}


@app.get("/v1/grafo/encontros")
def encontros(a: str, b: str, depth: int = 2) -> dict[str, Any]:
    return {**meeting_points(a, b, depth), "disclaimer": DISCLAIMER}


@app.get("/v1/grafo/hubs")
def hubs_api(
    metric: str = "degree",
    tipo: str = "todos",
    de: str | None = None,
    ate: str | None = None,
    por_periodo: int = 0,
) -> dict[str, Any]:
    return hubs(metric, tipo=tipo, de=de, ate=ate, por_periodo=bool(por_periodo))


@app.get("/v1/grafo/comunidades")
def comunidades_api(
    mode: str = "comunidades",
    de: str | None = None,
    ate: str | None = None,
) -> dict[str, Any]:
    return communities(mode=mode, de=de, ate=ate)


@app.get("/v1/grafo/comparar")
def comparar(a: str, b: str) -> dict[str, Any]:
    ea = meeting_points(a, b, 2)
    path = shortest_paths(a, b, 6)
    return {
        "a": a,
        "b": b,
        "encontros": ea,
        "caminhos": path,
        "aviso": "Interseção ≠ aliança. Path ≠ culpa.",
        "disclaimer": DISCLAIMER,
    }


@app.get("/v1/timeline")
def timeline(
    caso_id: str | None = None,
    eixo: str | None = None,
    de: str | None = None,
    ate: str | None = None,
) -> list[dict]:
    kb = load_kb()
    items = kb.get("timeline") or []
    if caso_id:
        items = [t for t in items if caso_id in (t.get("caso_ids") or [])]
    if eixo:
        items = [t for t in items if t.get("eixo") == eixo]
    if de:
        items = [t for t in items if str(t.get("data", "9999"))[:4] >= de]
    if ate:
        items = [t for t in items if str(t.get("data", "0000"))[:4] <= ate]
    return items


@app.get("/v1/timeline/como-chegamos")
def como_chegamos(evento_id: str) -> dict[str, Any]:
    kb = load_kb()
    items = sorted(kb.get("timeline") or [], key=lambda t: str(t.get("data", "")))
    idx = next((i for i, t in enumerate(items) if t.get("id") == evento_id), None)
    if idx is None:
        raise HTTPException(404, "Evento não encontrado")
    chain = items[: idx + 1]
    return {
        "evento": items[idx],
        "cadeia": chain,
        "total": len(chain),
        "disclaimer": DISCLAIMER,
    }


@app.get("/v1/fontes")
def fontes(nivel: str | None = None, orgao: str | None = None) -> list[dict]:
    pg_docs = serving_ind.list_documentos(nivel=nivel, orgao=orgao)
    if pg_docs is not None:
        return pg_docs
    kb = load_kb()
    docs = kb.get("documentos") or []
    if nivel:
        docs = [d for d in docs if d.get("nivel_fonte") == nivel]
    if orgao:
        docs = [d for d in docs if (d.get("orgao") or "").lower() == orgao.lower()]
    return docs


@app.get("/v1/empresas")
def empresas_list(
    q: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_empresas.list_empresas(q=q, limit=limit, offset=offset)


@app.get("/v1/empresas/{company_id}")
def empresas_detail(company_id: str) -> dict[str, Any]:
    data = serving_empresas.get_empresa(company_id)
    if not data:
        raise HTTPException(404, detail="empresa não encontrada")
    return data


@app.get("/v1/casos")
def casos_list(
    q: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_casos.list_casos(q=q, limit=limit, offset=offset)


@app.get("/v1/casos/{case_id}")
def casos_detail(case_id: str) -> dict[str, Any]:
    data = serving_casos.get_caso(case_id)
    if not data:
        raise HTTPException(404, detail="caso não encontrado")
    return data


@app.get("/v1/dinheiro")
def dinheiro_index() -> dict[str, Any]:
    return serving_dinheiro.dinheiro_resumo()


@app.get("/v1/dinheiro/{tab}")
def dinheiro_tab(
    tab: str,
    caso_id: str | None = None,
    uf: str | None = None,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    return serving_dinheiro.dinheiro_categoria(
        tab, caso_id=caso_id, uf=uf, q=q, limit=limit
    )


@app.get("/v1/magistrados")
def magistrados_list(
    q: str | None = None,
    court_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_mag.list_magistrados(
        q=q, court_id=court_id, limit=limit, offset=offset
    )


@app.get("/v1/magistrados/stats")
def magistrados_stats(
    court_id: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Agregados remuneração (timeline / tribunal). Remuneração ≠ orçamento Justiça."""
    return serving_mag.stats_magistrados(court_id=court_id, year=year)


@app.get("/v1/magistrados/{magistrate_id}")
def magistrados_detail(magistrate_id: str) -> dict[str, Any]:
    data = serving_mag.get_magistrado(magistrate_id)
    if not data:
        raise HTTPException(404, detail="magistrado não encontrado")
    return data


@app.get("/v1/pessoas")
def pessoas_list(
    q: str | None = None,
    no_poder: str | None = None,
    escopo: str | None = None,
    partido: str | None = None,
    uf: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_pessoas.list_pessoas(
        q=q,
        no_poder=no_poder,
        escopo=escopo,
        partido=partido,
        uf=uf,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/pessoas/{person_id}")
def pessoas_detail(person_id: str) -> dict[str, Any]:
    data = serving_pessoas.get_pessoa(person_id)
    if not data:
        raise HTTPException(404, detail="pessoa não encontrada")
    return data


@app.get("/v1/administrations")
def administrations_list(
    state_code: str | None = None,
    territory_id: str | None = None,
    year: int | None = None,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_adm.list_administrations(
        state_code=state_code,
        territory_id=territory_id,
        year=year,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/administrations/{administration_id}")
def administrations_detail(administration_id: str) -> dict[str, Any]:
    row = serving_adm.get_administration(administration_id)
    if not row:
        raise HTTPException(404, detail="administração não encontrada")
    return row


@app.get("/v1/mandates")
def mandates_list(
    state_code: str | None = None,
    person_id: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
) -> dict[str, Any]:
    return serving_adm.list_mandates(
        state_code=state_code, person_id=person_id, limit=limit
    )


@app.get("/v1/territorios/{territory_id}/contexto")
def territorio_contexto(
    territory_id: str,
    year: int = Query(...),
    indicators: str | None = Query(
        None, description="CSV de indicator_ids (opcional)"
    ),
) -> dict[str, Any]:
    inds = (
        [x.strip() for x in indicators.split(",") if x.strip()]
        if indicators
        else None
    )
    try:
        return serving_terr.territory_year_context(
            territory_id, year, indicator_ids=inds
        )
    except Exception as e:
        raise HTTPException(503, detail=str(e)) from e


@app.get("/v1/territorios/{territory_id}/timeline")
def territorio_timeline(
    territory_id: str,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Timeline de administrações estaduais (eventos com intervalo)."""
    tid = territory_id
    if len(tid) == 2 and tid.isalpha():
        tid = f"uf_{tid.upper()}"
    uf = tid.replace("uf_", "").upper() if tid.startswith("uf_") else None
    data = serving_adm.list_administrations(
        territory_id=tid if tid.startswith("uf_") else None,
        state_code=uf,
        limit=limit,
    )
    events = [
        {
            "event_id": a.get("administration_id"),
            "event_type": "ADMINISTRATION",
            "label": a.get("executive_person_name") or a.get("administration_id"),
            "start_date": a.get("start_date"),
            "end_date": a.get("end_date"),
            "person_id": a.get("executive_person_id"),
            "party": a.get("party_at_start"),
            "source": a.get("source"),
        }
        for a in data.get("items") or []
    ]
    events.sort(key=lambda e: e.get("start_date") or "", reverse=True)
    return {
        "ok": True,
        "territory_id": tid,
        "events": events,
        "total": len(events),
        "disclaimer": DISCLAIMER,
    }


@app.get("/v1/indicadores/meta")
def indicadores_meta() -> dict[str, Any]:
    try:
        return {**serving_ind.meta(), "disclaimer": DISCLAIMER}
    except Exception as e:
        raise HTTPException(503, detail=str(e)) from e


@app.get("/v1/indicadores")
def indicadores_catalog(
    include_territories: bool = Query(False),
    territory_type: str | None = None,
    state_code: str | None = None,
) -> dict[str, Any]:
    try:
        out: dict[str, Any] = {
            "indicators": serving_ind.list_indicators(),
            "meta": serving_ind.meta(),
            "disclaimer": DISCLAIMER,
        }
        if include_territories:
            out["territories"] = serving_ind.list_territories(
                territory_type=territory_type,
                state_code=state_code,
            )
        return out
    except Exception as e:
        raise HTTPException(503, detail=str(e)) from e


@app.get("/v1/indicadores/territories/{territory_id}")
def indicadores_territory(territory_id: str) -> dict[str, Any]:
    row = serving_ind.get_territory(territory_id)
    if not row:
        raise HTTPException(404, detail="território não encontrado")
    return row


@app.get("/v1/indicadores/years")
def indicadores_years(
    indicator_id: str = Query("ind_pop_estimada"),
) -> dict[str, Any]:
    try:
        years = serving_ind.years_for_indicator(indicator_id)
        return {"indicator_id": indicator_id, "years": years}
    except Exception as e:
        raise HTTPException(503, detail=str(e)) from e


@app.get("/v1/indicadores/observations")
def indicadores_observations(
    indicator_id: str = Query(...),
    year: int | None = None,
    level: str | None = Query(None, pattern="^(STATE|MUNICIPALITY)$"),
    uf: str | None = None,
    territory_id: str | None = None,
    limit: int = Query(20000, ge=1, le=100000),
) -> dict[str, Any]:
    try:
        rows = serving_ind.observations(
            indicator_id=indicator_id,
            year=year,
            level=level,
            uf=uf,
            territory_id=territory_id,
            limit=limit,
        )
        return {
            "indicator_id": indicator_id,
            "year": year,
            "level": level,
            "count": len(rows),
            "observations": rows,
            "disclaimer": DISCLAIMER,
        }
    except Exception as e:
        raise HTTPException(503, detail=str(e)) from e


@app.get("/v1/indicadores/series")
def indicadores_series(
    territory_id: str = Query(...),
    indicator_id: str = Query(...),
) -> dict[str, Any]:
    try:
        rows = serving_ind.series(territory_id, indicator_id)
        return {
            "territory_id": territory_id,
            "indicator_id": indicator_id,
            "count": len(rows),
            "observations": rows,
            "disclaimer": DISCLAIMER,
        }
    except Exception as e:
        raise HTTPException(503, detail=str(e)) from e


@app.get("/v1/indicadores/choropleth")
def indicadores_choropleth(
    year: int = Query(...),
    indicator_id: str = Query("ind_pop_estimada"),
) -> dict[str, Any]:
    try:
        values = serving_ind.choropleth(year, indicator_id)
        return {
            "year": year,
            "indicator_id": indicator_id,
            "values": values,
            "disclaimer": DISCLAIMER,
        }
    except Exception as e:
        raise HTTPException(503, detail=str(e)) from e


@app.get("/v1/fontes/registry")
def fontes_registry() -> dict[str, Any]:
    """SOURCE_REGISTRY machine-readable (fonte de verdade da coleta)."""
    root = Path(__file__).resolve().parents[2]
    path = Path(os.getenv("ATLAS_SOURCE_REGISTRY", root / "data" / "source_registry.json"))
    if not path.is_file():
        raise HTTPException(404, detail="source_registry.json ausente")
    import json

    reg = json.loads(path.read_text(encoding="utf-8"))
    return {**reg, "disclaimer": DISCLAIMER}


@app.get("/v1/fontes/coverage")
def fontes_coverage() -> dict[str, Any]:
    """Cobertura do registry + última ingestão (Onda F1)."""
    root = Path(__file__).resolve().parents[2]
    report = root / "pipelines" / "reports" / "coverage_f1.json"
    import json
    import sys

    sys.path.insert(0, str(root))
    try:
        from pipelines.registry import coverage_report

        live = coverage_report()
    except Exception as e:
        live = {"error": str(e), "sources": []}
    if report.is_file():
        try:
            saved = json.loads(report.read_text(encoding="utf-8"))
        except Exception:
            saved = None
    else:
        saved = None
    return {
        "live": live,
        "report_path": "pipelines/reports/coverage_f1.json",
        "saved": saved,
        "disclaimer": DISCLAIMER,
    }


@app.get("/v1/financeiro")
def financeiro(caso_id: str | None = None) -> list[dict]:
    kb = load_kb()
    fluxos = kb.get("fluxos_financeiros") or []
    if caso_id:
        fluxos = [f for f in fluxos if f.get("caso_id") == caso_id]
    return fluxos


@app.get("/v1/contas/resumo")
def contas_resumo(year: int = Query(..., ge=1990, le=2100)) -> dict[str, Any]:
    """Resumo Contas do Brasil (canônico). Não inventa déficit = RFB − despesa."""
    cache_key = f"contas:resumo:{year}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    data = serving_contas.resumo(year)
    cache_set(cache_key, data, ttl=300)
    return data


@app.get("/v1/contas/carga-tributaria")
def contas_carga_tributaria() -> dict[str, Any]:
    """Série anual carga tributária (% PIB) — CTB / RFB."""
    cache_key = "contas:carga_tributaria:series"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    data = serving_contas.list_carga_tributaria()
    cache_set(cache_key, data, ttl=600)
    return data


@app.get("/v1/contas/receitas")
def contas_receitas(
    year: int | None = Query(None, ge=1990, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    territory_id: str | None = None,
    government_level: str | None = None,
    source: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_contas.list_receitas(
        year=year,
        month=month,
        territory_id=territory_id,
        government_level=government_level,
        source=source,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/contas/despesas")
def contas_despesas(
    year: int | None = Query(None, ge=1990, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    territory_id: str | None = None,
    government_level: str | None = None,
    source: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_contas.list_despesas(
        year=year,
        month=month,
        territory_id=territory_id,
        government_level=government_level,
        source=source,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/contas/resultado-fiscal")
def contas_resultado_fiscal(
    year: int | None = Query(None, ge=1990, le=2100),
    territory_id: str | None = "terr_br",
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_contas.list_resultado_fiscal(
        year=year,
        territory_id=territory_id,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/contas/divida")
def contas_divida(
    year: int | None = Query(None, ge=1990, le=2100),
    debt_indicator: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_contas.list_divida(
        year=year,
        debt_indicator=debt_indicator,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/contas/renuncias")
def contas_renuncias(
    year: int | None = Query(None, ge=1990, le=2100),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    view: str = Query("aggregate", description="aggregate|beneficiarios"),
) -> dict[str, Any]:
    return serving_contas.list_renuncias(
        year=year, limit=limit, offset=offset, view=view
    )


@app.get("/v1/contas/pessoal")
def contas_pessoal(
    year: int | None = Query(None, ge=1990, le=2100),
    territory_id: str | None = None,
    government_level: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_contas.list_pessoal(
        year=year,
        territory_id=territory_id,
        government_level=government_level,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/contas/cno")
def contas_cno(
    uf: str | None = Query(None, min_length=2, max_length=2),
    cnpj: str | None = Query(None, min_length=14, max_length=18),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return serving_contas.list_cno(uf=uf, cnpj=cnpj, limit=limit, offset=offset)


@app.get("/v1/contas/territorios/{territory_id}")
def contas_territorio(
    territory_id: str,
    year: int | None = Query(None, ge=1990, le=2100),
) -> dict[str, Any]:
    return serving_contas.territorio(territory_id, year=year)


@app.get("/v1/poder/2026")
def poder_2026() -> dict:
    return load_kb().get("mapa_poder_2026") or {}


@app.post("/v1/correcoes")
def criar_correcao(body: CorrecaoIn) -> dict[str, Any]:
    conn = get_conn()
    if not conn:
        # fallback arquivo
        path = Path(os.getenv("KB_PATH", "")).parent / "correcoes.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(body.model_dump_json() + "\n")
        return {"ok": True, "storage": "file", "disclaimer": DISCLAIMER}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO correcoes (entidade_id, relacao_id, mensagem, email)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (body.entidade_id, body.relacao_id, body.mensagem, body.email),
        )
        rid = cur.fetchone()[0]
        conn.commit()
    return {"ok": True, "id": str(rid), "storage": "postgres"}


@app.post("/v1/trilhas")
def salvar_trilha(body: TrilhaIn) -> dict[str, Any]:
    conn = get_conn()
    if not conn:
        return {"ok": True, "storage": "memory", "passos": body.passos}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trilhas (titulo, passos, modo)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (body.titulo, body.passos, body.modo),
        )
        rid = cur.fetchone()[0]
        conn.commit()
    return {"ok": True, "id": str(rid), "share": f"/investigar?trilha={','.join(body.passos)}"}


class IaAskIn(BaseModel):
    pergunta: str = Field(min_length=3)


@app.post("/v1/ia/ask")
def ia_ask(body: IaAskIn) -> dict[str, Any]:
    return graphrag_answer(body.pergunta)


@app.get("/v1/ia/ask")
def ia_ask_get(q: str = Query(..., min_length=3)) -> dict[str, Any]:
    return graphrag_answer(q)


@app.get("/v1/busca/opensearch")
def busca_os(q: str = Query(""), size: int = 20) -> dict[str, Any]:
    hits = search_docs(q, size=size) if q else []
    # Agrupar por tipo para o explorar
    by_tipo: dict[str, list] = {}
    for h in hits:
        t = h.get("tipo") or "documento"
        by_tipo.setdefault(t, []).append(h)
    return {
        "q": q,
        "hits": hits,
        "by_tipo": by_tipo,
        "opensearch": ping_opensearch(),
        "disclaimer": DISCLAIMER,
        "evidence": [
            {
                "id": h.get("id"),
                "titulo": h.get("titulo"),
                "fonte": h.get("fonte") or h.get("orgao"),
                "url": h.get("url"),
                "score": h.get("_score"),
                "trecho": (h.get("corpo") or "")[:280],
            }
            for h in hits[:12]
        ],
    }


@app.get("/v1/status/deps")
def status_deps() -> dict[str, Any]:
    return {
        "postgres": ping_postgres(),
        "opensearch": ping_opensearch(),
        "neo4j": ping_neo4j(),
        "neo4j_nodes": neo4j_count() if ping_neo4j() else 0,
        "disclaimer": DISCLAIMER,
    }


@app.get("/v1/nlp/resolve")
def nlp_resolve(q: str = Query(..., min_length=2), limit: int = 15) -> dict[str, Any]:
    return {
        "q": q,
        "entidades": er_resolve(q, limit=limit),
        "disclaimer": "Candidatos de resolução — não criam arestas automaticamente.",
    }


@app.get("/v1/nlp/mentions")
def nlp_mentions(limit: int = 40) -> dict[str, Any]:
    return er_batch(limit=limit)


@app.get("/v1/busca/semantica")
def busca_semantica(q: str = Query(""), size: int = 10) -> dict[str, Any]:
    return {**semantic_search(q, size=size), "disclaimer": DISCLAIMER}


@app.post("/v1/busca/semantica/reload")
def busca_semantica_reload() -> dict[str, Any]:
    semantic_reload()
    return {"ok": True}


@app.get("/v1/grafo/gds/louvain")
def gds_louvain_api(
    de: str | None = None,
    ate: str | None = None,
) -> dict[str, Any]:
    return {**gds_louvain(de=de, ate=ate), "disclaimer": DISCLAIMER}


@app.get("/v1/busca/densa")
def busca_densa(q: str = Query(""), size: int = 10) -> dict[str, Any]:
    return {**dense_search(q, size=size), "disclaimer": DISCLAIMER}


@app.post("/v1/busca/densa/reload")
def busca_densa_reload() -> dict[str, Any]:
    dense_reload()
    return {"ok": True}


@app.get("/v1/status")
def status_stack() -> dict[str, Any]:
    """Resumo operacional para UI /status (web)."""
    return health()
