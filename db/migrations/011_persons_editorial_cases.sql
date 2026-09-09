-- 011 PERSON serving (materializa KB → Postgres; API deixa de depender de load_kb no path quente)

CREATE TABLE IF NOT EXISTS persons (
  person_id TEXT PRIMARY KEY,
  nome TEXT NOT NULL,
  partido TEXT,
  cargo_atual TEXT,
  uf TEXT,
  foto_url TEXT,
  no_poder_2026 BOOLEAN DEFAULT FALSE,
  tags JSONB DEFAULT '[]'::jsonb,
  mandatos JSONB DEFAULT '[]'::jsonb,
  despesas_resumo JSONB,
  status_badge TEXT,
  registros_count INT DEFAULT 0,
  aliases JSONB DEFAULT '[]'::jsonb,
  source_ids JSONB DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_persons_nome ON persons (nome);
CREATE INDEX IF NOT EXISTS idx_persons_partido ON persons (partido);
CREATE INDEX IF NOT EXISTS idx_persons_poder ON persons (no_poder_2026);
CREATE INDEX IF NOT EXISTS idx_persons_tags ON persons USING GIN (tags);

CREATE TABLE IF NOT EXISTS person_profiles (
  person_id TEXT PRIMARY KEY REFERENCES persons(person_id) ON DELETE CASCADE,
  profile JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE persons IS
  'PERSON list serving — IDs canônicos Atlas; processo/menção ≠ culpa.';
COMMENT ON TABLE person_profiles IS
  'Perfil agregado (slim + rels/regs/casos/grafo ego) para GET /v1/pessoas/{id}.';

-- Casos editoriais (dossiês KB) — distinto de legal_cases DataJud
CREATE TABLE IF NOT EXISTS editorial_cases (
  case_id TEXT PRIMARY KEY,
  nome TEXT NOT NULL,
  periodo TEXT,
  eixos JSONB DEFAULT '[]'::jsonb,
  resumo TEXT,
  payload JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_editorial_cases_nome ON editorial_cases (nome);

COMMENT ON TABLE editorial_cases IS
  'Dossiês editoriais do Atlas (não DataJud). Status jurídico ≠ culpa automática.';
