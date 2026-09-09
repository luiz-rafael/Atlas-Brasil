#!/usr/bin/env python3
"""
Câmara — proposições, autores, votações e votos nominais (arquivos anuais oficiais).
Anos: LEG_ANOS (default 2022..ano corrente).
Filtra autores/votos para deputados p_cam_ na gold (ativos).
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    bronze_dir,
    http_get,
    sha1_bytes,
    utc_now,
    write_json,
    write_jsonl,
    write_manifest,
    write_raw_record,
)
from pipelines.config.escopo import anos_periodo  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

BASE = "https://dadosabertos.camara.leg.br/arquivos"
GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"


def anos() -> list[int]:
    raw = os.getenv("LEG_ANOS", "").strip()
    if raw:
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]
    return anos_periodo()


def active_deputado_ids() -> set[str]:
    ids: set[str] = set()
    if not GOLD.exists():
        return ids
    kb = json.loads(GOLD.read_text(encoding="utf-8"))
    for e in kb.get("entidades") or []:
        eid = str(e.get("id") or "")
        if eid.startswith("p_cam_"):
            ids.add(eid.replace("p_cam_", "", 1))
    return ids


def download_csv(kind: str, ano: int) -> bytes | None:
    url = f"{BASE}/{kind}/csv/{kind}-{ano}.csv"
    r = http_get(url, timeout=300.0)
    if r.status_code != 200:
        print(f"  fail {kind}-{ano} HTTP {r.status_code}", file=sys.stderr)
        return None
    return r.content


def iter_csv_rows(raw: bytes):
    text = raw.decode("utf-8-sig", errors="replace")
    # alguns arquivos começam com linha de título
    if text.startswith("Lista") or text.startswith("\ufeffLista"):
        text = "\n".join(text.splitlines()[1:])
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for row in reader:
        yield {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}


def main() -> int:
    run = start_run("camara_legislativo", "camara.legislativo")
    out = bronze_dir("camara_legislativo")
    dep_ids = active_deputado_ids()
    print(f"Câmara legislativo: anos={anos()} deputados_alvo={len(dep_ids)}")

    autores_rows: list[dict] = []
    props_keep_ids: set[str] = set()
    votos_rows: list[dict] = []
    votacoes_meta: dict[str, dict] = {}
    props_meta: dict[str, dict] = {}
    voto_prop: dict[str, dict] = {}  # idVotacao -> proposicao

    files_meta = []
    for ano in anos():
        print(f"  ano {ano}…", flush=True)
        # autores → quais proposições importam
        raw_aut = download_csv("proposicoesAutores", ano)
        if raw_aut:
            write_raw_record(
                source_id="camara_legislativo",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=raw_aut,
                filename=f"proposicoesAutores-{ano}.csv",
                source_url=f"{BASE}/proposicoesAutores/csv/proposicoesAutores-{ano}.csv",
                dataset_id="camara.proposicoes_autores",
                content_type="text/csv",
            )
            files_meta.append(
                {"file": f"proposicoesAutores-{ano}.csv", "bytes": len(raw_aut), "sha1": sha1_bytes(raw_aut)}
            )
            for row in iter_csv_rows(raw_aut):
                did = str(row.get("idDeputadoAutor") or "").strip()
                if not did or did not in dep_ids:
                    continue
                pid = str(row.get("idProposicao") or "").strip()
                if not pid:
                    continue
                props_keep_ids.add(pid)
                autores_rows.append(
                    {
                        "ano_arquivo": ano,
                        "id_proposicao": pid,
                        "deputado_id": did,
                        "person_id": f"p_cam_{did}",
                        "nome_autor": row.get("nomeAutor"),
                        "partido": row.get("siglaPartidoAutor"),
                        "uf": row.get("siglaUFAutor"),
                        "ordem": row.get("ordemAssinatura"),
                        "proponente": row.get("proponente"),
                        "tipo_autor": row.get("tipoAutor"),
                    }
                )

        # vínculo votação → proposição (antes dos votos)
        raw_vp = download_csv("votacoesProposicoes", ano)
        if raw_vp:
            write_raw_record(
                source_id="camara_legislativo",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=raw_vp,
                filename=f"votacoesProposicoes-{ano}.csv",
                source_url=f"{BASE}/votacoesProposicoes/csv/votacoesProposicoes-{ano}.csv",
                dataset_id="camara.votacoes_proposicoes",
                content_type="text/csv",
            )
            files_meta.append(
                {
                    "file": f"votacoesProposicoes-{ano}.csv",
                    "bytes": len(raw_vp),
                    "sha1": sha1_bytes(raw_vp),
                }
            )
            for row in iter_csv_rows(raw_vp):
                vid = str(row.get("idVotacao") or "").strip()
                prop_id = str(row.get("proposicao_id") or "").strip()
                if not vid:
                    continue
                if prop_id:
                    props_keep_ids.add(prop_id)
                voto_prop[vid] = {
                    "id_proposicao": prop_id,
                    "proposicao_titulo": row.get("proposicao_titulo"),
                    "proposicao_ementa": (row.get("proposicao_ementa") or "")[:400],
                    "proposicao_sigla": row.get("proposicao_siglaTipo"),
                    "proposicao_numero": row.get("proposicao_numero"),
                    "proposicao_ano": row.get("proposicao_ano"),
                    "votacao_descricao": (row.get("descricao") or "")[:300],
                    "votacao_data": row.get("data"),
                }

        raw_prop = download_csv("proposicoes", ano)
        if raw_prop:
            write_raw_record(
                source_id="camara_legislativo",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=raw_prop,
                filename=f"proposicoes-{ano}.csv",
                source_url=f"{BASE}/proposicoes/csv/proposicoes-{ano}.csv",
                dataset_id="camara.proposicoes",
                content_type="text/csv",
            )
            files_meta.append(
                {"file": f"proposicoes-{ano}.csv", "bytes": len(raw_prop), "sha1": sha1_bytes(raw_prop)}
            )
            for row in iter_csv_rows(raw_prop):
                pid = str(row.get("id") or "").strip()
                if pid not in props_keep_ids:
                    continue
                props_meta[pid] = {
                    "id_proposicao": pid,
                    "sigla_tipo": row.get("siglaTipo"),
                    "numero": row.get("numero"),
                    "ano": row.get("ano") or ano,
                    "descricao_tipo": row.get("descricaoTipo"),
                    "ementa": (row.get("ementa") or "")[:500],
                    "data_apresentacao": row.get("dataApresentacao"),
                    "uri": row.get("uri"),
                    "keywords": row.get("keywords"),
                    "casa": "camara",
                }

        raw_vot = download_csv("votacoes", ano)
        if raw_vot:
            write_raw_record(
                source_id="camara_legislativo",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=raw_vot,
                filename=f"votacoes-{ano}.csv",
                source_url=f"{BASE}/votacoes/csv/votacoes-{ano}.csv",
                dataset_id="camara.votacoes",
                content_type="text/csv",
            )
            files_meta.append(
                {"file": f"votacoes-{ano}.csv", "bytes": len(raw_vot), "sha1": sha1_bytes(raw_vot)}
            )
            for row in iter_csv_rows(raw_vot):
                vid = str(row.get("id") or "").strip()
                if not vid:
                    continue
                votacoes_meta[vid] = {
                    "id_votacao": vid,
                    "data": row.get("data"),
                    "orgao": row.get("siglaOrgao"),
                    "aprovacao": row.get("aprovacao"),
                    "descricao": (row.get("descricao") or row.get("proposta") or "")[:300],
                    "uri": row.get("uri"),
                    "ano_arquivo": ano,
                    "casa": "camara",
                }

        raw_vv = download_csv("votacoesVotos", ano)
        if raw_vv:
            write_raw_record(
                source_id="camara_legislativo",
                ingestion_run_id=run["ingestion_run_id"],
                connector_version=run["connector_version"],
                payload=raw_vv,
                filename=f"votacoesVotos-{ano}.csv",
                source_url=f"{BASE}/votacoesVotos/csv/votacoesVotos-{ano}.csv",
                dataset_id="camara.votacoes_votos",
                content_type="text/csv",
            )
            files_meta.append(
                {"file": f"votacoesVotos-{ano}.csv", "bytes": len(raw_vv), "sha1": sha1_bytes(raw_vv)}
            )
            for row in iter_csv_rows(raw_vv):
                did = str(row.get("deputado_id") or "").strip()
                if not did or did not in dep_ids:
                    continue
                votos_rows.append(
                    {
                        "ano_arquivo": ano,
                        "id_votacao": row.get("idVotacao"),
                        "deputado_id": did,
                        "person_id": f"p_cam_{did}",
                        "voto": row.get("voto"),
                        "data_hora": row.get("dataHoraVoto"),
                        "partido": row.get("deputado_siglaPartido"),
                        "uf": row.get("deputado_siglaUf"),
                        "casa": "camara",
                        **(
                            {
                                "id_proposicao": (voto_prop.get(str(row.get("idVotacao") or "")) or {}).get(
                                    "id_proposicao"
                                ),
                                "proposicao_titulo": (
                                    voto_prop.get(str(row.get("idVotacao") or "")) or {}
                                ).get("proposicao_titulo"),
                                "proposicao_sigla": (
                                    voto_prop.get(str(row.get("idVotacao") or "")) or {}
                                ).get("proposicao_sigla"),
                                "proposicao_numero": (
                                    voto_prop.get(str(row.get("idVotacao") or "")) or {}
                                ).get("proposicao_numero"),
                                "proposicao_ano": (
                                    voto_prop.get(str(row.get("idVotacao") or "")) or {}
                                ).get("proposicao_ano"),
                                "proposicao_ementa": (
                                    voto_prop.get(str(row.get("idVotacao") or "")) or {}
                                ).get("proposicao_ementa"),
                            }
                        ),
                    }
                )

    write_jsonl(out / "proposicoes_autores.jsonl", autores_rows)
    write_jsonl(out / "proposicoes.jsonl", list(props_meta.values()))
    write_jsonl(out / "votacoes.jsonl", list(votacoes_meta.values()))
    write_jsonl(out / "votos.jsonl", votos_rows)
    write_jsonl(out / "votacao_proposicao.jsonl", [
        {"id_votacao": k, **v} for k, v in voto_prop.items()
    ])
    write_json(
        out / "resumo.json",
        {
            "fetched_at": utc_now(),
            "anos": anos(),
            "deputados_alvo": len(dep_ids),
            "autores": len(autores_rows),
            "proposicoes": len(props_meta),
            "votacoes": len(votacoes_meta),
            "votos": len(votos_rows),
            "votacao_proposicao": len(voto_prop),
            "votos_com_proposicao": sum(1 for v in votos_rows if v.get("id_proposicao")),
        },
    )
    write_manifest(
        out,
        "camara_legislativo",
        files_meta,
        extra={"ingestion_run_id": run["ingestion_run_id"], "fetched_at": utc_now()},
    )
    mark_ingested(
        "camara_legislativo",
        run_id=run["ingestion_run_id"],
        counts={
            "proposicoes": len(props_meta),
            "autores": len(autores_rows),
            "votos": len(votos_rows),
        },
        ok=True,
    )
    print(
        f"OK Câmara legislativo: props={len(props_meta)} autores={len(autores_rows)} "
        f"votos={len(votos_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
