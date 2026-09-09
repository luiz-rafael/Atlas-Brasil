#!/usr/bin/env python3
"""Probe direct downloads for RFB complementary datasets."""
from __future__ import annotations

import httpx

UA = {"User-Agent": "ATLAS-BRASIL-Ingestor/5.1 (+probe)"}
URLS = [
    "https://www.gov.br/receitafederal/dados/agregado-2015-a-2024-irpj-csll-pis-imp-cofins-imp-ipi-imp-e-ii-5.xlsx/@@download/file",
    "https://www.gov.br/receitafederal/dados/agregado-2015-a-2024-irpj-csll-pis-imp-cofins-imp-ipi-imp-e-ii-5.xlsx",
    "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/estudos/carga-tributaria/tabelas-carga-tributaria-no-brasil-2024/@@download/file",
    "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/estudos/carga-tributaria/tabelas-carga-tributaria-no-brasil-2023/@@download/file",
    "https://portaldatransparencia.gov.br/download-de-dados/renuncias/202312",
    "https://portaldatransparencia.gov.br/download-de-dados/renuncias/202406",
    # CKAN dados.gov often needs API
    "https://dados.gov.br/api/3/action/package_show?id=contencioso-administrativo-de-primeira-instancia-e-de-segunda-instancia-na-rfb",
    "https://dados.gov.br/api/3/action/package_show?id=cadastro-nacional-de-obras-cno",
]

def main() -> None:
    for u in URLS:
        try:
            r = httpx.get(u, timeout=120.0, follow_redirects=True, verify=False, headers=UA)
            ct = r.headers.get("content-type", "")
            print(f"{r.status_code} {len(r.content):10d} {ct[:40]:40s} {u[:100]}")
            if "json" in ct or u.endswith("package_show") or "api/3" in u:
                print(" ", r.text[:400].replace("\n", " "))
        except Exception as e:
            print(f"ERR {e} {u[:80]}")

if __name__ == "__main__":
    main()
