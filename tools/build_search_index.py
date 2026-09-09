#!/usr/bin/env python3
"""Indexa KB em SQLite FTS5 para busca rápida (OpenSearch-lite do MVP)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "atlas-brasil-kb-v2.json"
DB = ROOT / "data" / "atlas-search.sqlite"


def main() -> None:
    kb = json.loads(KB.read_text(encoding="utf-8"))
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        """
        CREATE VIRTUAL TABLE docs USING fts5(
          id, tipo, nome, extra, content='docs_raw', content_rowid='rowid'
        )
        """
    )
    # FTS5 external content is awkward; use simple content table
    conn.execute("DROP TABLE IF EXISTS docs")
    c.execute(
        """
        CREATE VIRTUAL TABLE docs USING fts5(
          id UNINDEXED, tipo UNINDEXED, nome, extra
        )
        """
    )

    rows = []
    for e in kb.get("entidades", []):
        if e.get("isolada"):
            continue
        extra = " ".join(
            filter(
                None,
                [
                    e.get("partido") or "",
                    e.get("cargo_atual") or "",
                    " ".join(e.get("tags") or []),
                    " ".join(e.get("aliases") or []),
                ],
            )
        )
        rows.append((e["id"], e.get("tipo") or "entidade", e.get("nome") or "", extra))
    for caso in kb.get("casos", []):
        rows.append(
            (
                caso["id"],
                "caso",
                caso.get("nome") or "",
                " ".join(caso.get("eixos") or []),
            )
        )
    for d in kb.get("documentos", []):
        rows.append(
            (
                d["id"],
                "documento",
                d.get("titulo") or "",
                " ".join(
                    filter(None, [d.get("orgao") or "", d.get("tipo") or "", d.get("url") or ""])
                ),
            )
        )

    c.executemany("INSERT INTO docs(id, tipo, nome, extra) VALUES (?,?,?,?)", rows)
    conn.commit()
    n = c.execute("SELECT count(*) FROM docs").fetchone()[0]
    conn.close()
    print(f"FTS OK -> {DB} rows={n}")


if __name__ == "__main__":
    main()
