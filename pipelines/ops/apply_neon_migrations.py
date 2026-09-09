#!/usr/bin/env python3
"""Load .env (strip quotes), prefer UNPOOLED URL, apply migrations. Never prints secrets."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    lines_out: list[str] = []
    changed = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.strip().startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k.strip() in ("DATABASE_URL", "DATABASE_URL_UNPOOLED"):
                nv = _strip_quotes(v)
                if nv != v:
                    changed = True
                    line = f"{k}={nv}"
                    v = nv
            os.environ[k.strip()] = _strip_quotes(v)
        lines_out.append(line)
    if changed:
        path.write_text("\n".join(lines_out) + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv(ENV_PATH)
    url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL") or ""
    url = _strip_quotes(url)
    if not url.startswith("postgresql"):
        print("ERROR: DATABASE_URL ausente ou invalida no .env", file=sys.stderr)
        return 1
    if "sslmode" not in url:
        url = url + ("&" if "?" in url else "?") + "sslmode=require"
    os.environ["DATABASE_URL"] = url

    import psycopg

    schema = ROOT / "db" / "schema.sql"
    if schema.is_file():
        print("Ensuring base schema.sql…")
        conn = psycopg.connect(url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(schema.read_text(encoding="utf-8"))
        conn.close()
        print("OK schema.sql")

    print("Applying migrations to Neon…")
    return subprocess.call(
        [sys.executable, "-u", str(ROOT / "pipelines" / "ops" / "apply_migrations.py")],
        cwd=str(ROOT),
    )


if __name__ == "__main__":
    raise SystemExit(main())
