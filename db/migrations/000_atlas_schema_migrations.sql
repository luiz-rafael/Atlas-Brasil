-- Tracking de migrations Atlas (idempotente).
CREATE TABLE IF NOT EXISTS atlas_schema_migrations (
  version TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  checksum TEXT
);

CREATE INDEX IF NOT EXISTS ix_atlas_schema_migrations_applied
  ON atlas_schema_migrations (applied_at);
