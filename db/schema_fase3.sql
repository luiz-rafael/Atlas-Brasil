-- ATLAS BRASIL — schema Fase 3 (entity resolution + embeddings)
-- Aplicar: psql $DATABASE_URL -f db/schema_fase3.sql

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

CREATE INDEX IF NOT EXISTS idx_entity_mentions_doc ON entity_mentions(doc_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_ent ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_status ON entity_mentions(status);

CREATE TABLE IF NOT EXISTS documento_embeddings (
  doc_id TEXT PRIMARY KEY,
  modelo TEXT NOT NULL,
  dim INT NOT NULL,
  embedding REAL[] NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS er_revisao (
  id BIGSERIAL PRIMARY KEY,
  mention_id BIGINT REFERENCES entity_mentions(id) ON DELETE CASCADE,
  decisao TEXT NOT NULL, -- aceitar | rejeitar | mesclar
  nota TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
