#!/usr/bin/env python3
"""
Ingest INEP — planilhas IDEB 2025 (série histórica 2005–2025).

Fonte oficial:
https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb/resultados/2005-2025

Baixa:
- UF/regiões
- Municípios: anos iniciais, anos finais, ensino médio
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, throttle, utc_now, write_json  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

UA = "ATLAS-BRASIL-Ingestor/5.1 (+pesquisa documental oficial IDEB/INEP)"
BASE = "https://download.inep.gov.br/ideb/resultados"
FILES = [
    "divulgacao_regioes_ufs_ideb_2025.zip",
    "divulgacao_anos_iniciais_municipios_2025.zip",
    "divulgacao_anos_finais_municipios_2025.zip",
    "divulgacao_ensino_medio_municipios_2025.zip",
]


# Prefer curl on Windows: download.inep often drops httpx TLS mid-handshake.
def download(url: str, dest: Path) -> dict:
    throttle()
    print(f"  baixando {url.split('/')[-1]} …", flush=True)
    try:
        r = httpx.get(
            url,
            headers={"User-Agent": UA},
            timeout=600.0,
            follow_redirects=True,
            verify=False,
        )
        r.raise_for_status()
        dest.write_bytes(r.content)
        return {"url": url, "file": dest.name, "bytes": len(r.content), "via": "httpx"}
    except Exception as first:
        import subprocess

        print(f"  httpx falhou ({first}); tentando curl …", flush=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "curl.exe",
            "-L",
            "--retry",
            "5",
            "--retry-delay",
            "2",
            "-A",
            UA,
            "-o",
            str(dest),
            url,
        ]
        subprocess.run(cmd, check=True)
        return {
            "url": url,
            "file": dest.name,
            "bytes": dest.stat().st_size,
            "via": "curl",
        }


def main() -> int:
    run = start_run("inep", "inep.ideb_2025")
    out = bronze_dir("inep")
    meta_files = []
    for name in FILES:
        url = f"{BASE}/{name}"
        dest = out / name
        try:
            meta_files.append(download(url, dest))
        except Exception as e:
            print(f"  FALHA {name}: {e}", file=sys.stderr)
            meta_files.append({"url": url, "error": str(e)})
    write_json(
        out / "ideb_meta.json",
        {
            "em": utc_now(),
            "fonte": "inep_ideb",
            "portal": (
                "https://www.gov.br/inep/pt-br/areas-de-atuacao/"
                "pesquisas-estatisticas-e-indicadores/ideb/resultados/2005-2025"
            ),
            "files": meta_files,
            "ingestion_run_id": run["ingestion_run_id"],
        },
    )
    ok = sum(1 for f in meta_files if "error" not in f)
    mark_ingested(
        "inep",
        run_id=run["ingestion_run_id"],
        counts={"arquivos": ok},
        ok=ok >= 2,
    )
    print(f"OK INEP IDEB: {ok}/{len(FILES)} arquivos → {out}")
    return 0 if ok >= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
