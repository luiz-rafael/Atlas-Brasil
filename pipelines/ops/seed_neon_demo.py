#!/usr/bin/env python3
"""Seed mínimo no Neon para demo (sem Docker local). Não imprime secrets."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ops"))
from apply_neon_migrations import load_dotenv, _strip_quotes, ENV_PATH  # noqa: E402


def main() -> int:
    load_dotenv(ENV_PATH)
    url = _strip_quotes(
        os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL") or ""
    )
    if "sslmode" not in url:
        url = url + ("&" if "?" in url else "?") + "sslmode=require"
    import psycopg

    rows = [
        (
            "demo:pessoa:lula",
            "Luiz Inácio Lula da Silva",
            "PT",
            "Presidente da República",
            "BR",
            True,
            ["presidente", "demo"],
        ),
        (
            "demo:pessoa:tarcisio",
            "Tarcísio de Freitas",
            "Republicanos",
            "Governador",
            "SP",
            True,
            ["governador", "demo"],
        ),
        (
            "demo:pessoa:caiado",
            "Ronaldo Caiado",
            "UNIÃO",
            "Governador",
            "GO",
            True,
            ["governador", "demo"],
        ),
    ]
    with psycopg.connect(url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for person_id, nome, partido, cargo, uf, poder, tags in rows:
                cur.execute(
                    """
                    INSERT INTO persons (
                      person_id, nome, partido, cargo_atual, uf,
                      no_poder_2026, tags, mandatos, aliases, source_ids, registros_count
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'[]'::jsonb,'[]'::jsonb,'[]'::jsonb,0)
                    ON CONFLICT (person_id) DO UPDATE SET
                      nome=EXCLUDED.nome,
                      partido=EXCLUDED.partido,
                      cargo_atual=EXCLUDED.cargo_atual,
                      uf=EXCLUDED.uf,
                      no_poder_2026=EXCLUDED.no_poder_2026,
                      tags=EXCLUDED.tags,
                      updated_at=NOW()
                    """,
                    (person_id, nome, partido, cargo, uf, poder, json.dumps(tags)),
                )
                profile = {
                    "id": person_id,
                    "nome": nome,
                    "partido": partido,
                    "cargo_atual": cargo,
                    "uf": uf,
                    "disclaimer": "Registro demo para smoke test. Não representa dossiê completo.",
                }
                cur.execute(
                    """
                    INSERT INTO person_profiles (person_id, profile)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (person_id) DO UPDATE SET
                      profile=EXCLUDED.profile,
                      updated_at=NOW()
                    """,
                    (person_id, json.dumps(profile, ensure_ascii=False)),
                )
            cur.execute("SELECT COUNT(*) FROM persons")
            n = cur.fetchone()[0]
    print(f"Seed demo OK — persons={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
