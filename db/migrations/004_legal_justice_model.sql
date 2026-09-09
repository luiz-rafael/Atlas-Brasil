-- Atlas Justiça / DataJud — modelo completo (complementa 003_legal_cases.sql)
-- Movimentos = append-only (evento). Status = SCD2. Culpa nunca automática.

-- Canonical case (dedupe multi-fonte pelo NPU)
CREATE TABLE IF NOT EXISTS canonical_legal_cases (
  canonical_case_id TEXT PRIMARY KEY,
  process_number TEXT NOT NULL,
  process_number_normalized TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_canonical_npu
  ON canonical_legal_cases (process_number_normalized);

CREATE TABLE IF NOT EXISTS source_case_records (
  source_case_record_id TEXT PRIMARY KEY,
  canonical_case_id TEXT NOT NULL REFERENCES canonical_legal_cases(canonical_case_id),
  source_id TEXT NOT NULL,
  process_number_normalized TEXT NOT NULL,
  court_alias TEXT,
  raw_record_id TEXT,
  retrieved_at TIMESTAMPTZ,
  payload_sha1 TEXT,
  UNIQUE (source_id, process_number_normalized)
);

-- Estende legal_cases se colunas faltarem (idempotente via DO)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='canonical_case_id') THEN
    ALTER TABLE legal_cases ADD COLUMN canonical_case_id TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='process_number_normalized') THEN
    ALTER TABLE legal_cases ADD COLUMN process_number_normalized TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='court_code') THEN
    ALTER TABLE legal_cases ADD COLUMN court_code TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='court_name') THEN
    ALTER TABLE legal_cases ADD COLUMN court_name TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='jurisdiction') THEN
    ALTER TABLE legal_cases ADD COLUMN jurisdiction TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='judging_body_code') THEN
    ALTER TABLE legal_cases ADD COLUMN judging_body_code TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='judging_body_name') THEN
    ALTER TABLE legal_cases ADD COLUMN judging_body_name TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='procedural_class_name') THEN
    ALTER TABLE legal_cases ADD COLUMN procedural_class_name TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='electronic_process') THEN
    ALTER TABLE legal_cases ADD COLUMN electronic_process BOOLEAN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='system_name') THEN
    ALTER TABLE legal_cases ADD COLUMN system_name TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='filing_date') THEN
    ALTER TABLE legal_cases ADD COLUMN filing_date DATE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='last_movement_date') THEN
    ALTER TABLE legal_cases ADD COLUMN last_movement_date TIMESTAMPTZ;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='legal_cases' AND column_name='raw_record_id') THEN
    ALTER TABLE legal_cases ADD COLUMN raw_record_id TEXT;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS procedural_classes (
  class_code TEXT PRIMARY KEY,
  class_name TEXT NOT NULL,
  taxonomy TEXT DEFAULT 'TPU',
  source TEXT DEFAULT 'cnj_tpu'
);

CREATE TABLE IF NOT EXISTS legal_case_subjects (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES legal_cases(case_id) ON DELETE CASCADE,
  subject_code TEXT,
  subject_name TEXT,
  is_primary BOOLEAN DEFAULT FALSE,
  source_id TEXT NOT NULL DEFAULT 'cnj_datajud',
  raw_record_id TEXT
);

CREATE INDEX IF NOT EXISTS ix_legal_case_subjects_case ON legal_case_subjects(case_id);

-- TPU reference
CREATE TABLE IF NOT EXISTS tpu_movements (
  code INT PRIMARY KEY,
  name TEXT NOT NULL,
  parent_code INT,
  category TEXT,
  description TEXT,
  valid_from DATE,
  valid_to DATE
);

CREATE TABLE IF NOT EXISTS tpu_subjects (
  code INT PRIMARY KEY,
  name TEXT NOT NULL,
  parent_code INT,
  category TEXT,
  valid_from DATE,
  valid_to DATE
);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='case_movements' AND column_name='movement_name') THEN
    ALTER TABLE case_movements ADD COLUMN movement_name TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='case_movements' AND column_name='complement') THEN
    ALTER TABLE case_movements ADD COLUMN complement JSONB;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='case_movements' AND column_name='sequence') THEN
    ALTER TABLE case_movements ADD COLUMN sequence INT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='case_movements' AND column_name='movement_timestamp') THEN
    ALTER TABLE case_movements ADD COLUMN movement_timestamp TIMESTAMPTZ;
  END IF;
END $$;

-- Status SCD2
CREATE TABLE IF NOT EXISTS case_status (
  case_status_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES legal_cases(case_id) ON DELETE CASCADE,
  status TEXT NOT NULL, -- EM_ANDAMENTO | ENCERRADO | SUSPENSO | ARQUIVADO | INCERTO
  status_source TEXT NOT NULL, -- SOURCE_EXPLICIT | RULE_DERIVED | MANUAL_REVIEW
  derived_from_movement_id TEXT,
  valid_from TIMESTAMPTZ NOT NULL,
  valid_to TIMESTAMPTZ,
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  confidence TEXT,
  UNIQUE (case_id, valid_from)
);

CREATE INDEX IF NOT EXISTS ix_case_status_current ON case_status(case_id) WHERE is_current;

-- Participação (não HAS_PROCESS genérico)
CREATE TABLE IF NOT EXISTS case_participation (
  participation_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES legal_cases(case_id) ON DELETE CASCADE,
  entity_id TEXT,
  entity_type TEXT, -- PERSON | COMPANY | UNKNOWN
  role TEXT NOT NULL, -- PLAINTIFF | DEFENDANT | ... | UNKNOWN
  atlas_relation TEXT, -- MENTIONED_IN | ... | NULL até evidência
  role_source TEXT,
  source_id TEXT NOT NULL,
  evidence_id TEXT,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  confidence TEXT NOT NULL DEFAULT 'low',
  notes TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  dataset_id TEXT,
  raw_record_id TEXT,
  case_id TEXT,
  movement_id TEXT,
  entity_id TEXT,
  relation_id TEXT,
  evidence_type TEXT,
  retrieved_at TIMESTAMPTZ,
  source_record_timestamp TIMESTAMPTZ,
  confidence TEXT
);

CREATE TABLE IF NOT EXISTS legal_quarantine (
  quarantine_id TEXT PRIMARY KEY,
  reason TEXT NOT NULL, -- AMBIGUOUS_PERSON | INVALID_PROCESS_NUMBER | ...
  source_id TEXT,
  raw_record_id TEXT,
  payload JSONB,
  status TEXT NOT NULL DEFAULT 'OPEN', -- OPEN | RESOLVED | IGNORED
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS datajud_source_state (
  tribunal TEXT PRIMARY KEY,
  last_checked_at TIMESTAMPTZ,
  last_successful_at TIMESTAMPTZ,
  last_cursor TEXT,
  last_page INT,
  last_process_timestamp TIMESTAMPTZ,
  requests_today INT DEFAULT 0,
  rate_limit_state TEXT,
  health_status TEXT,
  terms_version TEXT,
  terms_checked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS source_terms_snapshots (
  source_id TEXT NOT NULL,
  terms_version TEXT NOT NULL,
  terms_url TEXT,
  usage_policy TEXT,
  redistribution_policy TEXT,
  cross_reference_policy TEXT,
  checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (source_id, terms_version)
);

COMMENT ON TABLE case_status IS 'Estado processual SCD2 — distinto de CASE_MOVEMENT (append-only)';
COMMENT ON TABLE case_participation IS 'Papel processual documentado; atlas_relation acusatório só com evidência';
COMMENT ON TABLE legal_quarantine IS 'Nunca descartar silenciosamente registros problemáticos';
