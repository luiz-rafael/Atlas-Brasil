-- Fase A control plane (aplicar em bases já existentes)
-- psql "$DATABASE_URL" -f db/migrations/001_control_plane.sql

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
