-- CASE_DISCOVERY — por que o processo entrou no Atlas (não scrape nacional)

CREATE TABLE IF NOT EXISTS case_discovery (
  id TEXT PRIMARY KEY,
  case_id TEXT,  -- preenchido após enrich / canonical
  process_number TEXT,
  process_number_normalized TEXT NOT NULL,
  discovered_by_source TEXT NOT NULL,
  discovered_by_entity_id TEXT,
  discovery_type TEXT NOT NULL,
  -- OFFICIAL_REFERENCE | COMPANY_CONTEXT | PERSON_CONTEXT | KNOWN_REFRESH | MANUAL
  discovery_reference TEXT,
  discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ingest_decision TEXT NOT NULL DEFAULT 'PENDING',
  -- PENDING | INGEST | IGNORE | QUARANTINE
  decision_reason TEXT,
  decided_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_case_discovery_npu
  ON case_discovery (process_number_normalized);

CREATE INDEX IF NOT EXISTS ix_case_discovery_entity
  ON case_discovery (discovered_by_entity_id)
  WHERE discovered_by_entity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_case_discovery_pending
  ON case_discovery (ingest_decision)
  WHERE ingest_decision = 'PENDING';

COMMENT ON TABLE case_discovery IS
  'Trilha de descoberta: Atlas não espelha o Judiciário — só processos documentados no escopo';

-- Processos conhecidos → refresh incremental
CREATE TABLE IF NOT EXISTS known_legal_cases (
  process_number_normalized TEXT PRIMARY KEY,
  case_id TEXT,
  court_alias TEXT,
  last_movement_at TIMESTAMPTZ,
  last_checked_at TIMESTAMPTZ,
  last_successful_enrich_at TIMESTAMPTZ,
  check_interval_hours INT DEFAULT 24,
  active BOOLEAN NOT NULL DEFAULT TRUE
);
