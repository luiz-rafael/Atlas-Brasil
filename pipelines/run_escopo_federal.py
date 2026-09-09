#!/usr/bin/env python3
"""
Orquestra escopo federal 2010–hoje:
  Câmara histórica + Senado + Executivo + legislativo (voto↔projeto) + remuneraçāo.

Não coleta estados/municípios (fora do MVP).
DataJud permanece stub até a API voltar (ONDA2_SKIP_DATAJUD=1).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
PY = sys.executable


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


def main() -> int:
    load_dotenv()
    env = os.environ.copy()
    # força janela 2010–hoje
    env["ATLAS_ANO_INICIO"] = env.get("ATLAS_ANO_INICIO", "2010")
    env["CAMARA_HISTORICO"] = "1"
    env["ATLAS_REPLACE_LEGACY_KB"] = "1"
    env["ATLAS_HTTP_RPS"] = env.get("ATLAS_HTTP_RPS", "2")
    env["ONDA2_SKIP_DATAJUD"] = "1"
    env["LEG_GOLD_MAX_PROPS"] = env.get("LEG_GOLD_MAX_PROPS", "25000")
    env["NEO4J_SKIP"] = "1"

    from pipelines.config.escopo import anos_csv, camara_legislaturas

    # força anos do escopo (ignora LEG_ANOS residual da sessão)
    if env.get("ESCOPO_KEEP_LEG_ANOS", "0") != "1":
        env["LEG_ANOS"] = anos_csv()
    else:
        env["LEG_ANOS"] = env.get("LEG_ANOS") or anos_csv()
    env["CAMARA_LEGISLATURAS"] = env.get("CAMARA_LEGISLATURAS") or ",".join(
        str(x) for x in camara_legislaturas()
    )
    if env.get("ESCOPO_KEEP_LEG_ANOS", "0") != "1":
        env["CGU_EMENDA_ANOS"] = env["LEG_ANOS"]
        env["PERFIL_DESPESA_ANOS"] = env["LEG_ANOS"]
    else:
        env["CGU_EMENDA_ANOS"] = env.get("CGU_EMENDA_ANOS") or env["LEG_ANOS"]
        env["PERFIL_DESPESA_ANOS"] = env.get("PERFIL_DESPESA_ANOS") or env["LEG_ANOS"]

    print("=== Escopo federal Atlas ===")
    print(f"anos={env['LEG_ANOS']}")
    print(f"legislaturas={env['CAMARA_LEGISLATURAS']}")
    print("incluso: Pres/Vice/Ministros + STF + Dep/Sen | fora: estados/municípios/STJ")

    steps = [
        ("ingest/camara_api.py", "Câmara histórica (legs)"),
        ("ingest/senado_api.py", "Senado atual"),
        ("ingest/executivo_federal.py", "Executivo Pres/Vice/Ministros"),
        ("ingest/stf_composicao.py", "Composição STF"),
        ("transform/silver_politicos.py", "Silver políticos"),
        ("transform/gold_kb.py", "Gold KB base"),
        ("load/export_kb_json.py", "Export KB"),
        ("transform/gold_executivo_merge.py", "Gold executivo"),
        ("transform/gold_stf_composicao_merge.py", "Gold STF composição"),
        ("ingest/camara_legislativo.py", "Câmara props/votos"),
        ("ingest/senado_legislativo.py", "Senado matérias/votos"),
        ("ingest/remuneracao_oficial.py", "Remuneração macro"),
        ("transform/silver_legislativo.py", "Silver legislativo"),
        ("transform/gold_legislativo_merge.py", "Gold legislativo"),
        # DataJud: placeholder explícito
    ]
    skip = {s.strip() for s in env.get("ESCOPO_SKIP", "postgres,neo4j").split(",") if s.strip()}
    for script, label in steps:
        key = script.split("/")[-1].replace(".py", "")
        if key in skip:
            print(f"\n=== skip {label} ===")
            continue
        print(f"\n=== {label} ===", flush=True)
        r = subprocess.run([PY, str(ROOT / script)], cwd=str(PROJECT), env=env)
        if r.returncode != 0 and key in (
            "camara_api",
            "senado_api",
            "silver_politicos",
            "gold_kb",
        ):
            print(f"ABORT {label}", file=sys.stderr)
            return r.returncode
        if r.returncode != 0:
            print(f"aviso: {label} code={r.returncode}", file=sys.stderr)

    print("\n=== DataJud ===\npulado (API instável) — coletor pronto em ingest/datajud_cnj.py")
    print("Escopo federal etapa legislativa/executiva concluída.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
