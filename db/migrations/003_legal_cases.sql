-- LEGAL_CASE + CASE_MOVEMENT (DataJud normalizer)
-- Movimentos append-only; sem SCD2.

CREATE TABLE IF NOT EXISTS legal_cases (
  case_id TEXT PRIMARY KEY,
  process_number TEXT NOT NULL,
  process_digits TEXT,
  court TEXT,
  jurisdiction_degree TEXT,
  judging_body TEXT,
  procedural_class TEXT,
  procedural_class_code TEXT,
  subjects JSONB,
  system TEXT,
  electronic BOOLEAN,
  source TEXT NOT NULL DEFAULT 'cnj_datajud',
  datajud_alias TEXT,
  seed_source_id TEXT,
  seed_entity_id TEXT,
  first_seen_at TIMESTAMPTZ,
  last_checked_at TIMESTAMPTZ,
  raw_sha1 TEXT,
  attrs JSONB DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_legal_cases_digits
  ON legal_cases (process_digits)
  WHERE process_digits IS NOT NULL;

CREATE TABLE IF NOT EXISTS case_movements (
  movement_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES legal_cases(case_id) ON DELETE CASCADE,
  movement_code INT,
  movement_description TEXT,
  movement_date TIMESTAMPTZ,
  source_id TEXT NOT NULL DEFAULT 'cnj_datajud',
  raw_record_id TEXT,
  first_retrieved_at TIMESTAMPTZ,
  retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_case_movements_case_date
  ON case_movements (case_id, movement_date);

CREATE TABLE IF NOT EXISTS legal_events (
  legal_event_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES legal_cases(case_id) ON DELETE CASCADE,
  movement_id TEXT REFERENCES case_movements(movement_id),
  event_type TEXT NOT NULL,
  event_date TIMESTAMPTZ,
  source_id TEXT,
  classification_method TEXT,
  confidence TEXT,
  human_verified BOOLEAN DEFAULT FALSE,
  relation_type TEXT,
  notes TEXT,
  retrieved_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE legal_cases IS 'DataJud capa/metadados — não inteiro teor; Portaria CNJ 374/2026';
COMMENT ON TABLE case_movements IS 'Movimentos TPU append-only (aconteceu → evento)';
COMMENT ON TABLE legal_events IS 'Classificação determinística TPU; UNKNOWN se sem regra; sem culpa automática';
