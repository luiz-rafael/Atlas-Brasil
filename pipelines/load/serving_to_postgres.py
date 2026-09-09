#!/usr/bin/env python3
"""Fase C: Iceberg/gold → Postgres serving (indicadores + documentos)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.lakehouse.config import LAKE  # noqa: E402

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil",
)
SILVER_IND = LAKE / "silver" / "indicadores"
BATCH = int(os.getenv("ATLAS_SERVING_BATCH", "5000") or "5000")


def _connect():
    try:
        import psycopg
    except ImportError:
        print("psycopg não instalado — skip serving load", file=sys.stderr)
        return None
    try:
        return psycopg.connect(DSN)
    except Exception as e:
        print(f"Postgres indisponível ({e}) — skip serving load", file=sys.stderr)
        return None


def _load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _copy_rows(cur, table: str, columns: list[str], rows: list[tuple]) -> int:
    if not rows:
        return 0
    from io import StringIO

    buf = StringIO()
    for row in rows:
        parts = []
        for v in row:
            if v is None:
                parts.append("\\N")
            else:
                s = str(v).replace("\\", "\\\\").replace("\t", " ").replace("\n", " ").replace("\r", " ")
                parts.append(s)
        buf.write("\t".join(parts) + "\n")
    buf.seek(0)
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        copy.write(buf.read())
    return len(rows)


def _load_observations_iceberg():
    from pipelines.lakehouse.io import read_table

    df = read_table("silver", "indicadores_observations")
    cols = [
        "observation_id",
        "indicator_id",
        "territory_id",
        "reference_year",
        "value",
        "unit",
        "source_id",
        "geographic_level",
    ]
    for c in cols:
        if c not in df.columns:
            raise RuntimeError(f"coluna ausente em Iceberg silver.indicadores_observations: {c}")
    return df.select(cols)


def _load_gold_uf():
    from pipelines.lakehouse.io import read_table, table_exists

    if not table_exists("gold", "indicadores_uf_latest"):
        return None
    return read_table("gold", "indicadores_uf_latest")


def _load_docs_iceberg():
    from pipelines.lakehouse.io import read_table, table_exists

    # silver tem mais colunas (orgao, nivel_fonte); gold é curado com URL
    if table_exists("silver", "documentos"):
        return read_table("silver", "documentos")
    if table_exists("gold", "documentos_curados"):
        return read_table("gold", "documentos_curados")
    return None


def main() -> int:
    conn = _connect()
    if conn is None:
        return 0

    territories = _load_json_list(SILVER_IND / "territories_latest.json")
    indicators = _load_json_list(SILVER_IND / "indicators_latest.json")
    if not territories or not indicators:
        print("dimensões silver ausentes (territories/indicators)", file=sys.stderr)
        return 1

    try:
        obs_df = _load_observations_iceberg()
        # Iceberg/JSONL pode repetir observation_id entre merges
        obs_df = obs_df.unique(subset=["observation_id"], keep="last")
    except Exception as e:
        print(f"falha lendo Iceberg observations: {e}", file=sys.stderr)
        return 1

    gold_uf = None
    try:
        gold_uf = _load_gold_uf()
    except Exception as e:
        print(f"aviso gold uf_latest: {e}", file=sys.stderr)

    docs_df = None
    try:
        docs_df = _load_docs_iceberg()
    except Exception as e:
        print(f"aviso documentos Iceberg: {e}", file=sys.stderr)

    counts: dict[str, int] = {}
    with conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE observations, gold_indicadores_uf_latest")
            cur.execute("TRUNCATE territories, indicators")

            t_rows = [
                (
                    t.get("territory_id"),
                    t.get("ibge_code"),
                    t.get("name"),
                    t.get("territory_type"),
                    t.get("state_code"),
                    t.get("state_name"),
                    t.get("region_code"),
                    t.get("region_name"),
                    t.get("fonte"),
                )
                for t in territories
                if t.get("territory_id")
            ]
            counts["territories"] = _copy_rows(
                cur,
                "territories",
                [
                    "territory_id",
                    "ibge_code",
                    "name",
                    "territory_type",
                    "state_code",
                    "state_name",
                    "region_code",
                    "region_name",
                    "fonte",
                ],
                t_rows,
            )

            i_rows = [
                (
                    i.get("indicator_id"),
                    i.get("name"),
                    i.get("display_name"),
                    i.get("description"),
                    i.get("category"),
                    i.get("subcategory"),
                    i.get("unit"),
                    i.get("source_id"),
                    i.get("dataset_id"),
                    i.get("minimum_geographic_level"),
                    i.get("methodology_url"),
                    i.get("notes"),
                )
                for i in indicators
                if i.get("indicator_id")
            ]
            counts["indicators"] = _copy_rows(
                cur,
                "indicators",
                [
                    "indicator_id",
                    "name",
                    "display_name",
                    "description",
                    "category",
                    "subcategory",
                    "unit",
                    "source_id",
                    "dataset_id",
                    "minimum_geographic_level",
                    "methodology_url",
                    "notes",
                ],
                i_rows,
            )

            # observations em lotes via COPY
            n_obs = 0
            batch: list[tuple] = []
            for row in obs_df.iter_rows(named=True):
                batch.append(
                    (
                        row["observation_id"],
                        row["indicator_id"],
                        row["territory_id"],
                        int(row["reference_year"]) if row["reference_year"] is not None else None,
                        float(row["value"]) if row["value"] is not None else None,
                        row.get("unit"),
                        row.get("source_id"),
                        row.get("geographic_level"),
                    )
                )
                if len(batch) >= BATCH:
                    n_obs += _copy_rows(
                        cur,
                        "observations",
                        [
                            "observation_id",
                            "indicator_id",
                            "territory_id",
                            "reference_year",
                            "value",
                            "unit",
                            "source_id",
                            "geographic_level",
                        ],
                        batch,
                    )
                    batch = []
            if batch:
                n_obs += _copy_rows(
                    cur,
                    "observations",
                    [
                        "observation_id",
                        "indicator_id",
                        "territory_id",
                        "reference_year",
                        "value",
                        "unit",
                        "source_id",
                        "geographic_level",
                    ],
                    batch,
                )
            counts["observations"] = n_obs

            if gold_uf is not None and gold_uf.height > 0:
                g_rows = [
                    (
                        r["territory_id"],
                        r["indicator_id"],
                        int(r["reference_year"]) if r["reference_year"] is not None else None,
                        float(r["value"]) if r["value"] is not None else None,
                        r.get("unit"),
                        r.get("source_id"),
                    )
                    for r in gold_uf.iter_rows(named=True)
                ]
                counts["gold_indicadores_uf_latest"] = _copy_rows(
                    cur,
                    "gold_indicadores_uf_latest",
                    [
                        "territory_id",
                        "indicator_id",
                        "reference_year",
                        "value",
                        "unit",
                        "source_id",
                    ],
                    g_rows,
                )

            if docs_df is not None and docs_df.height > 0:
                # upsert documentos (não truncate KB docs existentes)
                n_docs = 0
                for r in docs_df.iter_rows(named=True):
                    doc_id = r.get("id")
                    if not doc_id:
                        continue
                    titulo = r.get("titulo") or doc_id
                    cur.execute(
                        """
                        INSERT INTO documentos (
                          id, titulo, url, nivel_fonte, orgao, fonte, source_system,
                          is_primary, titulo_len, data
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (id) DO UPDATE SET
                          titulo=EXCLUDED.titulo,
                          url=COALESCE(EXCLUDED.url, documentos.url),
                          nivel_fonte=COALESCE(EXCLUDED.nivel_fonte, documentos.nivel_fonte),
                          orgao=COALESCE(EXCLUDED.orgao, documentos.orgao),
                          fonte=EXCLUDED.fonte,
                          source_system=EXCLUDED.source_system,
                          is_primary=EXCLUDED.is_primary,
                          titulo_len=EXCLUDED.titulo_len
                        """,
                        (
                            doc_id,
                            titulo,
                            r.get("url"),
                            r.get("nivel_fonte"),
                            r.get("orgao"),
                            r.get("fonte"),
                            r.get("source_system"),
                            bool(r["is_primary"]) if r.get("is_primary") is not None else None,
                            int(r["titulo_len"]) if r.get("titulo_len") is not None else None,
                            r.get("collected_at") or r.get("data"),
                        ),
                    )
                    n_docs += 1
                counts["documentos_upsert"] = n_docs

            cur.execute(
                """
                INSERT INTO meta_sistema (chave, valor, updated_at)
                VALUES ('serving_indicadores', %s::jsonb, NOW())
                ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor, updated_at=NOW()
                """,
                (json.dumps(counts),),
            )

    print(json.dumps({"ok": True, "dsn_host": DSN.split("@")[-1], "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
