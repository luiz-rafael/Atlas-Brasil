#!/usr/bin/env python3
"""Probe RFB subsection pages for downloadable files."""
from __future__ import annotations

import re

import httpx

UA = {"User-Agent": "ATLAS-BRASIL-Ingestor/5.1 (+probe)"}
pages = [
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/beneficios-e-renuncias-fiscais/renuncias-fiscais-de-tributos-federais",
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/beneficios-e-renuncias-fiscais/empresas-habilitadas-em-regimes-tributarios-e-aduaneiros-especiais",
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/beneficios-e-renuncias-fiscais/entidades-imunes-e-isentas",
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/carga-tributaria/conjunto-de-dados-da-carga-tributaria",
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos",
    "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/editais/transacao-tributaria",
]


def main() -> None:
    hub = "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos"
    r = httpx.get(hub, timeout=90, follow_redirects=True, headers=UA)
    print("hub", r.status_code)
    links = re.findall(r'href=["\']([^"\']+)["\']', r.text, flags=re.I)
    for h in links:
        low = h.lower()
        if any(
            k in low
            for k in (
                "contencioso",
                "transacao",
                "cno",
                "obra",
                "carga",
                "beneficio",
                "renuncia",
                "fiscalizacao",
                "credito",
            )
        ):
            print("HUB", h[:200])

    for u in pages:
        try:
            rr = httpx.get(u, timeout=90, follow_redirects=True, headers=UA)
            print(f"\n=== {u} {rr.status_code} {len(rr.content)}")
            links = re.findall(r'href=["\']([^"\']+)["\']', rr.text, flags=re.I)
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
                    )
                ):
                    keep.append(h)
            for h in list(dict.fromkeys(keep))[:50]:
                print(" ", h[:240])
        except Exception as e:
            print("ERR", u, e)


if __name__ == "__main__":
    main()
