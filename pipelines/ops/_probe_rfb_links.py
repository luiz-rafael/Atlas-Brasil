#!/usr/bin/env python3
"""Probe RFB open-data download links."""
from __future__ import annotations

import re
import httpx

UA = "ATLAS-BRASIL-Ingestor/5.1 (+probe RFB)"
PAGES = [
    "https://www.gov.br/receitafederal/dados",
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/beneficios-e-renuncias-fiscais",
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/carga-tributaria",
    "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/estudos/carga-tributaria",
    "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/estudos/carga-tributaria/carga-tributaria-no-brasil-2024",
    "https://portaldatransparencia.gov.br/download-de-dados/renuncias",
]

def main() -> None:
    for u in PAGES:
        try:
            r = httpx.get(u, timeout=90.0, follow_redirects=True, verify=False, headers={"User-Agent": UA})
            print(f"\n=== {u} status={r.status_code} bytes={len(r.content)}")
            text = r.text
            links = re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I)
            keep = []
            for h in links:
                low = h.lower()
                if any(x in low for x in (".xlsx", ".csv", ".ods", ".zip", "download", "tabelas", "renuncia", "carga", "contencioso", "cno", "transac")):
                    keep.append(h)
            for h in list(dict.fromkeys(keep))[:40]:
                print(" ", h[:200])
        except Exception as e:
            print(f"\n=== {u} ERR {e}")

if __name__ == "__main__":
    main()
