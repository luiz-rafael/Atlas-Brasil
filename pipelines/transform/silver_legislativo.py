#!/usr/bin/env python3
"""Silver legislativo (Câmara + Senado) + remuneração macro.

Métricas honestas:
- Projetos ≠ toda proposição (REQ/RIC/EMC…)
- Presença: votos registrados ÷ votações do Plenário no período (ausência = sem registro)
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, write_json, write_jsonl  # noqa: E402

# Tipos tratados como "projetos" na UI (não inclui requerimentos/emendas de comissão)
TIPOS_PROJETO = frozenset(
    {"PL", "PLP", "PEC", "PLN", "PLC", "PLS", "PDC", "PDL", "PRC", "MPV"}
)


def latest_day(fonte: str) -> Path | None:
    base = LAKE / "bronze" / fonte
    if not base.exists():
        return None
    days = [p for p in base.iterdir() if p.is_dir()]
    days = [p for p in days if len(p.name) == 10 and p.name[4] == "-"] or days
    return max(days, key=lambda p: p.name) if days else None


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def is_ausente(voto: str | None) -> bool:
    v = (voto or "").strip().lower()
    return v in {"ausente", "ausência", "-"} or "ausente" in v


def is_presente_voto(voto: str | None) -> bool:
    v = (voto or "").strip().lower()
    if not v or is_ausente(v):
        return False
    # obstrução / abstenção / art.17 ainda é presença na sessão de votação
    return True


def year_of(row: dict) -> int | None:
    ano = row.get("ano") or row.get("ano_arquivo")
    if isinstance(ano, int):
        return ano
    if isinstance(ano, str) and ano.isdigit():
        return int(ano)
    for key in ("data_hora", "data", "votacao_data"):
        s = str(row.get(key) or "")
        if len(s) >= 4 and s[:4].isdigit():
            return int(s[:4])
    return None


def aggregate_votos(
    votos: list[dict],
    votacoes: list[dict],
) -> dict[str, dict]:
    """Agrega votos; amostra de projetos vem agrupada por proposição (mais recente primeiro)."""
    plen_by_year: dict[int, set[str]] = defaultdict(set)
    plen_all: set[str] = set()
    votacao_meta: dict[str, dict] = {}
    for v in votacoes:
        vid = str(v.get("id_votacao") or v.get("id") or "")
        if vid:
            votacao_meta[vid] = v
        org = (v.get("orgao") or "").upper()
        if org not in {"PLEN", "PLENÁRIO", "PLENARIO"}:
            continue
        if not vid:
            continue
        plen_all.add(vid)
        y = year_of(v)
        if y:
            plen_by_year[y].add(vid)

    by: dict[str, dict] = {}
    voted_ids: dict[str, set[str]] = defaultdict(set)

    for row in votos:
        pid = row.get("person_id")
        if not pid:
            continue
        ag = by.setdefault(
            pid,
            {
                "person_id": pid,
                "casa": row.get("casa"),
                "total_votacoes": 0,
                "presente": 0,
                "ausente": 0,
                "por_voto": Counter(),
                "por_ano": defaultdict(lambda: {"total": 0, "presente": 0, "ausente": 0}),
                "by_prop": {},
                "anos_com_voto": set(),
            },
        )
        ag["total_votacoes"] += 1
        voto = row.get("voto") or ""
        ag["por_voto"][voto] += 1
        ano = year_of(row)
        if ano:
            ag["anos_com_voto"].add(ano)
        bucket = ag["por_ano"][ano] if ano else None
        if bucket is not None:
            bucket["total"] += 1
        vid = str(row.get("id_votacao") or "")
        if vid:
            voted_ids[pid].add(vid)
        if is_ausente(voto):
            ag["ausente"] += 1
            if bucket is not None:
                bucket["ausente"] += 1
        elif is_presente_voto(voto):
            ag["presente"] += 1
            if bucket is not None:
                bucket["presente"] += 1
        prop_id = row.get("id_proposicao") or row.get("id_materia")
        if prop_id or row.get("proposicao_titulo"):
            meta_v = votacao_meta.get(vid) or {}
            titulo = (
                row.get("proposicao_titulo")
                or (
                    f"{row.get('proposicao_sigla') or ''} "
                    f"{row.get('proposicao_numero') or ''}/"
                    f"{row.get('proposicao_ano') or ''}"
                ).strip()
            )
            key = str(prop_id or titulo)
            g = ag["by_prop"].setdefault(
                key,
                {
                    "id_proposicao": prop_id,
                    "titulo": titulo,
                    "sigla": row.get("proposicao_sigla"),
                    "numero": row.get("proposicao_numero"),
                    "ano": row.get("proposicao_ano"),
                    "ementa": (row.get("proposicao_ementa") or "")[:220],
                    "votos": [],
                    "qtd_votacoes": 0,
                },
            )
            g["qtd_votacoes"] += 1
            if len(g["votos"]) < 40:
                g["votos"].append(
                    {
                        "voto": voto,
                        "data": row.get("data_hora") or row.get("data") or meta_v.get("data"),
                        "id_votacao": row.get("id_votacao"),
                        "descricao_votacao": (meta_v.get("descricao") or "")[:220],
                        "orgao": meta_v.get("orgao") or row.get("orgao"),
                    }
                )

    out = {}
    for pid, ag in by.items():
        anos = sorted(ag["anos_com_voto"]) or sorted(plen_by_year.keys())
        universe: set[str] = set()
        for y in anos:
            universe |= plen_by_year.get(y, set())
        if not universe and plen_all:
            universe = set(plen_all)
        presentes_ids = voted_ids.get(pid, set()) & universe
        if universe:
            total_u = len(universe)
            presente_u = len(presentes_ids)
            ausente_u = max(0, total_u - presente_u)
            taxa = round(presente_u / total_u, 4) if total_u else None
            metodo = "plen_universo"
        else:
            total_u = ag["total_votacoes"] or 1
            presente_u = ag["presente"]
            ausente_u = ag["ausente"]
            taxa = round(presente_u / total_u, 4)
            metodo = "somente_registros_voto"

        # Agrupa por proposição (vários votos no mesmo PL são normais: emendas, destaques…)
        grupos = list(ag.get("by_prop", {}).values())
        for g in grupos:
            g["votos"].sort(key=lambda x: str(x.get("data") or ""), reverse=True)
            g["ultima_data"] = g["votos"][0].get("data") if g["votos"] else None
        grupos.sort(key=lambda x: str(x.get("ultima_data") or ""), reverse=True)

        amostra_grupos: list[dict] = []
        for g in grupos[:50]:
            votos_g = g["votos"][:8]
            amostra_grupos.append({**g, "votos": votos_g})

        flat_amostra = []
        for g in amostra_grupos:
            for vv in g.get("votos") or []:
                flat_amostra.append(
                    {
                        "voto": vv.get("voto"),
                        "data": vv.get("data"),
                        "id_proposicao": g.get("id_proposicao"),
                        "titulo": g.get("titulo"),
                        "ementa": g.get("ementa"),
                        "id_votacao": vv.get("id_votacao"),
                        "descricao_votacao": vv.get("descricao_votacao"),
                    }
                )

        out[pid] = {
            "person_id": pid,
            "casa": ag["casa"],
            "total_votacoes_nominais": total_u if universe else ag["total_votacoes"],
            "votos_registrados": ag["total_votacoes"],
            "presente": presente_u if universe else ag["presente"],
            "ausente": ausente_u if universe else ag["ausente"],
            "taxa_presenca": taxa,
            "metodo_presenca": metodo,
            "por_voto": dict(ag["por_voto"]),
            "por_ano": {
                str(k): v for k, v in sorted(ag["por_ano"].items(), key=lambda x: str(x[0]))
            },
            "amostra_votos_projetos": flat_amostra[:40],
            "votos_por_proposicao": amostra_grupos,
            "anos_atividade": anos,
            "aviso_presenca": (
                "Presença oficial de plenário não está nesta métrica de votos. "
                "Várias linhas no mesmo PL são votações nominais distintas "
                "(emenda, destaque, requerimento) — ver descrição de cada votação. "
                "A amostra lista as proposições com voto mais recentes."
            ),
        }
    return out


def prop_ano_e_data(meta: dict) -> tuple[int | None, str | None]:
    """Ano oficial; se vier 0/vazio (pareceres etc.), deriva de data_apresentacao."""
    data = meta.get("data_apresentacao") or meta.get("dataApresentacao")
    data_s = str(data) if data else None
    ano_raw = meta.get("ano")
    ano_i: int | None = None
    try:
        if ano_raw is not None and str(ano_raw).strip() not in {"", "0"}:
            ano_i = int(ano_raw)
    except Exception:
        ano_i = None
    if ano_i is None and data_s and len(data_s) >= 4 and data_s[:4].isdigit():
        ano_i = int(data_s[:4])
    return ano_i, data_s


def label_prop(meta: dict | None, prop_id: str) -> str:
    if not meta:
        return str(prop_id)
    sigla = meta.get("sigla_tipo") or "PROP"
    num = meta.get("numero") or ""
    ano_i, _ = prop_ano_e_data(meta)
    ano = ano_i if ano_i is not None else (meta.get("ano") or "")
    return f"{sigla} {num}/{ano}".strip()


def main() -> int:
    cam = latest_day("camara_legislativo")
    sen = latest_day("senado_legislativo")
    rem = latest_day("remuneracao_oficial")

    props = []
    autores = []
    votos = []
    votacoes = []
    if cam:
        props.extend(load_jsonl(cam / "proposicoes.jsonl"))
        autores.extend(load_jsonl(cam / "proposicoes_autores.jsonl"))
        votos.extend(load_jsonl(cam / "votos.jsonl"))
        votacoes.extend(load_jsonl(cam / "votacoes.jsonl"))
    if sen:
        for m in load_jsonl(sen / "materias.jsonl"):
            props.append(
                {
                    "id_proposicao": f"sen:{m.get('id_materia')}",
                    "sigla_tipo": m.get("sigla"),
                    "numero": m.get("numero"),
                    "ano": m.get("ano"),
                    "ementa": m.get("ementa"),
                    "uri": m.get("uri"),
                    "casa": "senado",
                }
            )
        for a in load_jsonl(sen / "autorias.jsonl"):
            autores.append(
                {
                    "id_proposicao": f"sen:{a.get('id_materia')}",
                    "person_id": a.get("person_id"),
                    "deputado_id": None,
                    "casa": "senado",
                    "ano": a.get("ano"),
                    "autor_principal": a.get("autor_principal"),
                }
            )
        votos.extend(load_jsonl(sen / "votos.jsonl"))

    props_by_id = {str(p.get("id_proposicao")): p for p in props if p.get("id_proposicao")}
    freq = aggregate_votos(votos, votacoes)

    props_por_pessoa: dict[str, list] = defaultdict(list)
    tipos_por_pessoa: dict[str, Counter] = defaultdict(Counter)
    for a in autores:
        pid = a.get("person_id")
        prop_id = a.get("id_proposicao")
        if not pid or not prop_id:
            continue
        props_por_pessoa[pid].append(prop_id)
        meta = props_by_id.get(str(prop_id)) or {}
        tipo = (meta.get("sigla_tipo") or a.get("tipo") or "?").upper()
        tipos_por_pessoa[pid][tipo] += 1

    resumo_pessoa = []
    for pid, prop_ids in props_por_pessoa.items():
        uniq = list(dict.fromkeys([x for x in prop_ids if x]))
        tipo_uniq: Counter = Counter()
        items = []
        for pid_prop in uniq:
            meta = props_by_id.get(str(pid_prop)) or {}
            tipo = str(meta.get("sigla_tipo") or "?").upper()
            tipo_uniq[tipo] += 1
            ano_i, data_s = prop_ano_e_data(meta)
            items.append(
                {
                    "id": pid_prop,
                    "label": label_prop(meta, str(pid_prop)),
                    "tipo": tipo,
                    "numero": meta.get("numero"),
                    "ano": ano_i if ano_i is not None else meta.get("ano"),
                    "data_apresentacao": data_s,
                    "ementa": (meta.get("ementa") or "")[:180],
                    "_ano_sort": ano_i or 0,
                    "_data_sort": data_s or "",
                    "_id_sort": str(pid_prop),
                }
            )
        # mais recente → mais antiga (data de apresentação, depois ano, depois id)
        items.sort(
            key=lambda x: (x["_data_sort"], x["_ano_sort"], x["_id_sort"]),
            reverse=True,
        )
        for it in items:
            it.pop("_ano_sort", None)
            it.pop("_data_sort", None)
            it.pop("_id_sort", None)
        qtd_projetos = sum(v for k, v in tipo_uniq.items() if k in TIPOS_PROJETO)
        f = freq.get(pid) or {}
        anos = f.get("anos_atividade") or []
        resumo_pessoa.append(
            {
                "person_id": pid,
                "qtd_proposicoes": len(uniq),
                "qtd_projetos": qtd_projetos,
                "por_tipo": dict(tipo_uniq),
                "proposicao_ids": [x["id"] for x in items[:500]],
                "proposicoes_sample": items[:12],
                "proposicoes_lista": items[:500],
                "frequencia": f,
                "ano_inicio_atividade": min(anos) if anos else None,
                "ano_fim_atividade": max(anos) if anos else None,
                "anos_atividade": (max(anos) - min(anos) + 1) if anos else None,
            }
        )
    for pid, f in freq.items():
        if pid not in props_por_pessoa:
            anos = f.get("anos_atividade") or []
            resumo_pessoa.append(
                {
                    "person_id": pid,
                    "qtd_proposicoes": 0,
                    "qtd_projetos": 0,
                    "por_tipo": {},
                    "proposicao_ids": [],
                    "proposicoes_sample": [],
                    "proposicoes_lista": [],
                    "frequencia": f,
                    "ano_inicio_atividade": min(anos) if anos else None,
                    "ano_fim_atividade": max(anos) if anos else None,
                    "anos_atividade": (max(anos) - min(anos) + 1) if anos else None,
                }
            )

    rem_series = []
    if rem and (rem / "subsidio_por_cargo_ano.json").exists():
        rem_series = json.loads((rem / "subsidio_por_cargo_ano.json").read_text(encoding="utf-8"))

    out = LAKE / "silver" / "legislativo"
    out.mkdir(parents=True, exist_ok=True)
    stamp = day_stamp()
    write_jsonl(out / f"proposicoes_{stamp}.jsonl", props)
    write_jsonl(out / "proposicoes_latest.jsonl", props)
    write_jsonl(out / f"autores_{stamp}.jsonl", autores)
    write_jsonl(out / "autores_latest.jsonl", autores)
    write_jsonl(out / f"votos_{stamp}.jsonl", votos)
    write_jsonl(out / "votos_latest.jsonl", votos)
    write_jsonl(out / f"resumo_pessoa_{stamp}.jsonl", resumo_pessoa)
    write_jsonl(out / "resumo_pessoa_latest.jsonl", resumo_pessoa)
    write_json(out / "remuneracao_macro.json", rem_series)
    write_json(
        out / "meta.json",
        {
            "proposicoes": len(props),
            "autores": len(autores),
            "votos": len(votos),
            "votacoes": len(votacoes),
            "pessoas": len(resumo_pessoa),
            "tipos_projeto": sorted(TIPOS_PROJETO),
        },
    )
    print(
        f"OK silver legislativo: props={len(props)} autores={len(autores)} "
        f"votos={len(votos)} votacoes={len(votacoes)} pessoas={len(resumo_pessoa)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
