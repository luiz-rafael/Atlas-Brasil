#!/usr/bin/env python3
"""Probe contencioso / CNO / transacao pages."""
from __future__ import annotations

import re

import httpx

UA = {"User-Agent": "ATLAS-BRASIL-Ingestor/5.1 (+probe)"}
PAGES = [
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/contencioso-administrativo",
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/fiscalizacao",
    "https://www.gov.br/receitafederal/pt-br/assuntos/cadastros-e-registros-especiais/obra",
    "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/editais/transacao-tributaria",
    "https://www.gov.br/receitafederal/dados",
    "https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-de-obras-cno",
    "https://dados.gov.br/dados/conjuntos-dados/contencioso-administrativo-de-primeira-instancia-e-de-segunda-instancia-na-rfb",
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/beneficios-e-renuncias-fiscais/renuncias-fiscais-de-tributos-federais/",
]


def dump(url: str) -> None:
    try:
        r = httpx.get(url, timeout=90, follow_redirects=True, headers=UA)
        print(f"\n=== {url}\nstatus={r.status_code} bytes={len(r.content)} ct={r.headers.get('content-type','')[:50]}")
        text = r.text
        links = re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I)
        keep = []
        for h in links:
            low = h.lower()
            if any(
                x in low
                for x in (
                    ".xlsx",
                    ".csv",
                    ".ods",
                    ".zip",
                    ".xls",
                    "@@download",
                    "/dados/",
                    "resource",
                    "download",
                    "cno",
                    "contencioso",
                    "transacao",
                    "edital",
                )
            ):
                keep.append(h)
        for h in list(dict.fromkeys(keep))[:60]:
            print(" ", h[:220])
        # also look for filenames in text
        for m in re.findall(r"[\w\-./]+\.(?:xlsx|csv|zip|ods|xls)", text, flags=re.I)[:20]:
            print(" FILE", m[:200])
    except Exception as e:
        print("ERR", url, e)


def main() -> None:
    for u in PAGES:
        dump(u)


if __name__ == "__main__":
    main()
