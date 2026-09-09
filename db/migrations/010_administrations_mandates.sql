-- 010 ADMINISTRATION / MANDATE serving (Fase B temporal)
-- Fonte de carga: silver governadores TSE (pipelines/ops/load_administrations.py)

CREATE TABLE IF NOT EXISTS mandates (
  mandate_id TEXT PRIMARY KEY,
  person_id TEXT,
  person_stub TEXT,
  person_name TEXT,
  office TEXT NOT NULL,
  territory_id TEXT,
  state_code TEXT,
  start_date DATE,
  end_date DATE,
  election_year INT,
  party_at_start TEXT,
  source TEXT,
  source_url TEXT,
  evidence_degree TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mandates_territory
  ON mandates (territory_id, start_date);
CREATE INDEX IF NOT EXISTS idx_mandates_person
  ON mandates (person_id);
CREATE INDEX IF NOT EXISTS idx_mandates_state_year
  ON mandates (state_code, election_year);

CREATE TABLE IF NOT EXISTS administrations (
  administration_id TEXT PRIMARY KEY,
  territory_id TEXT NOT NULL,
  state_code TEXT,
  administration_type TEXT NOT NULL DEFAULT 'STATE_ADMINISTRATION',
  executive_person_id TEXT,
  executive_person_name TEXT,
  start_date DATE,
  end_date DATE,
  party_at_start TEXT,
  mandate_id TEXT REFERENCES mandates(mandate_id),
  election_year INT,
  source TEXT,
  source_url TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_administrations_territory
  ON administrations (territory_id, start_date);
CREATE INDEX IF NOT EXISTS idx_administrations_state
  ON administrations (state_code, start_date);
CREATE INDEX IF NOT EXISTS idx_administrations_person
  ON administrations (executive_person_id);

COMMENT ON TABLE administrations IS
  'Contexto de governo por território/intervalo. Não copia indicadores; join temporal.';
COMMENT ON TABLE mandates IS
  'Papel individual (cargo) com intervalo. Fundamento de STATE_ADMINISTRATION estadual.';
