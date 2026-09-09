#!/usr/bin/env python3
"""
Coleta TOTAL — políticos em exercício (Câmara + Senado) e dados ligados.

Ordem: Casa → gold → perfis → TSE/PNCP/órgãos → CGU emendas/sanções/legal → ER.

Não usa caps de amostra (defaults “full”). Sobrescreva via env se precisar.
Pule etapas: COLETA_SKIP=neo4j,postgres,pncp
Só algumas: COLETA_ONLY=camara_api,senado_api,silver_politicos,gold_kb
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
PY = sys.executable
REPORTS = ROOT / "reports"


def load_dotenv() -> None:
    path = PROJECT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("$env:"):
            line = line[5:]
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def apply_full_defaults(env: dict[str, str]) -> None:
    """Cobertura plena para ~594 ativos.

    Por padrão FORÇA caps de amostra da sessão (COLETA_FORCE_FULL=1).
    Use COLETA_FORCE_FULL=0 para só preencher o que faltar (setdefault).
    """
    y = datetime.now().year
    defaults = {
        "ATLAS_REPLACE_LEGACY_KB": "1",
        "ATLAS_HTTP_RPS": "2",
        # Casa
        "CAMARA_DETAIL_LIMIT": "0",  # detalhe no enrich_perfis
        "SENADO_DETAIL_LIMIT": "0",
        "TSE_MAX_RESOURCES": "12",
        "TSE_PACKAGES": "candidatos-2022,candidatos-2024",
        # Perfis
        "PERFIL_LIMIT": "0",
        "PERFIL_DESPESAS": "1",
        # Mandato/eleição — janela Atlas (default 2010→hoje via escopo)
        "PERFIL_DESPESA_ANOS": ",".join(str(a) for a in range(2010, y + 1)),
        "DESPESA_MAX_PAGES": "80",
        "PERFIL_RESUME": "0",  # força refresh completo
        "PERFIL_SKIP_GOLD": "0",
        "CAMARA_HISTORICO": "1",
        "ATLAS_ANO_INICIO": "2010",
        # Órgãos / frentes
        "CAMARA_ORGAOS_PAGES": "50",
        "CAMARA_FRENTES_MEMBROS_LIMIT": "-1",
        # TSE bens / prestacao / PNCP
        "TSE_BENS_PACKAGE": "candidatos-2022",
        "TSE_PRESTACAO_MAX": "4",
        "TSE_PRESTACAO_MAX_MB": "120",
        "PNCP_DIAS": "30",
        "PNCP_MAX_PAGES": "25",
        "PNCP_PAGE_SIZE": "50",
        "PNCP_MAX_ROWS": "8000",
        "F1_MERGE_PERFIS": "1",
        # CGU — todos autores Casa, ciclo Atlas
        "CGU_EMENDA_AUTOR_LIMIT": "1000",
        "CGU_EMENDA_MAX_PAGES": "15",
        "CGU_EMENDA_ANOS": ",".join(str(a) for a in range(2010, y + 1)),
        "CGU_CNPJ_LIMIT": "2000",
        "CGU_LEGAL_PAGES": "10",
        "CGU_CEAF_NOME_LIMIT": "700",
        "CGU_CEPIM_CNPJ_LIMIT": "700",
        "CGU_OPS_NEWS_LIMIT": "20",
        "ONDA2_SKIP_DATAJUD": "1",
        "LEG_ANOS": ",".join(str(a) for a in range(2010, y + 1)),
        "LEG_GOLD_MAX_PROPS": "25000",
        # Load — skip se stack local não estiver no ar
        "NEO4J_SKIP": "1",
    }
    force = env.get("COLETA_FORCE_FULL", "1") == "1"
    for k, v in defaults.items():
        if force or k not in env:
            env[k] = v


STEPS: list[tuple[str, str]] = [
    # 1) Núcleo ativos
    ("ingest/camara_api.py", "Câmara — deputados em exercício"),
    ("ingest/senado_api.py", "Senado — senadores em exercício"),
    ("ingest/tse_bulk.py", "TSE bulk candidatos"),
    ("transform/silver_politicos.py", "Silver políticos"),
    ("transform/gold_kb.py", "Gold KB (p_cam_/p_sen_)"),
    ("load/export_kb_json.py", "Export KB JSON"),
    # 2) Perfis completos
    ("ingest/enrich_perfis.py", "Enriquecer perfis + despesas"),
    ("ingest/executivo_federal.py", "Executivo Pres/Vice/Ministros"),
    ("transform/gold_executivo_merge.py", "Gold executivo"),
    # 2b) Legislativo + remuneração macro
    ("ingest/camara_legislativo.py", "Câmara proposições/votações"),
    ("ingest/senado_legislativo.py", "Senado matérias/votações"),
    ("ingest/remuneracao_oficial.py", "Remuneração macro cargo×ano"),
    ("transform/silver_legislativo.py", "Silver legislativo"),
    ("transform/gold_legislativo_merge.py", "Gold legislativo merge"),
    # 3) Dinheiro / órgãos
    ("ingest/tse_bens.py", "TSE bens 2022"),
    ("ingest/tse_prestacao.py", "TSE prestação"),
    ("ingest/pncp_api.py", "PNCP contratos"),
    ("ingest/transferegov_api.py", "Transferegov"),
    ("ingest/camara_orgaos.py", "Câmara órgãos/frentes"),
    ("transform/silver_f1.py", "Silver F1"),
    ("transform/merge_perfis_gold.py", "Merge perfis → gold"),
    ("transform/gold_f1_merge.py", "Gold F1 merge"),
    ("transform/er_casas_tse.py", "ER Casa ↔ TSE bens"),
    # 4) CGU focado em políticos/CNPJs da KB
    ("ingest/cgu_portal.py", "CGU emendas + CEIS/CNEP"),
    ("ingest/cgu_legal.py", "CGU legal (CEAF/CEPIM/ops)"),
    ("transform/silver_cgu.py", "Silver CGU"),
    ("transform/silver_empresas.py", "Silver empresas"),
    ("transform/gold_cgu_merge.py", "Gold CGU merge"),
    ("transform/gold_legal_cases.py", "Gold LEGAL_CASE mentioned_in"),
    ("transform/er_casas_tse.py", "ER Casa ↔ TSE (repass)"),
    # 5) Load opcional
    ("load/to_postgres.py", "Postgres"),
    ("load/to_neo4j.py", "Neo4j"),
]


CRITICAL = {
    "camara_api",
    "senado_api",
    "silver_politicos",
    "gold_kb",
}


def step_key(script: str) -> str:
    return script.split("/")[-1].replace(".py", "")


def main() -> int:
    load_dotenv()
    env = os.environ.copy()
    apply_full_defaults(env)

    skip = {s.strip() for s in env.get("COLETA_SKIP", "postgres,neo4j").split(",") if s.strip()}
    only = {s.strip() for s in env.get("COLETA_ONLY", "").split(",") if s.strip()}

    REPORTS.mkdir(parents=True, exist_ok=True)
    print("=== Coleta TOTAL — políticos ativos ===")
    print(f"CGU key: {'sim' if env.get('ATLAS_PORTAL_API_KEY') else 'NÃO (emendas/sanções vão stub)'}")
    print(f"skip={sorted(skip) or '-'} only={sorted(only) or '-'}")
    print(
        f"emendas autores≤{env.get('CGU_EMENDA_AUTOR_LIMIT')} "
        f"anos={env.get('CGU_EMENDA_ANOS')} "
        f"despesas anos={env.get('PERFIL_DESPESA_ANOS')}"
    )

    # TSE bens 2024 em passo extra se pacote default for 2022
    codes: list[int] = []
    ran_bens_2024 = False

    for script, label in STEPS:
        key = step_key(script)
        if key in skip or script in skip:
            print(f"\n=== skip {label} ===")
            continue
        if only and key not in only and script not in only:
            continue

        print(f"\n=== {label} ===", flush=True)
        r = subprocess.run([PY, str(ROOT / script)], cwd=str(PROJECT), env=env)
        codes.append(r.returncode)
        if r.returncode != 0:
            print(f"aviso: {label} code={r.returncode}", file=sys.stderr)
            if key in CRITICAL:
                print(f"ABORT em {label}", file=sys.stderr)
                return r.returncode

        # segundo pacote de bens TSE
        if key == "tse_bens" and not ran_bens_2024 and "tse_bens" not in skip:
            if env.get("TSE_BENS_ALSO_2024", "1") == "1":
                ran_bens_2024 = True
                env2 = env.copy()
                env2["TSE_BENS_PACKAGE"] = "candidatos-2024"
                print("\n=== TSE bens 2024 ===", flush=True)
                r2 = subprocess.run(
                    [PY, str(ROOT / "ingest/tse_bens.py")], cwd=str(PROJECT), env=env2
                )
                codes.append(r2.returncode)

    # coverage
    try:
        sys.path.insert(0, str(PROJECT))
        from pipelines.common import write_json
        from pipelines.registry import coverage_report

        cov = coverage_report()
        out = REPORTS / "coverage_politicos_ativos.json"
        write_json(out, cov)
        print(f"\ncoverage → {out}")
    except Exception as e:
        print(f"coverage fail: {e}", file=sys.stderr)

    # resumo gold
    try:
        import json

        gold = PROJECT / "data" / "atlas-brasil-kb-gold.json"
        if gold.exists():
            kb = json.loads(gold.read_text(encoding="utf-8"))
            cam = sum(
                1
                for e in kb.get("entidades") or []
                if str(e.get("id", "")).startswith("p_cam_")
            )
            sen = sum(
                1
                for e in kb.get("entidades") or []
                if str(e.get("id", "")).startswith("p_sen_")
            )
            em = sum(1 for e in kb.get("entidades") or [] if e.get("emendas_resumo"))
            perf = sum(
                1 for e in kb.get("entidades") or [] if e.get("perfil_atualizado_em")
            )
            print(
                f"\nResumo gold: dep={cam} sen={sen} "
                f"perfis_atualizados={perf} com_emendas={em} "
                f"casos={len(kb.get('casos') or [])}"
            )
    except Exception as e:
        print(f"resumo fail: {e}", file=sys.stderr)

    print("\nColeta políticos ativos concluída.")
    return 0 if any(c == 0 for c in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
