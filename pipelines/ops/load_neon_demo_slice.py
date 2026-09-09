#!/usr/bin/env python3
"""Carrega no Neon um CORTE REAL para demo pública.

Inclui:
  - territories: BRASIL + REGIÕES + 27 UFs
  - indicators: catálogo completo (leve)
  - observations: só territory_id uf_* (~12k linhas do JSONL)
  - mandates + administrations (governadores)
  - persons + person_profiles: políticos no poder / com cargo (perfil slim)

Uso:
  python -u pipelines/ops/load_neon_demo_slice.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ops"))
sys.path.insert(0, str(ROOT / "api"))

from apply_neon_migrations import load_dotenv, _strip_quotes, ENV_PATH  # noqa: E402

SILVER = ROOT / "data" / "lake" / "silver" / "indicadores"
OBS_JSONL = SILVER / "observations_latest.jsonl"
TERR_JSON = SILVER / "territories_latest.json"
IND_JSON = SILVER / "indicators_latest.json"
WEB_KB = ROOT / "data" / "atlas-brasil-kb-web.json"

PERSON_LIMIT = int(os.getenv("ATLAS_DEMO_PERSON_LIMIT", "400"))


def neon_url() -> str:
    load_dotenv(ENV_PATH)
    url = _strip_quotes(
        os.environ.get("DATABASE_URL_UNPOOLED")
        or os.environ.get("DATABASE_URL")
        or ""
    )
    if not url.startswith("postgresql"):
        raise SystemExit("DATABASE_URL Neon ausente no .env")
    if "sslmode" not in url:
        url = url + ("&" if "?" in url else "?") + "sslmode=require"
    return url


def load_dims(cur) -> tuple[int, int]:
    terrs = json.loads(TERR_JSON.read_text(encoding="utf-8"))
    inds = json.loads(IND_JSON.read_text(encoding="utf-8"))
    keep_types = {"STATE", "REGION", "COUNTRY", "BRASIL", "state", "region", "country"}
    kept = []
    for t in terrs:
        tid = (t.get("territory_id") or "").strip()
        ttype = (t.get("territory_type") or t.get("type") or "").upper()
        if tid.startswith("uf_") or tid in ("br", "brasil", "BR", "BRASIL"):
            kept.append(t)
        elif ttype in {x.upper() for x in keep_types} and not tid.startswith("mun_"):
            kept.append(t)

    cur.execute("TRUNCATE observations, territories, indicators CASCADE")
    n_t = 0
    for t in kept:
        tid = t.get("territory_id")
        if not tid:
            continue
        cur.execute(
            """
            INSERT INTO territories (
              territory_id, ibge_code, name, territory_type, state_code,
              state_name, region_code, region_name, fonte
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (territory_id) DO UPDATE SET
              name=EXCLUDED.name,
              territory_type=EXCLUDED.territory_type,
              state_code=EXCLUDED.state_code,
              updated_at=NOW()
            """,
            (
                tid,
                t.get("ibge_code"),
                t.get("name") or tid,
                t.get("territory_type") or t.get("type"),
                t.get("state_code"),
                t.get("state_name"),
                t.get("region_code"),
                t.get("region_name"),
                t.get("fonte") or t.get("source_id"),
            ),
        )
        n_t += 1

    n_i = 0
    for ind in inds:
        iid = ind.get("indicator_id") or ind.get("id")
        if not iid:
            continue
        cur.execute(
            """
            INSERT INTO indicators (
              indicator_id, name, display_name, description, category,
              subcategory, unit, source_id, dataset_id,
              minimum_geographic_level, methodology_url, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (indicator_id) DO UPDATE SET
              display_name=EXCLUDED.display_name,
              unit=EXCLUDED.unit,
              updated_at=NOW()
            """,
            (
                iid,
                ind.get("name") or iid,
                ind.get("display_name") or ind.get("name") or iid,
                ind.get("description"),
                ind.get("category"),
                ind.get("subcategory"),
                ind.get("unit"),
                ind.get("source_id"),
                ind.get("dataset_id"),
                ind.get("minimum_geographic_level"),
                ind.get("methodology_url"),
                ind.get("notes"),
            ),
        )
        n_i += 1
    return n_t, n_i


def load_uf_observations(cur) -> int:
    if not OBS_JSONL.is_file():
        raise SystemExit(f"missing {OBS_JSONL}")
    batch: list[tuple] = []
    n = 0
    seen_terr: set[str] = set()
    cur.execute("SELECT territory_id FROM territories")
    valid = {r[0] for r in cur.fetchall()}

    def flush() -> None:
        nonlocal batch, n
        if not batch:
            return
        cur.executemany(
            """
            INSERT INTO observations (
              observation_id, indicator_id, territory_id, reference_year,
              value, unit, source_id, geographic_level
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (observation_id) DO UPDATE SET
              value=EXCLUDED.value,
              updated_at=NOW()
            """,
            batch,
        )
        n += len(batch)
        batch = []

    with OBS_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid = o.get("territory_id") or ""
            if not tid.startswith("uf_"):
                continue
            if tid not in valid:
                # ainda assim tenta se uf_ existe no JSONL sem dim
                continue
            oid = o.get("observation_id")
            iid = o.get("indicator_id")
            year = o.get("reference_year")
            if not oid or not iid or year is None:
                continue
            batch.append(
                (
                    oid,
                    iid,
                    tid,
                    int(year),
                    o.get("value"),
                    o.get("unit"),
                    o.get("source_id"),
                    o.get("geographic_level") or "uf",
                )
            )
            seen_terr.add(tid)
            if len(batch) >= 1000:
                flush()
                if n and n % 5000 == 0:
                    print(f"  observations… {n}")
    flush()
    print(f"  ufs_com_obs={len(seen_terr)}")
    return n


def load_admins(cur) -> tuple[int, int]:
    from app.serving_administrations import (
        administration_from_mandate,
        load_mandatos_silver,
        mandate_from_silver,
    )

    rows = load_mandatos_silver()
    mandatos = [mandate_from_silver(r) for r in rows]
    admins = {a["administration_id"]: a for a in (administration_from_mandate(m) for m in mandatos)}
    cur.execute("TRUNCATE administrations, mandates CASCADE")
    for m in mandatos:
        cur.execute(
            """
            INSERT INTO mandates (
              mandate_id, person_id, person_stub, person_name, office,
              territory_id, state_code, start_date, end_date,
              election_year, party_at_start, source, source_url, evidence_degree
            ) VALUES (
              %(mandate_id)s, %(person_id)s, %(person_stub)s, %(person_name)s, %(office)s,
              %(territory_id)s, %(state_code)s, %(start_date)s, %(end_date)s,
              %(election_year)s, %(party_at_start)s, %(source)s, %(source_url)s, %(evidence_degree)s
            )
            ON CONFLICT (mandate_id) DO UPDATE SET person_name=EXCLUDED.person_name, updated_at=NOW()
            """,
            m,
        )
    for a in admins.values():
        cur.execute(
            """
            INSERT INTO administrations (
              administration_id, territory_id, state_code, administration_type,
              executive_person_id, executive_person_name, start_date, end_date,
              party_at_start, mandate_id, election_year, source, source_url
            ) VALUES (
              %(administration_id)s, %(territory_id)s, %(state_code)s, %(administration_type)s,
              %(executive_person_id)s, %(executive_person_name)s, %(start_date)s, %(end_date)s,
              %(party_at_start)s, %(mandate_id)s, %(election_year)s, %(source)s, %(source_url)s
            )
            ON CONFLICT (administration_id) DO UPDATE SET
              executive_person_name=EXCLUDED.executive_person_name, updated_at=NOW()
            """,
            a,
        )
    return len(mandatos), len(admins)


def _pick_persons(ents: list[dict]) -> list[dict]:
    def score(e: dict) -> tuple:
        poder = 1 if e.get("no_poder_2026") else 0
        cargo = (e.get("cargo_atual") or "").lower()
        prio = 0
        for k, w in (
            ("presidente", 100),
            ("governador", 90),
            ("senador", 70),
            ("deputado federal", 60),
            ("deputado", 50),
            ("ministro", 80),
            ("prefeito", 40),
        ):
            if k in cargo:
                prio = max(prio, w)
        return (-poder, -prio, (e.get("nome") or ""))

    ranked = sorted(ents, key=score)
    picked: list[dict] = []
    seen = set()
    for e in ranked:
        if len(picked) >= PERSON_LIMIT:
            break
        pid = e.get("id")
        if not pid or pid in seen:
            continue
        if not (e.get("no_poder_2026") or e.get("cargo_atual") or e.get("partido")):
            continue
        seen.add(pid)
        picked.append(e)
    return picked


def load_persons(cur) -> int:
    from psycopg.types.json import Jsonb
    from app.serving_pessoas import _slim_pessoa, _fontes_of

    if not WEB_KB.is_file():
        print("WARN: KB web ausente — mantém persons existentes")
        return 0
    print(f"Loading KB {WEB_KB.name}…")
    kb = json.loads(WEB_KB.read_text(encoding="utf-8"))
    ents = [
        e
        for e in (kb.get("entidades") or [])
        if e.get("tipo") == "pessoa" and e.get("id") and not e.get("isolada")
    ]
    picked = _pick_persons(ents)
    print(f"persons_pool={len(ents)} picked={len(picked)}")

    cur.execute("TRUNCATE person_profiles, persons CASCADE")
    for e in picked:
        pid = e["id"]
        slim = _slim_pessoa(e)
        profile = {
            "ok": True,
            "pessoa": slim,
            "rels": [],
            "regs": [],
            "casos": {},
            "labels": {pid: slim.get("nome") or pid},
            "fontes": _fontes_of(e),
            "graphNodes": [
                {
                    "id": pid,
                    "nome": slim.get("nome") or pid,
                    "tipo": "pessoa",
                }
            ],
            "graphEdges": [],
            "source": "demo_slice",
            "nota_demo": "Perfil em corte demo (sem grafo completo). Dados oficiais de cargo/partido/UF.",
        }
        cur.execute(
            """
            INSERT INTO persons (
              person_id, nome, partido, cargo_atual, uf, foto_url,
              no_poder_2026, tags, mandatos, despesas_resumo,
              status_badge, registros_count, aliases, source_ids
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            """,
            (
                pid,
                e.get("nome") or pid,
                e.get("partido"),
                e.get("cargo_atual"),
                e.get("uf"),
                e.get("foto_url"),
                bool(e.get("no_poder_2026")),
                Jsonb(e.get("tags") or []),
                Jsonb(e.get("mandatos") or []),
                Jsonb(e.get("despesas_resumo"))
                if e.get("despesas_resumo") is not None
                else None,
                None,
                0,
                Jsonb(e.get("aliases") or []),
                Jsonb(e.get("source_ids") or []),
            ),
        )
        cur.execute(
            """
            INSERT INTO person_profiles (person_id, profile)
            VALUES (%s, %s)
            """,
            (pid, Jsonb(profile)),
        )
    return len(picked)


def main() -> int:
    import psycopg

    for p in (TERR_JSON, IND_JSON, OBS_JSONL):
        if not p.is_file():
            print(f"FAIL missing {p}")
            return 1

    url = neon_url()
    print("Connecting to Neon…")
    with psycopg.connect(url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("1/4 territories + indicators")
            nt, ni = load_dims(cur)
            print(f"   territories={nt} indicators={ni}")

            print("2/4 observations UF (stream JSONL — pode levar alguns minutos)")
            no = load_uf_observations(cur)
            print(f"   observations={no}")

            print("3/4 mandates / administrations")
            try:
                nm, na = load_admins(cur)
                print(f"   mandates={nm} administrations={na}")
            except Exception as e:
                print(f"   WARN admins: {type(e).__name__}: {e}")

            print("4/4 persons (corte político)")
            np_ = load_persons(cur)
            print(f"   persons={np_}")

            cur.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM territories),
                  (SELECT COUNT(*) FROM indicators),
                  (SELECT COUNT(*) FROM observations),
                  (SELECT COUNT(*) FROM persons),
                  (SELECT COUNT(*) FROM administrations)
                """
            )
            print("COUNTS", cur.fetchone())

    print("DONE — corte demo no Neon.")
    print("Reinicie/redeploy a API no Render e teste /v1/indicadores e /v1/pessoas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
