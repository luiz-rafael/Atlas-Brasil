-- Receita Federal complementar (renúncias, carga, contencioso, transação, CNO)
-- NÃO altera companies / company_status_history / company_partners.

CREATE TABLE IF NOT EXISTS tax_expenditure (
  tax_expenditure_id TEXT PRIMARY KEY,
  year INT NOT NULL,
  tributo TEXT,
  beneficio TEXT,
  regime TEXT,
  setor TEXT,
  cnae TEXT,
  valor NUMERIC,
  value_type TEXT NOT NULL DEFAULT 'ESTIMATED'
    CHECK (value_type IN ('OBSERVED', 'ESTIMATED', 'PROJECTED')),
  methodology TEXT,
  cnpj CHAR(14),
  cnpj_raiz CHAR(8),
  company_id TEXT,
  razao_social TEXT,
  territory_id TEXT DEFAULT 'terr_br',
  source_id TEXT NOT NULL DEFAULT 'receita_renuncias',
  dataset_id TEXT,
  source_file TEXT,
  retrieved_at TIMESTAMPTZ,
  meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_tax_expenditure_year ON tax_expenditure (year);
CREATE INDEX IF NOT EXISTS ix_tax_expenditure_cnpj ON tax_expenditure (cnpj)
  WHERE cnpj IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_tax_expenditure_company ON tax_expenditure (company_id)
  WHERE company_id IS NOT NULL;

COMMENT ON TABLE tax_expenditure IS
  'TAX_EXPENDITURE — renúncia/benefício fiscal. Renúncia ≠ pagamento. company_id só com CNPJ 14.';

CREATE TABLE IF NOT EXISTS tax_burden_observation (
  tax_burden_id TEXT PRIMARY KEY,
  year INT NOT NULL,
  tax_to_gdp_ratio NUMERIC,
  amount NUMERIC,
  amount_unit TEXT DEFAULT 'BRL',
  pib_bilhoes NUMERIC,
  arrecadacao_bruta_bilhoes NUMERIC,
  methodology TEXT,
  methodology_notes JSONB DEFAULT '{}'::jsonb,
  territory_id TEXT DEFAULT 'terr_br',
  territory_type TEXT DEFAULT 'BRASIL',
  source_id TEXT NOT NULL DEFAULT 'receita_carga_tributaria',
  dataset_id TEXT,
  source_file TEXT,
  retrieved_at TIMESTAMPTZ,
  meta JSONB DEFAULT '{}'::jsonb,
  UNIQUE (year, territory_id, source_id)
);

CREATE INDEX IF NOT EXISTS ix_tax_burden_year ON tax_burden_observation (year);

COMMENT ON TABLE tax_burden_observation IS
  'Carga tributária % PIB (CTB/RFB). Separado de ind_arrecadacao_federal.';

CREATE TABLE IF NOT EXISTS admin_tax_contencioso_observation (
  contencioso_obs_id TEXT PRIMARY KEY,
  year INT,
  admin_case_id TEXT,
  entity_type TEXT NOT NULL DEFAULT 'ADMINISTRATIVE_TAX_CASE',
  quantidade NUMERIC,
  valor NUMERIC,
  tempo_medio NUMERIC,
  territory_id TEXT DEFAULT 'terr_br',
  source_id TEXT NOT NULL DEFAULT 'receita_contencioso',
  dataset_id TEXT,
  source_file TEXT,
  retrieved_at TIMESTAMPTZ,
  raw JSONB DEFAULT '{}'::jsonb,
  meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_admin_contencioso_year
  ON admin_tax_contencioso_observation (year);
CREATE INDEX IF NOT EXISTS ix_admin_contencioso_case
  ON admin_tax_contencioso_observation (admin_case_id);

COMMENT ON TABLE admin_tax_contencioso_observation IS
  'Contencioso administrativo tributário — NUNCA mesclar com LEGAL_CASE/DataJud.';

CREATE TABLE IF NOT EXISTS tax_transaction_event (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL DEFAULT 'ADMINISTRATIVE_TAX_SETTLEMENT',
  edital TEXT,
  cnpj CHAR(14),
  company_id TEXT,
  valor NUMERIC,
  event_date DATE,
  source_id TEXT NOT NULL DEFAULT 'receita_transacao_tributaria',
  dataset_id TEXT,
  source_file TEXT,
  retrieved_at TIMESTAMPTZ,
  raw JSONB DEFAULT '{}'::jsonb,
  meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_tax_tx_cnpj ON tax_transaction_event (cnpj)
  WHERE cnpj IS NOT NULL;

COMMENT ON TABLE tax_transaction_event IS
  'Transação tributária / acordo administrativo — não é LEGAL_CASE judicial.';

CREATE TABLE IF NOT EXISTS cno_works (
  cno_work_id TEXT PRIMARY KEY,
  cno_id TEXT,
  cnpj CHAR(14),
  company_id TEXT,
  municipality TEXT,
  uf CHAR(2),
  source_id TEXT NOT NULL DEFAULT 'receita_cno',
  dataset_id TEXT,
  source_file TEXT,
  retrieved_at TIMESTAMPTZ,
  raw JSONB DEFAULT '{}'::jsonb,
  meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_cno_works_cnpj ON cno_works (cnpj)
  WHERE cnpj IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_cno_works_company ON cno_works (company_id)
  WHERE company_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_cno_works_cno_id ON cno_works (cno_id);

COMMENT ON TABLE cno_works IS
  'Cadastro Nacional de Obras — company_id apenas com CNPJ 14 válido.';
