#!/usr/bin/env python3
"""
Ingest RAIS — estoque de vínculos/empregos formais por UF (slice P1).

Preferência:
  1) ATLAS_RAIS_FILE (csv/xlsx local)
  2) FTP ftp.mtps.gov.br /pdet/rais/{ano}/nacionais/4-resultadosdesagregados.xls
     (agregados oficiais 2007–2017; microdados RAIS_VINC são pesados demais para P1)
  3) Mensagem clara se remoto indisponível

Bronze: rais_estoque_extract.jsonl — year, uf, vinculos/empregos
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
from ftplib import FTP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

FTP_HOST = "ftp.mtps.gov.br"
FTP_RAIS = "/pdet/rais"

UF_NAME_TO_SIGLA = {
    "rondônia": "RO",
    "rondonia": "RO",
    "acre": "AC",
    "amazonas": "AM",
    "roraima": "RR",
    "pará": "PA",
    "para": "PA",
    "amapá": "AP",
    "amapa": "AP",
    "tocantins": "TO",
    "maranhão": "MA",
    "maranhao": "MA",
    "piauí": "PI",
    "piaui": "PI",
    "ceará": "CE",
    "ceara": "CE",
    "rio grande do norte": "RN",
    "paraíba": "PB",
    "paraiba": "PB",
    "pernambuco": "PE",
    "alagoas": "AL",
    "sergipe": "SE",
    "bahia": "BA",
    "minas gerais": "MG",
    "espírito santo": "ES",
    "espirito santo": "ES",
    "rio de janeiro": "RJ",
    "são paulo": "SP",
    "sao paulo": "SP",
    "paraná": "PR",
    "parana": "PR",
    "santa catarina": "SC",
    "rio grande do sul": "RS",
    "mato grosso do sul": "MS",
    "mato grosso": "MT",
    "goiás": "GO",
    "goias": "GO",
    "distrito federal": "DF",
}

YEARS = [
    int(y)
    for y in os.getenv("ATLAS_RAIS_YEARS", "").split(",")
    if y.strip().isdigit()
]


def _norm_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^\d+\s*[-–]\s*", "", s)
    return s


def uf_from_label(label: str) -> str | None:
    n = _norm_name(label)
    if n.upper() in UF_NAME_TO_SIGLA.values():
        return n.upper()
    # "35 - São Paulo"
    m = re.match(r"^(\d{2})\s*[-–]\s*(.+)$", (label or "").strip())
    if m:
        n = _norm_name(m.group(2))
    return UF_NAME_TO_SIGLA.get(n)


def parse_tabela2_xls(path: Path) -> list[dict]:
    try:
        import xlrd
    except ImportError:
        print("  xlrd ausente — pip install xlrd para ler XLS da RAIS", file=sys.stderr)
        return []
    wb = xlrd.open_workbook(str(path))
    if "tabela2" not in wb.sheet_names():
        return []
    sh = wb.sheet_by_name("tabela2")
    # cabeçalho anos na linha 3; Total nas colunas 3 (ano1) e 6 (ano2)
    year_a = year_b = None
    try:
        year_a = int(sh.cell_value(3, 1))
        year_b = int(sh.cell_value(3, 4))
    except (TypeError, ValueError):
        pass
    rows = []
    now = utc_now()
    for r in range(5, sh.nrows):
        label = str(sh.cell_value(r, 0) or "").strip()
        if not label or label.lower().startswith(("total", "fonte", "elabor", "obs", "norte", "nordeste", "sudeste", "sul", "centro")):
            # ainda tenta UF embutida
            pass
        uf = uf_from_label(label)
        if not uf:
            continue
        for year, col in ((year_a, 3), (year_b, 6)):
            if not year:
                continue
            try:
                val = float(sh.cell_value(r, col))
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "ano": int(year),
                    "uf": uf,
                    "vinculos": int(val),
                    "empregos": int(val),
                    "retrieved_at": now,
                    "fonte": "ftp_pdet_rais_desagregados",
                }
            )
    return rows


def parse_local_file(path: Path) -> list[dict]:
    suf = path.suffix.lower()
    now = utc_now()
    if suf == ".xls":
        return parse_tabela2_xls(path)
    if suf == ".csv":
        text = path.read_text(encoding="utf-8", errors="replace")
        delim = ";" if text[:2000].count(";") >= text[:2000].count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        out = []
        for row in reader:
            keys = {k.lower(): k for k in (row.keys() or [])}
            k_uf = keys.get("uf") or keys.get("sigla_uf") or keys.get("estado")
            k_ano = keys.get("ano") or keys.get("year") or keys.get("exercicio")
            k_v = (
                keys.get("vinculos")
                or keys.get("vínculos")
                or keys.get("empregos")
                or keys.get("estoque")
                or keys.get("empregos_formais")
            )
            if not (k_uf and k_ano and k_v):
                continue
            uf = str(row[k_uf]).strip().upper()[:2]
            try:
                ano = int(float(str(row[k_ano])))
                val = int(float(str(row[k_v]).replace(".", "").replace(",", ".")))
            except ValueError:
                continue
            out.append(
                {
                    "ano": ano,
                    "uf": uf,
                    "vinculos": val,
                    "empregos": val,
                    "retrieved_at": now,
                    "fonte": "ATLAS_RAIS_FILE",
                }
            )
        return out
    if suf in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            return []
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sh = wb.active
        rows_list = list(sh.iter_rows(values_only=True))
        if not rows_list:
            return []
        header = [str(h or "").lower() for h in rows_list[0]]
        out = []
        for row in rows_list[1:]:
            d = {header[i]: row[i] for i in range(min(len(header), len(row)))}
            uf = str(d.get("uf") or d.get("sigla_uf") or "").strip().upper()[:2]
            try:
                ano = int(float(d.get("ano") or d.get("year") or 0))
                val = int(float(d.get("vinculos") or d.get("empregos") or 0))
            except (TypeError, ValueError):
                continue
            if uf and ano and val:
                out.append(
                    {
                        "ano": ano,
                        "uf": uf,
                        "vinculos": val,
                        "empregos": val,
                        "retrieved_at": now,
                        "fonte": "ATLAS_RAIS_FILE",
                    }
                )
        return out
    return []


def ftp_list_years(ftp: FTP) -> list[int]:
    ftp.cwd(FTP_RAIS)
    names = ftp.nlst()
    return sorted(int(n) for n in names if n.isdigit())


def ftp_download_desag(ftp: FTP, year: int, dest: Path) -> bool:
    remote = f"{FTP_RAIS}/{year}/nacionais"
    try:
        ftp.cwd(remote)
    except Exception:
        return False
    names = {n.upper(): n for n in ftp.nlst()}
    real = names.get("4-RESULTADOSDESAGREGADOS.XLS")
    if not real:
        # fallback qualquer xls com desag
        for k, v in names.items():
            if "DESAG" in k and k.endswith(".XLS"):
                real = v
                break
    if not real:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    ftp.sendcmd("TYPE I")
    with dest.open("wb") as f:
        ftp.retrbinary(f"RETR {real}", f.write)
    return dest.exists() and dest.stat().st_size > 0


def main() -> int:
    run = start_run("rais", "rais.estoque_uf")
    out = bronze_dir("rais")
    raw = out / "raw"
    raw.mkdir(exist_ok=True)
    all_rows: list[dict] = []
    messages: list[str] = []

    local = os.getenv("ATLAS_RAIS_FILE")
    if local:
        p = Path(local)
        if p.is_file():
            all_rows.extend(parse_local_file(p))
            messages.append(f"local={p} rows={len(all_rows)}")
        else:
            messages.append(f"ATLAS_RAIS_FILE ausente: {local}")

    if not all_rows:
        try:
            ftp = FTP(FTP_HOST, timeout=180)
            ftp.encoding = "latin-1"
            ftp.login()
            years = YEARS or ftp_list_years(ftp)
            # P1: últimos anos agregados disponíveis (FTP histórico ~2007–2017)
            if not YEARS:
                years = [y for y in years if y >= 2010][-5:]
            print(f"  FTP years={years}", flush=True)
            for year in years:
                dest = raw / f"rais_{year}_desag.xls"
                try:
                    if not dest.exists() or dest.stat().st_size == 0:
                        print(f"  baixando RAIS {year} desagregados …", flush=True)
                        if not ftp_download_desag(ftp, year, dest):
                            print(f"  skip ausente {year}", flush=True)
                            continue
                    got = parse_tabela2_xls(dest)
                    # filtra ao ano do arquivo se necessário
                    all_rows.extend(got)
                    print(f"  OK {year}: +{len(got)} linhas", flush=True)
                except Exception as e:
                    messages.append(f"falha {year}: {e}")
                    print(f"  FALHA {year}: {e}", file=sys.stderr)
            try:
                ftp.quit()
            except Exception:
                pass
        except Exception as e:
            messages.append(f"FTP indisponível: {e}")
            print(f"FTP RAIS indisponível: {e}", file=sys.stderr)
            print(
                "Microdados /pdet/microdados/RAIS são pesados demais para P1. "
                "Use ATLAS_RAIS_FILE=csv com colunas ano,uf,vinculos.",
                file=sys.stderr,
            )

    # dedupe
    by_key = {(r["ano"], r["uf"]): r for r in all_rows if r.get("uf") and r.get("ano")}
    rows = list(by_key.values())
    extract = out / "rais_estoque_extract.jsonl"
    if rows:
        write_jsonl(extract, rows)

    write_json(
        out / "rais_meta.json",
        {
            "em": utc_now(),
            "fonte": "rais",
            "rows": len(rows),
            "messages": messages,
            "extract": extract.name if rows else None,
            "ingestion_run_id": run["ingestion_run_id"],
            "day": day_stamp(),
            "nota": "Estoque formal por UF (tabela2 desagregados). Microdados vínculos não processados em P1.",
        },
    )
    mark_ingested(
        "rais",
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        ok=len(rows) > 0,
        error=None if rows else (messages[-1] if messages else "sem dados"),
        dataset_id="rais.estoque_uf",
    )
    print(f"OK RAIS estoque: rows={len(rows)} -> {out}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
