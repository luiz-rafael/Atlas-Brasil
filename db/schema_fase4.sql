-- ATLAS BRASIL — Fase 4
-- Observabilidade + embeddings densos
-- psql $DATABASE_URL -f db/schema_fase4.sql

CREATE TABLE IF NOT EXISTS documento_embeddings_dense (
  doc_id TEXT PRIMARY KEY,
  modelo TEXT NOT NULL,
  dim INT NOT NULL,
  embedding REAL[] NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_emb_dense_modelo ON documento_embeddings_dense(modelo);

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

CREATE TABLE IF NOT EXISTS sistema_regiao (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO sistema_regiao (chave, valor)
VALUES ('atlas_region', COALESCE(current_setting('app.atlas_region', true), 'local'))
ON CONFLICT (chave) DO NOTHING;
