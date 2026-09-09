#!/usr/bin/env python3
"""
Executivo federal (escopo Atlas): Presidentes, Vices e Ministros de Estado.

- Seed oficial curado 2010–hoje (chefes/vices) com URLs.
- Ministros atuais: tentativa de páginas Planalto + lista seed histórica.
- Não inclui governadores/prefeitos (fora do MVP).

Gera bronze + entidades prontas para gold_executivo_merge.
"""

from __future__ import annotations

import json
import re
import sys
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
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

# Mandatos presidenciais no período (fonte: TSE / Planalto — registro público)
PRESIDENTES = [
    {
        "id": "p_exec_pres_lula_2010",
        "nome": "Luiz Inácio Lula da Silva",
        "cargo": "presidente_republica",
        "periodo_inicio": "2003-01-01",
        "periodo_fim": "2010-12-31",
        "partido": "PT",
        "fonte_url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia",
        "tags": ["executivo", "ex_ocupante", "presidente"],
    },
    {
        "id": "p_exec_pres_dilma_1",
        "nome": "Dilma Vana Rousseff",
        "cargo": "presidente_republica",
        "periodo_inicio": "2011-01-01",
        "periodo_fim": "2016-08-31",
        "partido": "PT",
        "fonte_url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia",
        "tags": ["executivo", "ex_ocupante", "presidente"],
    },
    {
        "id": "p_exec_pres_temer",
        "nome": "Michel Miguel Elias Temer Lulia",
        "cargo": "presidente_republica",
        "periodo_inicio": "2016-08-31",
        "periodo_fim": "2018-12-31",
        "partido": "MDB",
        "fonte_url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia",
        "tags": ["executivo", "ex_ocupante", "presidente"],
    },
    {
        "id": "p_exec_pres_bolsonaro",
        "nome": "Jair Messias Bolsonaro",
        "cargo": "presidente_republica",
        "periodo_inicio": "2019-01-01",
        "periodo_fim": "2022-12-31",
        "partido": "PL",
        "fonte_url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia",
        "tags": ["executivo", "ex_ocupante", "presidente"],
    },
    {
        "id": "p_exec_pres_lula_3",
        "nome": "Luiz Inácio Lula da Silva",
        "cargo": "presidente_republica",
        "periodo_inicio": "2023-01-01",
        "periodo_fim": None,
        "partido": "PT",
        "fonte_url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia",
        "tags": ["executivo", "no_poder", "presidente"],
        "no_poder": True,
    },
]

VICES = [
    {
        "id": "p_exec_vice_temer",
        "nome": "Michel Miguel Elias Temer Lulia",
        "cargo": "vice_presidente",
        "periodo_inicio": "2011-01-01",
        "periodo_fim": "2016-08-31",
        "partido": "MDB",
        "fonte_url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia",
        "tags": ["executivo", "ex_ocupante", "vice_presidente"],
    },
    {
        "id": "p_exec_vice_mourao",
        "nome": "Hamilton Mourão",
        "cargo": "vice_presidente",
        "periodo_inicio": "2019-01-01",
        "periodo_fim": "2022-12-31",
        "partido": "Republicanos",
        "fonte_url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia",
        "tags": ["executivo", "ex_ocupante", "vice_presidente"],
    },
    {
        "id": "p_exec_vice_alckmin",
        "nome": "Geraldo José Rodrigues Alckmin Filho",
        "cargo": "vice_presidente",
        "periodo_inicio": "2023-01-01",
        "periodo_fim": None,
        "partido": "PSB",
        "fonte_url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia",
        "tags": ["executivo", "no_poder", "vice_presidente"],
        "no_poder": True,
    },
]

# Gabinete atual (seed curado — scrape Planalto é best-effort).
# Fonte pública: https://www.gov.br/planalto/pt-br/conheca-a-presidencia/ministros-e-ministras/ministros-1
# Atualizado após reforma eleitoral abr/2026 (titulares técnicos / remanescentes).
FONTE_MINISTROS = (
    "https://www.gov.br/planalto/pt-br/conheca-a-presidencia/ministros-e-ministras/ministros-1"
)

MINISTROS_ATUAIS = [
    {
        "id": "p_exec_min_casa_civil",
        "nome": "Miriam Belchior",
        "pasta": "Casa Civil",
        "partido": None,
    },
    {
        "id": "p_exec_min_fazenda",
        "nome": "Dario Durigan",
        "pasta": "Fazenda",
        "partido": None,
    },
    {
        "id": "p_exec_min_planejamento",
        "nome": "Bruno Moretti",
        "pasta": "Planejamento e Orçamento",
        "partido": None,
    },
    {
        "id": "p_exec_min_educacao",
        "nome": "Leonardo Barchini",
        "pasta": "Educação",
        "partido": None,
    },
    {
        "id": "p_exec_min_justica",
        "nome": "Ricardo Lewandowski",
        "pasta": "Justiça e Segurança Pública",
        "partido": None,
    },
    {
        "id": "p_exec_min_defesa",
        "nome": "José Múcio Monteiro Filho",
        "pasta": "Defesa",
        "partido": None,
    },
    {
        "id": "p_exec_min_relacoes_exteriores",
        "nome": "Mauro Vieira",
        "pasta": "Relações Exteriores",
        "partido": None,
    },
    {
        "id": "p_exec_min_saude",
        "nome": "Alexandre Padilha",
        "pasta": "Saúde",
        "partido": "PT",
    },
    {
        "id": "p_exec_min_meio_ambiente",
        "nome": "João Paulo Capobianco",
        "pasta": "Meio Ambiente e Mudança do Clima",
        "partido": None,
    },
    {
        "id": "p_exec_min_agricultura",
        "nome": "André de Paula",
        "pasta": "Agricultura e Pecuária",
        "partido": "PSD",
    },
    {
        "id": "p_exec_min_desenvolvimento_agrario",
        "nome": "Fernanda Machiaveli",
        "pasta": "Desenvolvimento Agrário e Agricultura Familiar",
        "partido": None,
    },
    {
        "id": "p_exec_min_cidades",
        "nome": "Antônio Vladimir Lima",
        "pasta": "Cidades",
        "partido": None,
    },
    {
        "id": "p_exec_min_direitos_humanos",
        "nome": "Janine Mello",
        "pasta": "Direitos Humanos e da Cidadania",
        "partido": None,
    },
    {
        "id": "p_exec_min_esporte",
        "nome": "Paulo Henrique Cordeiro Perna",
        "pasta": "Esporte",
        "partido": None,
    },
    {
        "id": "p_exec_min_portos",
        "nome": "Tomé Barros Monteiro da Franca",
        "pasta": "Portos e Aeroportos",
        "partido": None,
    },
    {
        "id": "p_exec_min_mdic",
        "nome": "Márcio Elias Rosa",
        "pasta": "Desenvolvimento, Indústria, Comércio e Serviços",
        "partido": None,
    },
    {
        "id": "p_exec_min_relacoes_institucionais",
        "nome": "José Nobre Guimarães",
        "pasta": "Relações Institucionais",
        "partido": "PT",
    },
    {
        "id": "p_exec_min_comunicacao",
        "nome": "Sidônio Palmeira",
        "pasta": "Comunicação Social",
        "partido": None,
    },
    {
        "id": "p_exec_min_secom_boulos",
        "nome": "Guilherme Castro Boulos",
        "pasta": "Secretaria-Geral da Presidência",
        "partido": "PSOL",
    },
    {
        "id": "p_exec_min_cgu",
        "nome": "Vinícius Marques de Carvalho",
        "pasta": "Controladoria-Geral da União",
        "partido": None,
    },
    {
        "id": "p_exec_min_agu",
        "nome": "Jorge Messias",
        "pasta": "Advocacia-Geral da União",
        "partido": None,
    },
    {
        "id": "p_exec_min_minas_energia",
        "nome": "Alexandre Silveira",
        "pasta": "Minas e Energia",
        "partido": "PSD",
    },
    {
        "id": "p_exec_min_trabalho",
        "nome": "Luiz Marinho",
        "pasta": "Trabalho e Emprego",
        "partido": "PT",
    },
    {
        "id": "p_exec_min_previdencia",
        "nome": "Wolney Queiroz",
        "pasta": "Previdência Social",
        "partido": "PDT",
    },
    {
        "id": "p_exec_min_gestao",
        "nome": "Esther Dweck",
        "pasta": "Gestão e da Inovação em Serviços Públicos",
        "partido": None,
    },
    {
        "id": "p_exec_min_ciencia",
        "nome": "Luciana Santos",
        "pasta": "Ciência, Tecnologia e Inovação",
        "partido": "PCdoB",
    },
    {
        "id": "p_exec_min_pesca",
        "nome": "Rivetla Edipo Araujo Cruz",
        "pasta": "Aquicultura e Pesca",
        "partido": None,
    },
    {
        "id": "p_exec_min_povos_indigenas",
        "nome": "Luiz Henrique Eloy Amado",
        "pasta": "Povos Indígenas",
        "partido": None,
    },
]


def _seed_ministros() -> list[dict]:
    out = []
    for m in MINISTROS_ATUAIS:
        out.append(
            {
                "id": m["id"],
                "nome": m["nome"],
                "cargo": "ministro_estado",
                "pasta": m.get("pasta"),
                "periodo_inicio": "2026-04-01",
                "periodo_fim": None,
                "partido": m.get("partido"),
                "fonte_url": FONTE_MINISTROS,
                "tags": ["executivo", "ministro", "no_poder", "seed_gabinete"],
                "no_poder": True,
                "cargo_label": f"Ministro(a) — {m.get('pasta')}",
            }
        )
    return out


def fetch_ministros_atuais() -> list[dict]:
    """Best-effort: páginas oficiais do Planalto; fallback = seed curado."""
    urls = [
        FONTE_MINISTROS,
        "https://www.gov.br/planalto/pt-br/composicao/ministros",
        "https://www.gov.br/planalto/pt-br/acesso-a-informacao/ministros",
    ]
    found: list[dict] = []
    seen: set[str] = set()
    for url in urls:
        try:
            r = http_get(url, timeout=45.0)
            if r.status_code != 200:
                continue
            html = r.text
            for m in re.finditer(
                r"(?:ministro|ministra)[^<]{0,80}</[^>]+>\s*<[^>]+>([^<]{5,80})",
                html,
                flags=re.I,
            ):
                nome = re.sub(r"\s+", " ", m.group(1)).strip()
                if len(nome) < 5 or nome.lower() in seen:
                    continue
                seen.add(nome.lower())
                found.append(
                    {
                        "id": f"p_exec_min_{abs(hash(nome.lower())) % 10**10}",
                        "nome": nome,
                        "cargo": "ministro_estado",
                        "periodo_inicio": None,
                        "periodo_fim": None,
                        "partido": None,
                        "fonte_url": url,
                        "tags": ["executivo", "ministro", "no_poder", "scrape_planalto"],
                        "no_poder": True,
                    }
                )
            for m in re.finditer(
                r"Minist[eé]rio[^<]{0,60}</[^>]+>[\s\S]{0,200}?<strong>([^<]{5,90})</strong>",
                html,
                flags=re.I,
            ):
                nome = re.sub(r"\s+", " ", m.group(1)).strip()
                if len(nome) < 5 or nome.lower() in seen:
                    continue
                seen.add(nome.lower())
                found.append(
                    {
                        "id": f"p_exec_min_{abs(hash(nome.lower())) % 10**10}",
                        "nome": nome,
                        "cargo": "ministro_estado",
                        "fonte_url": url,
                        "tags": ["executivo", "ministro", "no_poder", "scrape_planalto"],
                        "no_poder": True,
                    }
                )
        except Exception as e:
            print(f"  planalto fail {url}: {e}", file=sys.stderr)
    if len(found) < 5:
        print(
            f"  scrape fraco ({len(found)}); usando seed curado ({len(MINISTROS_ATUAIS)})",
            file=sys.stderr,
        )
        return _seed_ministros()
    return found


def main() -> int:
    run = start_run("executivo_federal", "executivo.federal")
    out = bronze_dir("executivo_federal")
    pessoas = []
    for row in PRESIDENTES + VICES:
        pessoas.append({**row, "tipo": "pessoa", "fetched_at": utc_now()})
    mins = fetch_ministros_atuais()
    # Garante seed mesmo se scrape trouxe poucos — dedupe por nome
    by_nome = {p["nome"].lower(): p for p in pessoas}
    for m in mins:
        key = m["nome"].lower()
        if key in by_nome:
            continue
        pessoas.append({**m, "tipo": "pessoa", "fetched_at": utc_now()})
        by_nome[key] = m
    # Se ainda sem ministros, força seed
    n_min = sum(1 for p in pessoas if p.get("cargo") == "ministro_estado")
    if n_min == 0:
        for m in _seed_ministros():
            pessoas.append({**m, "tipo": "pessoa", "fetched_at": utc_now()})
        n_min = len(MINISTROS_ATUAIS)

    write_jsonl(out / "pessoas_executivo.jsonl", pessoas)
    write_json(
        out / "resumo.json",
        {
            "fetched_at": utc_now(),
            "presidentes": len(PRESIDENTES),
            "vices": len(VICES),
            "ministros": n_min,
            "total": len(pessoas),
            "escopo": "federal_executivo_2010_plus",
            "fora_mvp": ["governador", "prefeito", "vereador", "deputado_estadual"],
        },
    )
    write_manifest(
        out,
        "executivo_federal",
        [{"file": "pessoas_executivo.jsonl", "count": len(pessoas)}],
        extra={"ingestion_run_id": run["ingestion_run_id"]},
    )
    mark_ingested(
        "executivo_federal",
        run_id=run["ingestion_run_id"],
        counts={"pessoas": len(pessoas), "ministros": n_min},
        ok=True,
    )
    print(
        f"OK executivo: total={len(pessoas)} "
        f"(pres={len(PRESIDENTES)} vice={len(VICES)} min={n_min})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
