# Atlas Brasil

Plataforma de **transparência pública baseada em dados oficiais**: integra bases dispersas (eleições, legislativo, contas, contratos, empresas, indicadores, justiça) em um modelo canônico, histórico e rastreável — e expõe isso via API + aplicação web.

Este repositório contém **código e contratos**. Dados brutos, lake, KB JSON e segredos **não** entram no git (ver [O que não vai no repositório](#o-que-não-vai-no-repositório)).

---

## Princípios (não são marketing — são constraints de produto)

1. **A fonte não define o modelo do produto.** APIs mudam; o canônico (PERSON, COMPANY, ADMINISTRATION, …) precisa sobreviver.
2. **ENTITY ≠ EVENT ≠ OBSERVATION.** Pessoa/empresa existem; eleição/mandato acontecem; indicador/fiscal são medidos no tempo.
3. **Correlação ≠ causalidade.** Caminho em grafo ≠ relação direta afirmada ao usuário.
4. **Processo ≠ culpa.** Justiça é documentada com papel processual, temporalidade, fonte e evidência. Desfechos posteriores (arquivamento, absolvição, anulação) têm peso igual ou maior.
5. **IA não é fonte factual.** Cadeia: pergunta → (opcionalmente) LLM → dados/documentos → evidência → fonte.

Âncoras editoriais: *O Atlas não acusa. O Atlas documenta.* · *Você não precisa acreditar no Atlas. Confira a fonte.*

---

## Arquitetura (visão sênior)

```
Fontes oficiais
    │  (TSE, Câmara, Senado, Receita, PNCP, Tesouro/Siconfi, IBGE, DataJud, …)
    ▼
Orquestração (Airflow) + coletores (pipelines/ingest)
    │
    ├─► MinIO/S3 (raw mirror)
    └─► Lake medallion
            Bronze  → raw tipado + provenance
            Silver  → limpeza, normalização, chaves
            Gold    → canônico / serving-ready
                │
                ├─► PostgreSQL   (serving, séries, movimentos, SCD2, fiscais)
                ├─► Neo4j        (relações estáveis do knowledge graph)
                └─► OpenSearch   (busca / IR)
                        │
                        ▼
                   FastAPI (/v1/*)
                        │
                        ▼
                   Next.js (web)
```

**Decisão de storage:** milhões de movimentos/observações ficam no Postgres (e timeline). Neo4j guarda o que é relação relevante para consulta de grafo — não o dump completo do mundo.

**Knowledge graph vs visual graph:** o KG completo existe para a máquina; a UI recebe subgrafos com contexto. Evidência e proveniência são obrigatórias em relações fortes.

### Stack

| Camada | Tecnologia |
|--------|------------|
| Orquestração | Apache Airflow |
| Lake / object | MinIO (S3), Apache Iceberg (piloto), Polars / Spark |
| Serving OLTP / séries | PostgreSQL 16 |
| Knowledge graph | Neo4j 5 (+ APOC) |
| Busca | OpenSearch |
| Cache / fila | Redis, Redpanda (Kafka-compatible) |
| API | FastAPI (`api/`) |
| Web | Next.js 14 + Tailwind (`web/`) |
| Observabilidade | Prometheus + Grafana |

Contratos: `platform/api-contract-v1.json`, `platform/atlas-brasil-api-v2.json`.

---

## Layout do monorepo

| Pasta | Responsabilidade |
|-------|------------------|
| `api/` | FastAPI — serving `/v1/*`, clientes Neo4j/OpenSearch/Postgres, métricas |
| `web/` | App Next.js — exploração territorial, pessoas, contas, grafo, indicadores |
| `pipelines/` | Ingest → transform → load; `legal/`, `fiscal/`, `lakehouse/`, `catalog/` |
| `db/` | `schema.sql` (init) + `migrations/` versionadas |
| `airflow/` | DAGs (orquestram; coleta fica em `pipelines/`) |
| `src/` | Pacote Python paralelo (ex.: remuneração CNJ / magistrados) |
| `platform/` | Contratos OpenAPI/JSON |
| `tools/` | Sync, validate, smoke, utilitários locais |
| `tests/` | Pytest (cnj, fiscal, siconfi, lakehouse, serving) |
| `observabilidade/` | Prometheus + Grafana provisioning |
| `data/` | **Local only** — lake, KB, filas (gitignored, exceto mocks leves) |

---

## Modelo canônico (conceitos)

| Tipo | Exemplos | Ideia |
|------|----------|--------|
| **ENTITY** | PERSON, COMPANY, TERRITORY, DOCUMENT | Algo que *existe* |
| **EVENT** | eleição, mandato, movimento processual | Algo que *aconteceu* |
| **OBSERVATION** | indicador, carga tributária, série fiscal | Algo *medido* em período |

Outros conceitos de produto/serving: `ADMINISTRATION`, `MANDATE`, `CONTRACT`, `CAMPAIGN`, `LEGAL_CASE`, `CASE_PARTICIPATION`, `CASE_MOVEMENT` (append-only), `CASE_STATUS` (SCD2).

### Justiça / DataJud (gate, não espelho)

Não espelhamos o Judiciário. Coleta em níveis:

1. **OFFICIAL_REFERENCE** — NPU já ligado a entidade Atlas → lookup
2. **COMPANY_CONTEXT / PERSON_CONTEXT** — descoberta escopada (ex.: CNPJ), nunca dump nacional
3. **KNOWN_REFRESH** — processo já no Atlas; se `last_movement` igual → SKIP

`CASE_DISCOVERY` responde: *por que este processo está aqui?* Gate: evidência suficiente → INGEST; senão IGNORE / QUARANTINE (raw da fonte não é apagado).

Relações fortes (`CONVICTED_IN`, `ACQUITTED_IN`, …) **só com evidência** — nunca só por classe/assunto. Assunto processional ≠ culpa da pessoa.

Ver: `pipelines/legal/`, `db/migrations/003_legal_cases.sql`, `005_case_discovery.sql`, `004_legal_justice_model.sql`.

---

## Serviços locais (Docker)

```bash
docker compose up -d
# API no profile full:
docker compose --profile full up -d api
```

| Serviço | Host | Credencial de lab (trocar em produção) |
|---------|------|----------------------------------------|
| Postgres | `localhost:5433` | `atlas` / `atlasbrasil` · DB `atlas_brasil` |
| Neo4j | `7474` / `7687` | `neo4j` / `atlasbrasil` |
| Redis | `6379` | — |
| MinIO | `9000` · console `9001` | `atlasminio` / `atlasbrasilminio` |
| OpenSearch | `9200` | — |
| OS Dashboards | `5601` | — |
| Redpanda | `19092` | — |
| API | **`8001`→8000** | profile `full` |
| Prometheus | `9090` | — |
| Grafana | `3002` | `atlas` / `atlasbrasil` |

Airflow (opcional):

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow.yml --profile airflow up -d
# UI http://localhost:8080 · atlas / atlasbrasil
```

Senhas default do compose são **lab only**.

---

## Setup rápido

### 1. Segredos

```bash
cp .env.example .env
cp web/.env.local.example web/.env.local
```

Preencha no mínimo (quando for usar as fontes):

- `ATLAS_PORTAL_API_KEY` — chave interna do portal
- `ATLAS_DATAJUD_API_KEY` — [API Pública DataJud](https://datajud-wiki.cnj.jus.br/api-publica/acesso/)
- `NEXT_PUBLIC_ATLAS_API_URL=http://localhost:8001`

Nunca commite `.env` / `web/.env.local`.

### 2. Infra + API

```bash
docker compose up -d
docker compose --profile full up -d --build api
# health: http://localhost:8001/docs  (ou rota de health exposta)
```

API local (alternativa):

```bash
cd api && pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# ajuste NEXT_PUBLIC_ATLAS_API_URL se não usar o mapeamento 8001
```

### 3. Web

```bash
cd web && npm install && npm run dev
# http://localhost:3000
```

Sem Neo4j/Postgres populados, partes da UI caem em fallbacks (KB local em `data/` — você precisa gerar/carregar localmente).

### 4. Pipelines (exemplo)

```bash
pip install httpx polars pyarrow "psycopg[binary]" neo4j
python pipelines/run_onda1.py          # políticos federais
# ver pipelines/README.md para ondas F1/F2, fiscais, CNJ, etc.
```

Migrations:

```bash
python pipelines/ops/apply_migrations.py
```

---

## Fluxo de dados (detalhe)

1. **Extract** — `pipelines/ingest/*` (HTTP/CKAN/CSV/ZIP); Airflow chama e aplica `check_source_update` (SKIP se sem mudança).
2. **Bronze** — `data/lake/bronze/{source}/` + manifest/provenance; espelho opcional no MinIO.
3. **Silver** — tipagem, normalização, chaves naturais (CNPJ, NPU, id TSE, …).
4. **Entity resolution** — ligar a mesma PERSON/COMPANY entre fontes (heurísticas + regras; fuzzy de razão social não é chave).
5. **Gold / serving** — tabelas Postgres (`db/migrations/*`), export KB, load Neo4j/OpenSearch.
6. **API** — `api/app/serving_*.py` (pessoas, empresas, contas, território, magistrados, casos, …).
7. **Web** — preferência API-first; alguns módulos ainda leem artefatos locais de KB se o serving estiver vazio.

Catálogo de datasets: `pipelines/catalog/datasets.yaml`, `pipelines/catalog/canonical_map.yaml`.

---

## O que não vai no repositório

| Excluído | Motivo |
|----------|--------|
| `data/*` (exceto `.gitkeep` + `data/mocks/`) | Lake/KB pesados (centenas de MB–GB) |
| `web/data/` | Espelho local de KB |
| `.env`, `web/.env.local` | Segredos |
| `*.md` (exceto este `README.md`) | Docs internos ficam fora do público |
| `*.parquet`, `*.zip`, `*.sqlite` | Artefatos de coleta |
| `node_modules/`, `.next/`, venvs, `logs/` | Runtime |

Contribuidores precisam **gerar** o lake localmente a partir das fontes oficiais (ou usar mocks em `data/mocks/`).

---

## Contribuição (expectativa técnica)

Antes de abrir PR grande:

- Preserve proveniência (fonte, `observed_at` / `collected_at`, IDs oficiais).
- Não invente arestas sem evidência; prefira QUARANTINE a “ligar por nome”.
- Em justiça: papel processual explícito; nunca promover menção → condenação.
- Em indicadores/contas: série temporal ≠ atribuição causal a governo.
- Segredos só em env; exemplos comentados em `.env.example`.
- Testes em `tests/` quando tocar parsers, money, discovery legal ou serving.

Críticas bem-vindas especialmente em: **entity resolution**, **modelagem de grafo temporal**, **CASE_DISCOVERY**, e **limites do que a UI pode afirmar**.

---

## Status

Projeto em desenvolvimento ativo. Cobertura de fontes é **parcial** por desenho (escopo > dump). Volumes locais típicos já incluem milhões de observações de indicadores e dezenas/centenas de milhares de registros fiscais/eleitorais — isso **não** está versionado aqui.

Licença / governança do repositório público: a definir pelo mantenedor ao publicar o remote.
