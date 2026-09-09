-- Contas do Brasil — camada fiscal canônica (Tesouro + SICONFI)
-- psql "$DATABASE_URL" -f db/migrations/007_fiscal_contas.sql

CREATE TABLE IF NOT EXISTS public_budget_execution (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  dataset_id TEXT NOT NULL,
  territory_id TEXT NOT NULL,
  government_level TEXT NOT NULL,
  reference_year INT NOT NULL,
  reference_month INT,
  reference_period TEXT NOT NULL,
  revenue_forecast DOUBLE PRECISION,
  revenue_realized DOUBLE PRECISION,
  expense_authorized DOUBLE PRECISION,
  expense_committed DOUBLE PRECISION,
  expense_liquidated DOUBLE PRECISION,
  expense_paid DOUBLE PRECISION,
  restos_a_pagar DOUBLE PRECISION,
  function_code TEXT,
  function_name TEXT,
  subfunction_code TEXT,
  subfunction_name TEXT,
  agency_code TEXT,
  agency_name TEXT,
  budget_unit_code TEXT,
  budget_unit_name TEXT,
  program_code TEXT,
  program_name TEXT,
  action_code TEXT,
  action_name TEXT,
  expense_group_code TEXT,
  expense_group_name TEXT,
  currency TEXT DEFAULT 'BRL',
  amount_scale TEXT DEFAULT 'units',
  published_at TIMESTAMPTZ,
  retrieved_at TIMESTAMPTZ,
  raw_record_id TEXT,
  revised BOOLEAN DEFAULT FALSE,
  methodology TEXT,
  notes TEXT,
  extra JSONB DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pbe_terr_period
  ON public_budget_execution (territory_id, reference_period);
CREATE INDEX IF NOT EXISTS idx_pbe_source_dataset
  ON public_budget_execution (source_id, dataset_id);

CREATE TABLE IF NOT EXISTS fiscal_result_observation (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  dataset_id TEXT NOT NULL,
  territory_id TEXT NOT NULL,
  reference_period TEXT NOT NULL,
  primary_revenue DOUBLE PRECISION,
  primary_expense DOUBLE PRECISION,
  primary_result DOUBLE PRECISION,
  nominal_result DOUBLE PRECISION,
  interest DOUBLE PRECISION,
  methodology TEXT NOT NULL,
  currency TEXT DEFAULT 'BRL',
  amount_scale TEXT DEFAULT 'millions',
  published_at TIMESTAMPTZ,
  retrieved_at TIMESTAMPTZ,
  raw_record_id TEXT,
  revised BOOLEAN DEFAULT FALSE,
  notes TEXT,
  extra JSONB DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fro_natural
  ON fiscal_result_observation (territory_id, reference_period, methodology, dataset_id);
CREATE INDEX IF NOT EXISTS idx_fro_period
  ON fiscal_result_observation (reference_period);

CREATE TABLE IF NOT EXISTS public_debt_observation (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  dataset_id TEXT NOT NULL,
  reference_period TEXT NOT NULL,
  debt_indicator TEXT NOT NULL,
  debt_type TEXT,
  stock DOUBLE PRECISION,
  issuance DOUBLE PRECISION,
  redemption DOUBLE PRECISION,
  amortization DOUBLE PRECISION,
  interest DOUBLE PRECISION,
  average_cost DOUBLE PRECISION,
  average_maturity DOUBLE PRECISION,
  indexer TEXT,
  currency TEXT DEFAULT 'BRL',
  amount_scale TEXT DEFAULT 'units',
  methodology TEXT,
  published_at TIMESTAMPTZ,
  retrieved_at TIMESTAMPTZ,
  raw_record_id TEXT,
  revised BOOLEAN DEFAULT FALSE,
  notes TEXT,
  extra JSONB DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pdo_natural
  ON public_debt_observation (
    reference_period, debt_indicator, COALESCE(debt_type, ''), dataset_id, COALESCE(indexer, '')
  );
CREATE INDEX IF NOT EXISTS idx_pdo_period
  ON public_debt_observation (reference_period);

CREATE TABLE IF NOT EXISTS personnel_expenditure (
  id TEXT PRIMARY KEY,
  territory_id TEXT NOT NULL,
  government_level TEXT NOT NULL,
  agency_id TEXT,
  reference_period TEXT NOT NULL,
  active_personnel DOUBLE PRECISION,
  retired_personnel DOUBLE PRECISION,
  pensions DOUBLE PRECISION,
  gross_amount DOUBLE PRECISION,
  source_id TEXT NOT NULL,
  dataset_id TEXT NOT NULL,
  currency TEXT DEFAULT 'BRL',
  raw_record_id TEXT,
  retrieved_at TIMESTAMPTZ,
  notes TEXT,
  extra JSONB DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pex_natural
  ON personnel_expenditure (
    territory_id, government_level, reference_period, COALESCE(agency_id, ''), dataset_id
  );

-- Extensão leve da quarantine existente (control plane) — razão tipada fiscal
ALTER TABLE quarantine ADD COLUMN IF NOT EXISTS domain TEXT;
CREATE INDEX IF NOT EXISTS idx_quarantine_domain
  ON quarantine (domain);
