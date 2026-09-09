#!/usr/bin/env python3
"""Aplica db/migrations/*.sql em ordem lexicográfica, com tracking.

Uso:
  python -u pipelines/ops/apply_migrations.py
  python -u pipelines/ops/apply_migrations.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG_DIR = ROOT / "db" / "migrations"
DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
)


def list_migration_files() -> list[Path]:
    files = sorted(MIG_DIR.glob("*.sql"))
    return files


def assert_unique_prefixes(files: list[Path]) -> None:
    """Falha se dois ficheiros partilharem o mesmo prefixo NNN_."""
    seen: dict[str, str] = {}
    for f in files:
        m = re.match(r"^(\d{3})_", f.name)
        if not m:
            raise SystemExit(f"migration sem prefixo NNN_: {f.name}")
        prefix = m.group(1)
        if prefix in seen:
            raise SystemExit(
                f"PREFIXO DUPLICADO {prefix}: {seen[prefix]} e {f.name}"
            )
        seen[prefix] = f.name


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = list_migration_files()
    assert_unique_prefixes(files)

    if args.dry_run:
        for f in files:
            print(f"OK order {f.name}")
        return 0

    import psycopg

    conn = psycopg.connect(DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        # bootstrap tracking
        track = MIG_DIR / "000_atlas_schema_migrations.sql"
        if track.exists():
            cur.execute(track.read_text(encoding="utf-8"))

        applied = set()
        try:
            cur.execute("SELECT version FROM atlas_schema_migrations")
            applied = {r[0] for r in cur.fetchall()}
        except Exception:
            applied = set()

        for f in files:
            m = re.match(r"^(\d{3})_", f.name)
            version = m.group(1) if m else f.stem
            if version in applied:
                print(f"SKIP {f.name} (já aplicada)")
                continue
            # Evita reaplicar DDL pesado em bases já inicializadas via schema.sql
            if version in {"001", "002"} and _table_exists(cur, "observations"):
                cur.execute(
                    """
                    INSERT INTO atlas_schema_migrations (version, filename, checksum)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (version) DO NOTHING
                    """,
                    (version, f.name, checksum(f)),
                )
                print(f"SKIP {f.name} (schema já presente — marcado como aplicado)")
                continue
            sql = f.read_text(encoding="utf-8")
            print(f"APPLY {f.name} ...", flush=True)
            cur.execute(sql)
            cur.execute(
                """
                INSERT INTO atlas_schema_migrations (version, filename, checksum)
                VALUES (%s, %s, %s)
                ON CONFLICT (version) DO UPDATE
                  SET filename = EXCLUDED.filename,
                      checksum = EXCLUDED.checksum,
                      applied_at = NOW()
                """,
                (version, f.name, checksum(f)),
            )
            print(f"OK {f.name}")
    conn.close()
    return 0


def _table_exists(cur, name: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name=%s
        """,
        (name,),
    )
    return cur.fetchone() is not None


if __name__ == "__main__":
    raise SystemExit(main())
