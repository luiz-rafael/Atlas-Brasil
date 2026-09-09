-- COMPANY master (CNPJ) + SCD2-ish status/partners — Receita Federal Fase 1
-- CNPJ é chave determinística. observed_at quando data exata de mudança é desconhecida.

CREATE TABLE IF NOT EXISTS companies (
  company_id TEXT PRIMARY KEY,
  cnpj CHAR(14) NOT NULL UNIQUE,
  cnpj_basico CHAR(8),
  razao_social TEXT,
  nome_fantasia TEXT,
  natureza_juridica TEXT,
  data_abertura DATE,
  capital_social NUMERIC,
  porte TEXT,
  cnae_fiscal TEXT,
  cnae_fiscal_descricao TEXT,
  municipio TEXT,
  uf CHAR(2),
  simples BOOLEAN,
  mei BOOLEAN,
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_companies_cnpj_basico ON companies (cnpj_basico);
CREATE INDEX IF NOT EXISTS ix_companies_uf ON companies (uf);

COMMENT ON TABLE companies IS
  'COMPANY master — chave CNPJ (Receita). Sem fuzzy-match de razão social.';

CREATE TABLE IF NOT EXISTS company_status_history (
  status_id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES companies (company_id),
  cnpj CHAR(14) NOT NULL,
  status TEXT NOT NULL,
  valid_from DATE,
  valid_to DATE,
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  observed_at TIMESTAMPTZ NOT NULL,
  data_situacao_fonte DATE,
  source TEXT,
  retrieved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_company_status_cnpj
  ON company_status_history (cnpj);

CREATE INDEX IF NOT EXISTS ix_company_status_current
  ON company_status_history (cnpj)
  WHERE is_current;

COMMENT ON TABLE company_status_history IS
  'SCD2-ish de situação cadastral. Preferir data_situacao_fonte como valid_from quando a RF informar; senão observed_at.';

CREATE TABLE IF NOT EXISTS company_partners (
  partner_row_id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES companies (company_id),
  cnpj CHAR(14) NOT NULL,
  partner_name TEXT,
  partner_cnpj_cpf TEXT,
  qualification TEXT,
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  observed_at TIMESTAMPTZ NOT NULL,
  valid_from DATE,
  valid_to DATE,
  source TEXT,
  retrieved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_company_partners_cnpj
  ON company_partners (cnpj);

CREATE INDEX IF NOT EXISTS ix_company_partners_current
  ON company_partners (cnpj)
  WHERE is_current;

COMMENT ON TABLE company_partners IS
  'QSA / sócios — snapshots com observed_at; não inventar PERSON só por nome.';
