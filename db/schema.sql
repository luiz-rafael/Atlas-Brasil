-- ATLAS BRASIL — schema relacional (tecnologias_aplicadas §6)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS entidades (
  id TEXT PRIMARY KEY,
  tipo TEXT NOT NULL,
  nome TEXT NOT NULL,
  partido TEXT,
  cargo_atual TEXT,
  no_poder_2026 BOOLEAN DEFAULT FALSE,
  uf TEXT,
  tags TEXT[] DEFAULT '{}',
  aliases TEXT[] DEFAULT '{}',
  isolada BOOLEAN DEFAULT FALSE,
  nota TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS casos (
  id TEXT PRIMARY KEY,
  nome TEXT NOT NULL,
  periodo TEXT,
  eixos TEXT[] DEFAULT '{}',
  nota TEXT
);

CREATE TABLE IF NOT EXISTS documentos (
  id TEXT PRIMARY KEY,
  tipo TEXT,
  titulo TEXT NOT NULL,
  data TEXT,
  nivel_fonte TEXT,
  orgao TEXT,
  url TEXT,
  url_pendente BOOLEAN DEFAULT FALSE,
  casos TEXT[] DEFAULT '{}',
  nota TEXT
);

CREATE TABLE IF NOT EXISTS relacoes (
  id TEXT PRIMARY KEY,
  origem TEXT NOT NULL,
  destino TEXT NOT NULL,
  tipo TEXT NOT NULL,
  periodo TEXT,
  contexto TEXT,
  justificativa_documental TEXT NOT NULL,
  grau_confirmacao TEXT NOT NULL,
  caso_id TEXT,
  fonte_ids TEXT[] DEFAULT '{}',
  fontes TEXT[] DEFAULT '{}',
  nota TEXT,
  url_pendente BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS registros_pessoa_caso (
  id TEXT PRIMARY KEY,
  pessoa_id TEXT NOT NULL,
  caso_id TEXT NOT NULL,
  status TEXT,
  camada TEXT,
  acusacao TEXT,
  situacao_atual TEXT,
  fonte_ids TEXT[] DEFAULT '{}',
  fontes TEXT[] DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS timeline (
  id TEXT PRIMARY KEY,
  data TEXT,
  eixo TEXT,
  titulo TEXT,
  caso_ids TEXT[] DEFAULT '{}',
  governo_id TEXT,
  fontes TEXT[] DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS fluxos_financeiros (
  id TEXT PRIMARY KEY,
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS correcoes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entidade_id TEXT,
  relacao_id TEXT,
  mensagem TEXT NOT NULL,
  email TEXT,
  status TEXT DEFAULT 'aberta',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trilhas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  titulo TEXT,
  passos TEXT[] NOT NULL,
  modo TEXT DEFAULT 'leigo',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta_sistema (
  chave TEXT PRIMARY KEY,
  valor JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entidades_tipo ON entidades(tipo);
CREATE INDEX IF NOT EXISTS idx_entidades_nome ON entidades(nome);
CREATE INDEX IF NOT EXISTS idx_relacoes_tipo ON relacoes(tipo);
CREATE INDEX IF NOT EXISTS idx_docs_nivel ON documentos(nivel_fonte);

-- Fase 3
CREATE TABLE IF NOT EXISTS entity_mentions (
  id BIGSERIAL PRIMARY KEY,
  doc_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  mention TEXT,
  score REAL,
  method TEXT,
  status TEXT DEFAULT 'candidato',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documento_embeddings (
  doc_id TEXT PRIMARY KEY,
  modelo TEXT NOT NULL,
  dim INT NOT NULL,
  embedding REAL[] NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fase 4
CREATE TABLE IF NOT EXISTS documento_embeddings_dense (
  doc_id TEXT PRIMARY KEY,
  modelo TEXT NOT NULL,
  dim INT NOT NULL,
  embedding REAL[] NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_api (
  id BIGSERIAL PRIMARY KEY,
  request_id TEXT,
  method TEXT,
  path TEXT,
  status INT,
  latency_ms REAL,
  region TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fase A — control plane (arquitetura.md)
CREATE TABLE IF NOT EXISTS source_state (
  source_id TEXT NOT NULL,
  dataset_id TEXT NOT NULL DEFAULT '',
  last_checked_at TIMESTAMPTZ,
  last_successful_at TIMESTAMPTZ,
  last_hash TEXT,
  last_cursor TEXT,
  last_page TEXT,
  last_record_timestamp TIMESTAMPTZ,
  last_run_id TEXT,
  health_status TEXT NOT NULL DEFAULT 'UNKNOWN',
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (source_id, dataset_id)
);

CREATE TABLE IF NOT EXISTS ingestion_run (
  run_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  dataset_id TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  records_found BIGINT,
  records_processed BIGINT,
  records_inserted BIGINT,
  records_updated BIGINT,
  records_rejected BIGINT,
  records_quarantined BIGINT,
  status TEXT NOT NULL DEFAULT 'RUNNING',
  error TEXT,
  counts JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS quarantine (
  id BIGSERIAL PRIMARY KEY,
  source_id TEXT NOT NULL,
  dataset_id TEXT,
  run_id TEXT,
  reason_code TEXT NOT NULL,
  payload JSONB NOT NULL,
  entity_hint TEXT,
  status TEXT NOT NULL DEFAULT 'OPEN',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_run_source ON ingestion_run(source_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_quarantine_status ON quarantine(status, source_id);
CREATE INDEX IF NOT EXISTS idx_source_state_health ON source_state(health_status);

-- Fase C — serving indicadores (Postgres canônico)
CREATE TABLE IF NOT EXISTS territories (
  territory_id TEXT PRIMARY KEY,
  ibge_code TEXT,
  name TEXT,
  territory_type TEXT,
  state_code TEXT,
  state_name TEXT,
  region_code TEXT,
  region_name TEXT,
  fonte TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS indicators (
  indicator_id TEXT PRIMARY KEY,
  name TEXT,
  display_name TEXT,
  description TEXT,
  category TEXT,
  subcategory TEXT,
  unit TEXT,
  source_id TEXT,
  dataset_id TEXT,
  minimum_geographic_level TEXT,
  methodology_url TEXT,
  notes TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS observations (
  observation_id TEXT PRIMARY KEY,
  indicator_id TEXT NOT NULL,
  territory_id TEXT NOT NULL,
  reference_year INT NOT NULL,
  value DOUBLE PRECISION,
  unit TEXT,
  source_id TEXT,
  geographic_level TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_observations_ind_year
  ON observations (indicator_id, reference_year);
CREATE INDEX IF NOT EXISTS idx_observations_terr_ind
  ON observations (territory_id, indicator_id);
CREATE INDEX IF NOT EXISTS idx_observations_year
  ON observations (reference_year);
CREATE INDEX IF NOT EXISTS idx_territories_type_state
  ON territories (territory_type, state_code);

ALTER TABLE documentos ADD COLUMN IF NOT EXISTS fonte TEXT;
ALTER TABLE documentos ADD COLUMN IF NOT EXISTS source_system TEXT;
ALTER TABLE documentos ADD COLUMN IF NOT EXISTS is_primary BOOLEAN;
ALTER TABLE documentos ADD COLUMN IF NOT EXISTS titulo_len INT;

CREATE TABLE IF NOT EXISTS gold_indicadores_uf_latest (
  territory_id TEXT NOT NULL,
  indicator_id TEXT NOT NULL,
  reference_year INT,
  value DOUBLE PRECISION,
  unit TEXT,
  source_id TEXT,
  PRIMARY KEY (territory_id, indicator_id)
);
