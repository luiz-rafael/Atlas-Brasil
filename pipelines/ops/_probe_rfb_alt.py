#!/usr/bin/env python3
from __future__ import annotations

import re

import httpx

UA = {"User-Agent": "ATLAS-BRASIL-Ingestor/5.1 (+probe)"}
URLS = [
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/contencioso-administrativo/contencioso-administrativo",
    "https://www.gov.br/receitafederal/dados/Anexo_II_Portaria_319_2023_2021-2022/@@download/file",
    "https://www.gov.br/receitafederal/dados/Anexo_I_Portaria_RFB_319_2023/@@download/file",
    "https://dadosabertos.rfb.gov.br/",
    "https://arquivos.receitafederal.gov.br/dados/cno/",
    "http://www.receita.fazenda.gov.br/publico/programaBrasil/CNO/CNO.zip",
    "https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/cno",
    "https://www.gov.br/fazenda/pt-br/acesso-a-informacao/dados-abertos",
]


def main() -> None:
    for u in URLS:
        try:
            r = httpx.get(u, timeout=60, follow_redirects=True, headers=UA)
            ct = r.headers.get("content-type", "")
            print(f"{r.status_code} {len(r.content):10d} {ct[:45]:45s} {u[:110]}")
            if "html" in ct.lower() and r.status_code == 200:
                links = re.findall(r'href=["\']([^"\']+)["\']', r.text, flags=re.I)
                keep = [
                    h
                    for h in links
                    if any(
                        x in h.lower()
                        for x in (
                            ".xlsx",
                            ".csv",
                            ".zip",
                            ".ods",
                            "@@download",
                            "cno",
                            "contencioso",
                            "/dados/",
                        )
                    )
                ]
                for h in list(dict.fromkeys(keep))[:25]:
                    print("  ", h[:200])
        except Exception as e:
            print(f"ERR {e} {u[:80]}")


if __name__ == "__main__":
    main()
