#!/usr/bin/env python3
"""
Ingest SICONFI — slice P0 finanças públicas.

Fontes (API Tesouro):
  DCA  → receitas, despesas, pessoal, investimentos, saúde, educação, transferências
  RGF  → Receita Corrente Líquida (RCL) — UFs (3º quadrimestre)

Cobertura inicial:
  UF  2014–2024 (DCA + RCL)
  Mun ano mais recente completo (default 2023) — DCA

Bronze: extratos slim (não grava DCA bruto completo).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, throttle, utc_now, write_json  # noqa: E402
from pipelines.registry import dataset_id_from_env, mark_ingested, start_run  # noqa: E402

BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
UA = "ATLAS-BRASIL-Ingestor/5.1 (+pesquisa documental oficial SICONFI)"
YEARS_UF = list(range(2014, 2025))  # 2014–2024
MUN_YEAR = int(os.getenv("ATLAS_SICONFI_MUN_YEAR", "2023"))
_raw_mun_years = os.getenv("ATLAS_SICONFI_MUN_YEARS", "").strip()
MUN_YEARS = (
    [int(y) for y in _raw_mun_years.split(",") if y.strip().isdigit()]
    if _raw_mun_years
    else [MUN_YEAR]
)
# opcional: ATLAS_SICONFI_UF_ONLY=1 pula municípios
UF_ONLY = os.getenv("ATLAS_SICONFI_UF_ONLY", "").strip() in ("1", "true", "yes")
# opcional: ATLAS_SICONFI_SKIP_UF=1 só municípios (UF já coletada)
SKIP_UF = os.getenv("ATLAS_SICONFI_SKIP_UF", "").strip() in ("1", "true", "yes")

# (indicator_key, matcher)
# matcher: (anexo_substr, cod_conta|None, conta_exact|None, coluna_exact)


def latest_ibge_json(name: str):
    base = ROOT / "data" / "lake" / "bronze" / "ibge"
    if not base.exists():
        return None
    for day in sorted(base.iterdir(), reverse=True):
        p = day / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def api_get(path: str, params: dict) -> list[dict]:
    url = f"{BASE}/{path.lstrip('/')}"
    out: list[dict] = []
    offset = 0
    while True:
        throttle()
        q = {**params, "limit": 5000, "offset": offset}
        r = httpx.get(
            url,
            params=q,
            headers={"User-Agent": UA},
            timeout=180.0,
            follow_redirects=True,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("items") or []
        out.extend(items)
        if not data.get("hasMore"):
            break
        offset += len(items)
        if not items:
            break
    return out


def pick_valor(
    items: list[dict],
    *,
    anexo_contains: str,
    coluna: str,
    cod_conta: str | None = None,
    conta_exact: str | None = None,
    conta_startswith: str | None = None,
) -> float | None:
    for it in items:
        anexo = str(it.get("anexo") or "")
        if anexo_contains not in anexo:
            continue
        if str(it.get("coluna") or "") != coluna:
            continue
        if cod_conta is not None and str(it.get("cod_conta") or "") != cod_conta:
            continue
        conta = str(it.get("conta") or "").strip()
        if conta_exact is not None and conta != conta_exact:
            continue
        if conta_startswith is not None and not conta.startswith(conta_startswith):
            continue
        try:
            return float(it.get("valor"))
        except (TypeError, ValueError):
            return None
    return None


def extract_dca_metrics(items: list[dict]) -> dict[str, float]:
    """Extrai métricas P0 do DCA (valores nominais em R$)."""
    m: dict[str, float] = {}
    v = pick_valor(
        items,
        anexo_contains="Anexo I-C",
        coluna="Receitas Brutas Realizadas",
        cod_conta="ReceitasExcetoIntraOrcamentarias",
    )
    if v is not None:
        m["receita_bruta"] = v

    v = pick_valor(
        items,
        anexo_contains="Anexo I-C",
        coluna="Receitas Brutas Realizadas",
        cod_conta="RO1.7.0.0.00.0.0",
    )
    if v is not None:
        m["transferencias_correntes"] = v

    v = pick_valor(
        items,
        anexo_contains="Anexo I-D",
        coluna="Despesas Empenhadas",
        cod_conta="TotalDespesas",
        conta_exact="Total Geral da Despesa",
    )
    if v is not None:
        m["despesa_total"] = v

    v = pick_valor(
        items,
        anexo_contains="Anexo I-D",
        coluna="Despesas Liquidadas",
        cod_conta="TotalDespesas",
        conta_exact="Total Geral da Despesa",
    )
    if v is not None:
        m["despesa_liquidada"] = v

    v = pick_valor(
        items,
        anexo_contains="Anexo I-D",
        coluna="Despesas Pagas",
        cod_conta="TotalDespesas",
        conta_exact="Total Geral da Despesa",
    )
    if v is not None:
        m["despesa_paga"] = v

    v = pick_valor(
        items,
        anexo_contains="Anexo I-D",
        coluna="Despesas Empenhadas",
        cod_conta="DO3.1.00.00.00.00",
    )
    if v is not None:
        m["despesa_pessoal"] = v

    v = pick_valor(
        items,
        anexo_contains="Anexo I-D",
        coluna="Despesas Empenhadas",
        cod_conta="DO4.4.00.00.00.00",
    )
    if v is not None:
        m["despesa_investimentos"] = v

    # Anexo I-E: função — cod_conta genérico TotalDespesas + rótulo da conta
    v = pick_valor(
        items,
        anexo_contains="Anexo I-E",
        coluna="Despesas Empenhadas",
        conta_exact="10 - Saúde",
    )
    if v is not None:
        m["despesa_saude"] = v

    v = pick_valor(
        items,
        anexo_contains="Anexo I-E",
        coluna="Despesas Empenhadas",
        conta_exact="12 - Educação",
    )
    if v is not None:
        m["despesa_educacao"] = v

    return m


def extract_rcl(items: list[dict]) -> float | None:
    """RCL do RGF: preferir coluna Valor / VALOR do rótulo canônico."""
    prefer_cols = {"Valor", "VALOR"}
    candidates: list[tuple[int, float]] = []
    for it in items:
        conta = str(it.get("conta") or "")
        if "RECEITA CORRENTE LIQUIDA - RCL (IV)" not in conta and "RECEITA CORRENTE LÍQUIDA - RCL (IV)" not in conta:
            # aceitar variação sem acento já coberta; também forma com LÍQUIDA
            if "RECEITA CORRENTE L" not in conta or "RCL (IV)" not in conta:
                continue
        col = str(it.get("coluna") or "")
        try:
            val = float(it.get("valor"))
        except (TypeError, ValueError):
            continue
        rank = 0 if col in prefer_cols else 1
        if "Até o 3" in col:
            rank = 0
        candidates.append((rank, val))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def load_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            done.add(f"{row.get('cod_ibge')}|{row.get('exercicio')}|{row.get('fonte')}")
        except json.JSONDecodeError:
            continue
    return done


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    run = start_run("siconfi", "siconfi.dca_rgf_p0")
    out = bronze_dir("siconfi")
    estados = latest_ibge_json("estados.json") or []
    municipios = latest_ibge_json("municipios.json") or []
    if not estados:
        print("bronze IBGE estados ausente — rode ibge_territorios.py", file=sys.stderr)
        return 1

    dca_path = out / "dca_extract.jsonl"
    rcl_path = out / "rgf_rcl_extract.jsonl"
    done = load_done(dca_path) | load_done(rcl_path)

    ok = 0
    fail = 0

    # —— UFs DCA ——
    if not SKIP_UF:
      for est in sorted(estados, key=lambda e: e["id"]):
        cod = int(est["id"])
        uf = est["sigla"]
        for year in YEARS_UF:
            key = f"{cod}|{year}|dca"
            if key in done:
                continue
            try:
                items = api_get("dca", {"an_exercicio": year, "id_ente": cod})
                metrics = extract_dca_metrics(items)
                row = {
                    "fonte": "dca",
                    "cod_ibge": cod,
                    "uf": uf,
                    "nivel": "STATE",
                    "exercicio": year,
                    "metrics": metrics,
                    "n_items": len(items),
                    "retrieved_at": utc_now(),
                }
                append_jsonl(dca_path, row)
                done.add(key)
                ok += 1
                print(f"  DCA UF {uf} {year}: {len(metrics)} métricas", flush=True)
            except Exception as e:
                fail += 1
                print(f"  FALHA DCA UF {uf} {year}: {e}", file=sys.stderr)
                append_jsonl(
                    out / "errors.jsonl",
                    {"fonte": "dca", "cod_ibge": cod, "exercicio": year, "error": str(e)},
                )

    # —— UFs RCL (RGF 3º Q) ——
    if not SKIP_UF:
      for est in sorted(estados, key=lambda e: e["id"]):
        cod = int(est["id"])
        uf = est["sigla"]
        esfera = "D" if uf == "DF" else "E"
        for year in YEARS_UF:
            key = f"{cod}|{year}|rgf_rcl"
            if key in done:
                continue
            try:
                items = api_get(
                    "rgf",
                    {
                        "an_exercicio": year,
                        "id_ente": cod,
                        "in_periodicidade": "Q",
                        "nr_periodo": 3,
                        "co_tipo_demonstrativo": "RGF",
                        "co_esfera": esfera,
                        "co_poder": "E",
                    },
                )
                rcl = extract_rcl(items)
                row = {
                    "fonte": "rgf_rcl",
                    "cod_ibge": cod,
                    "uf": uf,
                    "nivel": "STATE",
                    "exercicio": year,
                    "metrics": {"rcl": rcl} if rcl is not None else {},
                    "n_items": len(items),
                    "retrieved_at": utc_now(),
                }
                append_jsonl(rcl_path, row)
                done.add(key)
                ok += 1
                print(f"  RCL UF {uf} {year}: {rcl}", flush=True)
            except Exception as e:
                fail += 1
                print(f"  FALHA RCL UF {uf} {year}: {e}", file=sys.stderr)

    # —— Municípios DCA (um ou mais anos) ——
    mun_ok = 0
    if not UF_ONLY and municipios:
        for mun_year in MUN_YEARS:
            print(f"  municípios DCA {mun_year} ({len(municipios)} entes) …", flush=True)
            for i, mun in enumerate(municipios, 1):
                cod = int(mun["id"])
                key = f"{cod}|{mun_year}|dca"
                if key in done:
                    continue
                try:
                    items = api_get("dca", {"an_exercicio": mun_year, "id_ente": cod})
                    metrics = extract_dca_metrics(items)
                    micro = mun.get("microrregiao") or {}
                    meso = micro.get("mesorregiao") or {}
                    uf_obj = meso.get("UF") or {}
                    if not uf_obj:
                        ri = mun.get("regiao-imediata") or {}
                        rint = ri.get("regiao-intermediaria") or {}
                        uf_obj = rint.get("UF") or {}
                    uf = (uf_obj.get("sigla") or "").upper()
                    row = {
                        "fonte": "dca",
                        "cod_ibge": cod,
                        "uf": uf or None,
                        "nivel": "MUNICIPALITY",
                        "exercicio": mun_year,
                        "nome": mun.get("nome"),
                        "metrics": metrics,
                        "n_items": len(items),
                        "retrieved_at": utc_now(),
                    }
                    append_jsonl(dca_path, row)
                    done.add(key)
                    ok += 1
                    mun_ok += 1
                    if i % 100 == 0 or mun_ok % 50 == 0:
                        print(f"  mun {mun_year} {i}/{len(municipios)} · novos={mun_ok}", flush=True)
                except Exception as e:
                    fail += 1
                    if fail <= 20 or fail % 50 == 0:
                        print(f"  FALHA mun {cod} {mun_year}: {e}", file=sys.stderr)

    meta = {
        "em": utc_now(),
        "fonte": "siconfi",
        "api": BASE,
        "years_uf": YEARS_UF,
        "mun_year": None if UF_ONLY else MUN_YEARS,
        "ok": ok,
        "fail": fail,
        "mun_ok": mun_ok,
        "dca_file": str(dca_path.name),
        "rcl_file": str(rcl_path.name),
        "ingestion_run_id": run["ingestion_run_id"],
        "day": day_stamp(),
    }
    write_json(out / "siconfi_meta.json", meta)
    mark_ingested(
        "siconfi",
        run_id=run["ingestion_run_id"],
        counts={"ok": ok, "fail": fail, "mun": mun_ok},
        ok=ok > 0,
        dataset_id=dataset_id_from_env("siconfi_dca"),
    )
    print(f"OK SICONFI: ok={ok} fail={fail} mun={mun_ok} → {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
