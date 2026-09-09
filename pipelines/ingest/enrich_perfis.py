#!/usr/bin/env python3
"""
Enriquece perfis de politicos com dados publicos detalhados:
- Camara: detalhe + foto + despesas (resumo anual)
- Senado: detalhe + foto
- Presidencia/ministros: lista publica gov.br (quando disponivel)

Grava bronze/perfis_enriquecidos/ e atualiza gold (campo perfil).
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import (  # noqa: E402
    LAKE,
    append_event,
    bronze_dir,
    http_get,
    sha1_bytes,
    utc_now,
    write_json,
    write_jsonl,
    write_manifest,
    write_raw_record,
)
from pipelines.registry import mark_ingested, start_run  # noqa: E402

CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
HEADERS_JSON = {"Accept": "application/json"}
GOLD = ROOT / "data" / "atlas-brasil-kb-gold.json"
ACTIVE = ROOT / "data" / "atlas-brasil-kb-active.json"
V2 = ROOT / "data" / "atlas-brasil-kb-v2.json"
YEAR = int(os.getenv("PERFIL_DESPESA_ANO", str(datetime.now().year - 1)))


def despesa_anos() -> list[int]:
    raw = os.getenv("PERFIL_DESPESA_ANOS", "").strip()
    if raw:
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]
    # padrão: ano anterior + corrente (cota pode atrasar no portal)
    y = datetime.now().year
    return [y - 1, y]


def fetch_json(url: str, timeout: float = 45.0) -> dict | list | None:
    try:
        r = http_get(url, headers=HEADERS_JSON, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        print(f"  fail {url[:80]}: {e}", file=sys.stderr)
        return None


def camara_detalhe(dep_id: str) -> dict:
    data = fetch_json(f"{CAMARA}/deputados/{dep_id}") or {}
    dados = data.get("dados") if isinstance(data, dict) else None
    return dados if isinstance(dados, dict) else {}


def camara_despesas(dep_id: str, ano: int) -> dict:
    """Soma despesas por tipo + top fornecedores (CNPJ/nome) — paginado."""
    total = 0.0
    por_tipo: dict[str, float] = defaultdict(float)
    por_forn: dict[str, dict] = {}
    n = 0
    max_pages = int(os.getenv("DESPESA_MAX_PAGES", "5"))
    url = (
        f"{CAMARA}/deputados/{dep_id}/despesas"
        f"?ano={ano}&itens=100&ordem=ASC&ordenarPor=dataDocumento"
    )
    pages = 0
    while url and pages < max_pages:
        pages += 1
        data = fetch_json(url, timeout=30.0)
        if not isinstance(data, dict):
            break
        for row in data.get("dados") or []:
            v = float(row.get("valorLiquido") or row.get("valorDocumento") or 0)
            total += v
            tipo = row.get("tipoDespesa") or "Outros"
            por_tipo[tipo] += v
            n += 1
            cnpj = re.sub(r"\D", "", str(row.get("cnpjCpfFornecedor") or ""))
            nome_f = (row.get("nomeFornecedor") or "").strip()
            if len(cnpj) >= 11 or nome_f:
                key = cnpj if len(cnpj) >= 11 else f"nome:{nome_f.upper()}"
                slot = por_forn.setdefault(
                    key,
                    {
                        "cnpj": cnpj if len(cnpj) == 14 else (cnpj if len(cnpj) == 11 else None),
                        "nome": nome_f or None,
                        "valor": 0.0,
                        "qtd": 0,
                    },
                )
                if nome_f and not slot.get("nome"):
                    slot["nome"] = nome_f
                slot["valor"] += v
                slot["qtd"] += 1
        next_u = None
        for link in data.get("links") or []:
            if link.get("rel") == "next":
                next_u = link.get("href")
                break
        url = next_u
    top = sorted(por_tipo.items(), key=lambda x: -x[1])[:8]
    top_forn = sorted(por_forn.values(), key=lambda x: -x["valor"])[:12]
    for f in top_forn:
        f["valor"] = round(f["valor"], 2)
    return {
        "ano": ano,
        "total": round(total, 2),
        "qtd_lancamentos": n,
        "por_tipo": [{"tipo": t, "valor": round(v, 2)} for t, v in top],
        "fornecedores": top_forn,
        "fonte_url": f"{CAMARA}/deputados/{dep_id}/despesas?ano={ano}",
        "completo": pages < max_pages or not url,
    }


def senado_detalhe(code: str) -> dict:
    data = fetch_json(f"{SENADO}/senador/{code}.json")
    return data if isinstance(data, dict) else {}


def extract_senado_perfil(raw: dict) -> dict:
    """Normaliza bloco IdentificacaoParlamentar / DadosBasicos do Senado."""
    out: dict = {}

    def walk(o):
        if isinstance(o, dict):
            if "IdentificacaoParlamentar" in o and isinstance(o["IdentificacaoParlamentar"], dict):
                out["ident"] = o["IdentificacaoParlamentar"]
            if "DadosBasicosParlamentar" in o and isinstance(o["DadosBasicosParlamentar"], dict):
                out["basicos"] = o["DadosBasicosParlamentar"]
            if "HistoricoAcademico" in o:
                out["academico"] = o["HistoricoAcademico"]
            if "Profissoes" in o:
                out["profissoes"] = o["Profissoes"]
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for i in o:
                walk(i)

    walk(raw)
    ident = out.get("ident") or {}
    bas = out.get("basicos") or {}
    return {
        "foto_url": ident.get("UrlFotoParlamentar") or bas.get("UrlFotoParlamentar"),
        "email": ident.get("EmailParlamentar"),
        "nome": ident.get("NomeCompletoParlamentar") or ident.get("NomeParlamentar"),
        "nome_parlamentar": ident.get("NomeParlamentar"),
        "partido": ident.get("SiglaPartidoParlamentar"),
        "uf": ident.get("UfParlamentar"),
        "pagina": ident.get("UrlPaginaParlamentar"),
        "sexo": bas.get("SexoParlamentar") or ident.get("SexoParlamentar"),
        "data_nascimento": bas.get("DataNascimento"),
        "naturalidade": bas.get("Naturalidade"),
        "uf_naturalidade": bas.get("UfNaturalidade"),
        "gabinete": ident.get("Telefone") or bas.get("TelefoneParlamentar"),
        "raw_keys": list(out.keys()),
    }


def extract_camara_perfil(det: dict) -> dict:
    ultimo = det.get("ultimoStatus") or {}
    gab = ultimo.get("gabinete") or {}
    return {
        "foto_url": ultimo.get("urlFoto") or det.get("urlFoto"),
        "email": ultimo.get("email") or gab.get("email") or det.get("email"),
        "nome": det.get("nomeCivil") or ultimo.get("nome"),
        "nome_eleitoral": ultimo.get("nomeEleitoral") or ultimo.get("nome"),
        "partido": ultimo.get("siglaPartido"),
        "uf": ultimo.get("siglaUf"),
        "situacao": ultimo.get("situacao") or ultimo.get("condicaoEleitoral"),
        "legislatura": ultimo.get("idLegislatura"),
        "data_nascimento": det.get("dataNascimento"),
        "municipio_nascimento": det.get("municipioNascimento"),
        "uf_nascimento": det.get("ufNascimento"),
        "escolaridade": det.get("escolaridade"),
        "sexo": det.get("sexo"),
        "cpf_mascarado": None,  # API pode trazer; nao persistir completo
        "rede_social": det.get("redeSocial") or [],
        "gabinete": {
            "nome": gab.get("nome"),
            "predio": gab.get("predio"),
            "sala": gab.get("sala"),
            "telefone": gab.get("telefone"),
            "email": gab.get("email"),
        },
        "uri": det.get("uri") or ultimo.get("uri"),
        "url_website": det.get("urlWebsite"),
    }


def fetch_presidencia_ministros() -> list[dict]:
    """Tenta lista publica de ministros (HTML gov.br) — best effort."""
    urls = [
        "https://www.gov.br/planalto/pt-br/conheca-a-presidencia/ministros",
        "https://www.gov.br/planalto/pt-br/acesso-a-informacao/institucional/ministerios",
    ]
    found = []
    for url in urls:
        try:
            r = http_get(url, timeout=40.0)
            if r.status_code != 200:
                continue
            html = r.text
            # capturar links/nomes grosseiros
            for m in re.finditer(
                r'href="([^"]+)"[^>]*>([^<]{5,80})</a>',
                html,
                flags=re.I,
            ):
                href, text = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
                if "ministro" in text.lower() or "ministra" in text.lower():
                    found.append({"titulo": text, "url": href, "fonte": url})
            # fotos
            for m in re.finditer(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"', html, flags=re.I):
                src, alt = m.group(1), m.group(2)
                if alt and len(alt) > 3:
                    found.append({"nome": alt, "foto_url": src, "fonte": url, "tipo": "img"})
            if found:
                break
        except Exception as e:
            print(f"presidencia fail {url}: {e}", file=sys.stderr)
    return found


def load_gold() -> dict:
    for p in (GOLD, ACTIVE, V2):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {"entidades": [], "relacoes": [], "documentos": [], "meta": {}}


def main() -> int:
    run = start_run("perfis_enriquecidos", "perfis.enriquecidos")
    out = bronze_dir("perfis_enriquecidos")
    kb = load_gold()
    ents = [e for e in kb.get("entidades") or [] if e.get("tipo") == "pessoa"]

    limit = int(os.getenv("PERFIL_LIMIT", "0") or "0")
    only_ids = {
        x.strip()
        for x in os.getenv("PERFIL_IDS", "").split(",")
        if x.strip()
    }
    force_ids = {
        x.strip()
        for x in os.getenv("PERFIL_FORCE_IDS", "").split(",")
        if x.strip()
    }
    # 0 = todos com id cam/sen; N = primeiros N
    targets = [e for e in ents if e["id"].startswith(("p_cam_", "p_sen_"))]
    if only_ids:
        targets = [e for e in targets if e["id"] in only_ids]
    # prioriza quem está no poder (guia Dinheiro precisa desses primeiro)
    targets.sort(key=lambda e: (0 if e.get("no_poder_2026") else 1, e.get("nome") or ""))
    if limit > 0:
        targets = targets[:limit]

    only_despesas = os.getenv("PERFIL_DESPESAS", "1") == "1"
    # checkpoint resume
    ck_path = out / "perfis.jsonl"
    done_ids: set[str] = set()
    perfis: list[dict] = []
    if ck_path.exists() and os.getenv("PERFIL_RESUME", "1") == "1":
        for line in ck_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                eid = row.get("entity_id")
                if eid:
                    done_ids.add(eid)
                    perfis.append(row)
            except json.JSONDecodeError:
                pass
        print(f"resume: {len(done_ids)} ja salvos")

    # reprocessa IDs forçados (ex.: despesas 2025 vazias)
    if force_ids:
        done_ids -= force_ids
        print(f"force refresh: {len(force_ids)} ids")

    # reabre quem ficou com cota zerada (ex.: coleta só no ano corrente vazio)
    if os.getenv("PERFIL_REFRESH_EMPTY_DESPESAS", "0") == "1":
        empty = {
            p["entity_id"]
            for p in perfis
            if p.get("entity_id", "").startswith("p_cam_")
            and not ((p.get("despesas") or {}).get("total") or 0)
        }
        if empty:
            done_ids -= empty
            print(f"refresh despesas vazias: {len(empty)} deputados (overwrite no merge)")

    targets = [e for e in targets if e["id"] not in done_ids]
    anos = despesa_anos()
    print(
        f"enriquecendo {len(targets)} perfis restantes "
        f"(despesas={'sim' if only_despesas else 'nao'} anos={anos})"
    )

    for i, e in enumerate(targets, 1):
        perfil: dict = {
            "entity_id": e["id"],
            "nome": e.get("nome"),
            "fetched_at": utc_now(),
            "fontes": [],
        }
        if e["id"].startswith("p_cam_"):
            dep_id = e["id"].replace("p_cam_", "", 1)
            det = camara_detalhe(dep_id)
            if det:
                perfil["camara"] = extract_camara_perfil(det)
                perfil["foto_url"] = perfil["camara"].get("foto_url")
                perfil["fontes"].append(f"{CAMARA}/deputados/{dep_id}")
            if only_despesas:
                por_ano = []
                for ano in anos:
                    d = camara_despesas(dep_id, ano)
                    por_ano.append(d)
                    perfil["fontes"].append(d["fonte_url"])
                perfil["despesas_por_ano"] = por_ano
                # resumo principal = ano mais recente com lançamentos, senão o último pedido
                escolhido = next(
                    (d for d in reversed(por_ano) if d.get("qtd_lancamentos")),
                    por_ano[-1] if por_ano else None,
                )
                perfil["despesas"] = escolhido
        elif e["id"].startswith("p_sen_"):
            code = e["id"].replace("p_sen_", "", 1)
            raw = senado_detalhe(code)
            if raw:
                perfil["senado"] = extract_senado_perfil(raw)
                perfil["foto_url"] = perfil["senado"].get("foto_url")
                perfil["fontes"].append(f"{SENADO}/senador/{code}.json")
                perfil["senado_raw_ref"] = f"senador/{code}.json"

        perfis.append(perfil)
        # checkpoint incremental
        with ck_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(perfil, ensure_ascii=False) + "\n")
        if i % 25 == 0:
            print(f"  {i}/{len(targets)} (total salvos {len(perfis)})", flush=True)

    # reescrever jsonl limpo (dedupe)
    by_eid = {p["entity_id"]: p for p in perfis}
    perfis = list(by_eid.values())
    write_jsonl(ck_path, perfis)

    # Presidencia (lista auxiliar — nao merge automatico sem ER)
    ministros = fetch_presidencia_ministros()
    write_json(out / "presidencia_ministros.json", {"items": ministros, "fetched_at": utc_now()})
    write_jsonl(out / "perfis.jsonl", perfis)

    files = []
    for name in ("perfis.jsonl", "presidencia_ministros.json"):
        p = out / name
        raw = p.read_bytes()
        files.append({"file": name, "bytes": len(raw), "sha1": sha1_bytes(raw)})
    write_manifest(
        out,
        "perfis_enriquecidos",
        files,
        extra={
            "count": len(perfis),
            "ano_despesa": YEAR,
            "ingestion_run_id": run["ingestion_run_id"],
        },
    )
    write_raw_record(
        source_id="perfis_enriquecidos",
        ingestion_run_id=run["ingestion_run_id"],
        connector_version=run["connector_version"],
        payload={"count": len(perfis), "ano_despesa": YEAR, "entity_ids": [p["entity_id"] for p in perfis[:500]]},
        filename="perfis_summary.json",
        dataset_id="perfis.enriquecidos",
    )
    append_event("document.discovered", {"source": "perfis_enriquecidos", "path": str(out), "count": len(perfis)})

    skip_gold = os.getenv("PERFIL_SKIP_GOLD", "0") == "1"
    # Recarrega gold antes do patch (não sobrescreve onda F1 correndo em paralelo).
    kb = load_gold()
    by_id = {p["entity_id"]: p for p in perfis}
    fotos = 0
    for e in kb.get("entidades") or []:
        p = by_id.get(e["id"])
        if not p:
            continue
        cam = p.get("camara") or {}
        sen = p.get("senado") or {}
        photo = p.get("foto_url") or cam.get("foto_url") or sen.get("foto_url")
        if photo:
            e["foto_url"] = photo
            fotos += 1
        e["email"] = cam.get("email") or sen.get("email") or e.get("email")
        e["nome_civil"] = cam.get("nome") or sen.get("nome") or e.get("nome")
        e["data_nascimento"] = cam.get("data_nascimento") or sen.get("data_nascimento")
        e["escolaridade"] = cam.get("escolaridade")
        e["municipio_nascimento"] = cam.get("municipio_nascimento") or sen.get("naturalidade")
        e["uf_nascimento"] = cam.get("uf_nascimento") or sen.get("uf_naturalidade")
        e["redes_sociais"] = cam.get("rede_social") or []
        e["gabinete"] = cam.get("gabinete") or (
            {"telefone": sen.get("gabinete")} if sen.get("gabinete") else None
        )
        e["pagina_oficial"] = cam.get("uri") or sen.get("pagina")
        partido = (cam.get("partido") or sen.get("partido") or "").strip() or None
        if partido:
            e["partido"] = partido.upper() if len(partido) <= 12 else partido
        uf = cam.get("uf") or sen.get("uf")
        if uf:
            e["uf"] = str(uf).upper()[:2]
        if p.get("despesas"):
            e["despesas_resumo"] = p["despesas"]
        if p.get("despesas_por_ano"):
            e["despesas_por_ano"] = p["despesas_por_ano"]
        e["perfil_fontes"] = p.get("fontes") or []
        e["perfil_atualizado_em"] = utc_now()
        aliases = list(e.get("aliases") or [])
        for a in (cam.get("nome_eleitoral"), sen.get("nome_parlamentar"), cam.get("nome")):
            if a and a not in aliases and a != e.get("nome"):
                aliases.append(a)
        e["aliases"] = aliases[:16]
        tags = [t for t in (e.get("tags") or []) if not str(t).startswith("partido:")]
        if "perfil_enriquecido" not in tags:
            tags.append("perfil_enriquecido")
        if photo and "tem_foto" not in tags:
            tags.append("tem_foto")
        if partido:
            tags.append(f"partido:{(e.get('partido') or partido)}")
        e["tags"] = tags

    mark_ingested(
        "perfis_enriquecidos",
        run_id=run["ingestion_run_id"],
        counts={"perfis": len(perfis), "fotos": fotos},
    )

    kb.setdefault("meta", {})["perfil_enrich"] = {
        "em": utc_now(),
        "perfis": len(perfis),
        "com_foto": fotos,
        "ano_despesa": YEAR,
    }
    if skip_gold:
        print(f"OK perfis={len(perfis)} fotos={fotos} (PERFIL_SKIP_GOLD=1)")
        return 0

    for path in (GOLD, ROOT / "data" / "lake" / "gold" / "kb.json"):
        write_json(path, kb)
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        write_json(ACTIVE, kb)
        write_json(V2, kb)

    print(f"OK perfis={len(perfis)} fotos={fotos} -> gold patch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
