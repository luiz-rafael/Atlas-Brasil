-- Fase C serving indicadores (aplicar em bases já existentes)
-- psql "$DATABASE_URL" -f db/migrations/002_serving_indicadores.sql

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

-- Espelho leve Iceberg/gold documentos (colunas opcionais)
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
