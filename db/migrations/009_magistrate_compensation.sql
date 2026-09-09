-- Remuneração de magistrados (transparência de pessoal). Não é DataJud.
-- Cada competência é um evento financeiro. Não usar SCD2 por pagamento mensal.

CREATE TABLE IF NOT EXISTS magistrates (
  magistrate_id TEXT PRIMARY KEY,
  normalized_name TEXT NOT NULL,
  court_id TEXT NOT NULL,
  position TEXT,
  source_id TEXT NOT NULL DEFAULT 'cnj_magistrate_compensation',
  source_person_identifier TEXT,
  display_name TEXT,
  resolution_method TEXT,
  resolution_confidence TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_magistrates_court_name
  ON magistrates (court_id, normalized_name);

COMMENT ON TABLE magistrates IS
  'MAGISTRATE — chave por órgão + identificador oficial; homônimo entre tribunais não mescla.';

CREATE TABLE IF NOT EXISTS magistrate_compensation (
  id TEXT PRIMARY KEY,
  magistrate_id TEXT NOT NULL REFERENCES magistrates (magistrate_id),
  court_id TEXT NOT NULL,
  reference_year INT,
  reference_month INT,
  reference_period TEXT,
  base_subsidy NUMERIC,
  personal_advantages NUMERIC,
  eventual_advantages NUMERIC,
  indemnities NUMERIC,
  retroactive_payments NUMERIC,
  other_components NUMERIC,
  gross_total NUMERIC,
  discounts NUMERIC,
  net_total NUMERIC,
  source_id TEXT NOT NULL DEFAULT 'cnj_magistrate_compensation',
  dataset_id TEXT,
  raw_record_id TEXT,
  published_at TIMESTAMPTZ,
  retrieved_at TIMESTAMPTZ,
  original_file_url TEXT,
  original_file_source TEXT,
  layout_id TEXT,
  position TEXT,
  notes TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_mag_comp_court_period
  ON magistrate_compensation (court_id, reference_year, reference_month);
CREATE INDEX IF NOT EXISTS ix_mag_comp_magistrate
  ON magistrate_compensation (magistrate_id, reference_year, reference_month);

COMMENT ON TABLE magistrate_compensation IS
  'MAGISTRATE_COMPENSATION — observação por competência. gross_total ≠ subsídio; null ≠ zero.';
COMMENT ON COLUMN magistrate_compensation.base_subsidy IS 'Subsídio / vencimento-base. Não é o bruto.';
COMMENT ON COLUMN magistrate_compensation.gross_total IS 'Total de rendimentos informado pela fonte.';
COMMENT ON COLUMN magistrate_compensation.net_total IS 'Líquido informado pela fonte. Não calcular bruto−descontos automaticamente.';
COMMENT ON COLUMN magistrate_compensation.indemnities IS 'Indenizações quando a fonte as identifica.';
COMMENT ON COLUMN magistrate_compensation.retroactive_payments IS 'Retroativos quando a fonte os identifica.';

CREATE TABLE IF NOT EXISTS compensation_component (
  id TEXT PRIMARY KEY,
  compensation_id TEXT NOT NULL REFERENCES magistrate_compensation (id),
  component_code TEXT,
  component_name TEXT NOT NULL,
  component_category TEXT NOT NULL,
  amount NUMERIC,
  source_id TEXT NOT NULL DEFAULT 'cnj_magistrate_compensation',
  raw_record_id TEXT,
  source_column TEXT
);

CREATE INDEX IF NOT EXISTS ix_comp_component_comp
  ON compensation_component (compensation_id, component_category);

COMMENT ON TABLE compensation_component IS
  'COMPENSATION_COMPONENT — rubricas detalhadas. Preferível a colunas fixas por tribunal.';
