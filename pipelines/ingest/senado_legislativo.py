#!/usr/bin/env python3
"""Senado — autorias e votações nominais por senador (p_sen_).
Anos: LEG_ANOS ou escopo Atlas (default 2010–hoje).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    bronze_dir,
    http_get,
    utc_now,
    write_json,
    write_jsonl,
    write_manifest,
    write_raw_record,
)
from pipelines.config.escopo import anos_periodo  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

BASE = "https://legis.senado.leg.br/dadosabertos"
GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"


def anos() -> set[int]:
    raw = os.getenv("LEG_ANOS", "").strip()
    if raw:
        return {int(x) for x in raw.split(",") if x.strip().isdigit()}
    return set(anos_periodo())


def active_senadores() -> list[dict]:
    if not GOLD.exists():
        return []
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    out = []
    for e in kb.get("entidades") or []:
        eid = str(e.get("id") or "")
        if eid.startswith("p_sen_"):
            out.append({"id": eid, "code": eid.replace("p_sen_", "", 1), "nome": e.get("nome")})
    return out


def _as_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def year_of(s: str | None) -> int | None:
    if not s:
        return None
    s = str(s)
    for part in (s[:4],):
        if part.isdigit() and 1990 <= int(part) <= 2100:
            return int(part)
    return None


def main() -> int:
    run = start_run("senado_legislativo", "senado.legislativo")
    out = bronze_dir("senado_legislativo")
    years = anos()
    sens = active_senadores()
    limit = int(os.getenv("SENADO_LEG_LIMIT", "0") or "0")
    if limit > 0:
        sens = sens[:limit]
    print(f"Senado legislativo: {len(sens)} senadores · anos={sorted(years)}")

    autorias: list[dict] = []
    votos: list[dict] = []
    materias: dict[str, dict] = {}

    for i, sen in enumerate(sens, 1):
        code = sen["code"]
        pid = sen["id"]
        for endpoint, kind in (("autorias", "autorias"), ("votacoes", "votacoes")):
            url = f"{BASE}/senador/{code}/{endpoint}.json"
            try:
                r = http_get(url, timeout=90.0)
            except Exception as e:
                print(f"  fail {code} {endpoint}: {e}", file=sys.stderr)
                continue
            if r.status_code != 200:
                continue
            write_raw_record(
                source_id="senado_legislativo",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=r.content,
                filename=f"{code}_{endpoint}.json",
                source_url=url,
                dataset_id=f"senado.{kind}",
                content_type="application/json",
            )
            data = r.json()
            if endpoint == "autorias":
                root = data.get("MateriasAutoriaParlamentar") or {}
                parl = root.get("Parlamentar") or {}
                auts = _as_list(((parl.get("Autorias") or {}).get("Autoria")))
                for a in auts:
                    mat = a.get("Materia") or {}
                    mid = str(mat.get("Codigo") or mat.get("CodigoMateria") or "")
                    ano_m = year_of(mat.get("Ano")) or year_of(
                        mat.get("DataApresentacao") or mat.get("Data")
                    )
                    if ano_m and ano_m not in years:
                        continue
                    if mid:
                        materias[mid] = {
                            "id_materia": mid,
                            "sigla": mat.get("Sigla") or mat.get("SiglaSubtipoMateria"),
                            "numero": mat.get("Numero"),
                            "ano": ano_m or mat.get("Ano"),
                            "ementa": (mat.get("Ementa") or "")[:500],
                            "casa": "senado",
                            "uri": mat.get("UrlTexto") or mat.get("UrlTramitacao"),
                        }
                    autorias.append(
                        {
                            "person_id": pid,
                            "senador_codigo": code,
                            "id_materia": mid,
                            "autor_principal": a.get("IndicadorAutorPrincipal"),
                            "ano": ano_m,
                            "casa": "senado",
                        }
                    )
            else:
                root = data.get("VotacaoParlamentar") or {}
                parl = root.get("Parlamentar") or {}
                vots = _as_list(((parl.get("Votacoes") or {}).get("Votacao")))
                for v in vots:
                    sess = v.get("SessaoPlenaria") or {}
                    data_sess = sess.get("DataSessao") or sess.get("Data") or ""
                    ano_v = year_of(data_sess)
                    if ano_v and ano_v not in years:
                        continue
                    mat = v.get("Materia") or {}
                    mid = str(mat.get("Codigo") or mat.get("CodigoMateria") or "")
                    voto = v.get("SiglaDescricaoVoto") or v.get("DescricaoVoto")
                    votos.append(
                        {
                            "person_id": pid,
                            "senador_codigo": code,
                            "id_votacao": str(
                                v.get("CodigoSessaoVotacao") or v.get("Sequencial") or ""
                            ),
                            "id_materia": mid,
                            "voto": voto,
                            "data": data_sess,
                            "descricao": (v.get("DescricaoVotacao") or "")[:300],
                            "resultado": v.get("DescricaoResultado"),
                            "casa": "senado",
                            "ano": ano_v,
                        }
                    )
            time.sleep(0.05)
        if i % 10 == 0:
            print(f"  {i}/{len(sens)} (autorias={len(autorias)} votos={len(votos)})", flush=True)

    write_jsonl(out / "autorias.jsonl", autorias)
    write_jsonl(out / "votos.jsonl", votos)
    write_jsonl(out / "materias.jsonl", list(materias.values()))
    write_json(
        out / "resumo.json",
        {
            "fetched_at": utc_now(),
            "anos": sorted(years),
            "senadores": len(sens),
            "autorias": len(autorias),
            "votos": len(votos),
            "materias": len(materias),
        },
    )
    write_manifest(
        out,
        "senado_legislativo",
        [
            {"file": "autorias.jsonl", "count": len(autorias)},
            {"file": "votos.jsonl", "count": len(votos)},
            {"file": "materias.jsonl", "count": len(materias)},
        ],
        extra={"ingestion_run_id": run["ingestion_run_id"]},
    )
    mark_ingested(
        "senado_legislativo",
        run_id=run["ingestion_run_id"],
        counts={"autorias": len(autorias), "votos": len(votos)},
        ok=True,
    )
    print(f"OK Senado legislativo: autorias={len(autorias)} votos={len(votos)} materias={len(materias)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
