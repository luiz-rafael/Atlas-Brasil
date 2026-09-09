#!/usr/bin/env python3
"""
Ingest SNIS/SINISA — Água e Esgotos (cobertura municipal).

Ordem de tentativa:
  1) ATLAS_SNIS_FILE / ATLAS_SNIS_CSV (drop local csv/xlsx)
  2) URLs SINISA/gov.br (zip Resultados) + scrape planilhas
  3) CKAN dadosabertos.cidades.gov.br
  4) Espelhos comunitários (só se passarem validação IBGE/%)

Métricas: agua_atendimento_pct (IN055/IAG0001), esgoto_atendimento_pct (IN015/IES0001),
          esgoto_tratamento_pct (IN016/IES2004/IES2003).
Bronze: snis_ae_extract.jsonl
"""

from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, throttle, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

UA = os.getenv(
    "ATLAS_USER_AGENT",
    "Mozilla/5.0 (compatible; ATLAS-BRASIL-Ingestor/5.1; +pesquisa documental oficial)",
)

CKAN = "https://dadosabertos.cidades.gov.br/api/3/action/package_search"

CANDIDATE_URLS = [
    "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa/arquivos/SINISA_Resultados_Ref2023.zip",
    "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa/resultados-sinisa/SINISA_ESGOTO_Planilhas_2023_v2.zip",
]

# coluna canônica → aliases (SNIS clássico + SINISA)
METRIC_ALIASES = {
    "agua_atendimento_pct": [
        "iag0001", "in055", "agua_atendimento", "atendimento_agua",
        "atendimentodapopulacaototalcomrededeabastecimentodeagua",
    ],
    "esgoto_atendimento_pct": [
        "ies0001", "in015", "in056", "esgoto_atendimento", "coleta_esgoto",
        "atendimentodapopulacaototalcomredecoletoradeesgoto",
    ],
    "esgoto_tratamento_pct": [
        "ies2004", "ies2003", "in016", "in046", "esgoto_tratamento",
        "esgototratadoreferidoaoesgotocoletado",
        "esgototratadoreferidoaaguaconsumida",
    ],
}

UF_PREFIXES = {
    "11", "12", "13", "14", "15", "16", "17",
    "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "31", "32", "33", "35", "41", "42", "43", "50", "51", "52", "53",
}


def _norm(s: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", s or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", t.lower())


def download_bytes(url: str, dest: Path) -> dict:
    throttle()
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": UA}
    try:
        r = httpx.get(url, headers=headers, timeout=300.0, follow_redirects=True)
        if r.status_code == 200 and r.content and len(r.content) > 200:
            dest.write_bytes(r.content)
            return {"url": url, "file": dest.name, "bytes": len(r.content), "via": "httpx"}
        raise RuntimeError(f"HTTP {r.status_code}")
    except Exception as first:
        print(f"  httpx falhou ({first}); tentando curl …", flush=True)
        cmd = [
            "curl.exe" if sys.platform == "win32" else "curl",
            "-L", "--retry", "3", "-A", UA, "-o", str(dest), url,
        ]
        try:
            subprocess.run(cmd, check=True, timeout=600)
            if dest.exists() and dest.stat().st_size > 200:
                return {"url": url, "file": dest.name, "bytes": dest.stat().st_size, "via": "curl"}
        except Exception as second:
            return {"url": url, "error": f"{first}; curl: {second}"}
        return {"url": url, "error": str(first)}


def _parse_float(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace("%", "")
    if not s or s.lower().startswith("não") or s.lower() in ("na", "nan", "-", "null", "none", "#n/d"):
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _valid_ibge(code: str) -> str | None:
    code = re.sub(r"\D", "", str(code or ""))
    if len(code) < 6:
        return None
    code = code[:7] if len(code) >= 7 else code[:6]
    if code[:2] not in UF_PREFIXES:
        return None
    return code


def _valid_pct(v: float | None) -> float | None:
    if v is None:
        return None
    if 0 <= v <= 100:
        return v
    if 0 <= v <= 1:
        return v * 100.0
    return None


def _pick_col(fieldnames: list[str], aliases: list[str]) -> str | None:
    norms = {_norm(f): f for f in fieldnames}
    for a in aliases:
        na = _norm(a)
        if na in norms:
            return norms[na]
        for nk, orig in norms.items():
            if na and (na == nk or (len(na) >= 5 and na in nk)):
                return orig
    return None


def year_from_text(*texts: str) -> int | None:
    for t in texts:
        m = re.search(r"ano\s+de\s+refer[eê]ncia\s+(\d{4})", t or "", re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"\b(20\d{2})\b", t or "")
        if m:
            return int(m.group(1))
    return None


def rows_from_matrix(rows: list[list], default_year: int | None = None) -> list[dict]:
    """Detecta linha de cabeçalho com cod_IBGE / Código do IBGE."""
    header_idx = None
    # preferir linha com códigos IAG/IES/IN0 (abaixo do título legível)
    for i, row in enumerate(rows[:40]):
        norms = [_norm(str(c or "")) for c in row]
        if any(n.startswith(("iag", "ies", "in0")) for n in norms) and any(
            n in ("codibge", "codigodoibge", "codigoibge") for n in norms
        ):
            header_idx = i
            break
    if header_idx is None:
        for i, row in enumerate(rows[:40]):
            norms = [_norm(str(c or "")) for c in row]
            if any(n in ("codibge", "codigodoibge", "codigoibge") for n in norms):
                header_idx = i
                break
    if header_idx is None:
        return []
    # ano no cabeçalho acima
    preamble = " ".join(
        str(c) for r in rows[: header_idx + 1] for c in r if c is not None
    )
    year = default_year or year_from_text(preamble) or int(os.getenv("ATLAS_SNIS_YEAR", "2023"))
    fields = [str(c or f"c{j}") for j, c in enumerate(rows[header_idx])]
    col_mun = _pick_col(fields, ["cod_ibge", "codigo_ibge", "codigo_do_ibge", "codibge", "ibge"])
    if not col_mun:
        return []
    cols = {k: _pick_col(fields, v) for k, v in METRIC_ALIASES.items()}
    if not any(cols.values()):
        return []
    out = []
    now = utc_now()
    mun_i = fields.index(col_mun)
    for row in rows[header_idx + 1 :]:
        if not row or mun_i >= len(row):
            continue
        code = _valid_ibge(row[mun_i])
        if not code:
            continue
        rec = {"cod_ibge": code, "ano": year, "retrieved_at": now}
        d = {fields[j]: row[j] if j < len(row) else None for j in range(len(fields))}
        for metric, col in cols.items():
            if not col:
                continue
            rec[metric] = _valid_pct(_parse_float(d.get(col)))
        if any(rec.get(m) is not None for m in METRIC_ALIASES):
            out.append(rec)
    return out


def rows_from_csv_text(text: str, default_year: int | None = None) -> list[dict]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    matrix = [list(r) for r in reader]
    return rows_from_matrix(matrix, default_year=default_year)


def rows_from_xlsx(path: Path) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    all_rows: list[dict] = []
    prefer = [s for s in wb.sheetnames if "atend" in s.lower() or "operac" in s.lower()]
    order = prefer + [s for s in wb.sheetnames if s not in prefer]
    for name in order:
        if "nota" in name.lower():
            continue
        sh = wb[name]
        matrix = [list(row) for row in sh.iter_rows(values_only=True)]
        got = rows_from_matrix(matrix)
        all_rows.extend(got)
    return merge_rows(all_rows)


def merge_rows(rows: list[dict]) -> list[dict]:
    by: dict[tuple, dict] = {}
    for r in rows:
        key = (r.get("cod_ibge"), r.get("ano"))
        if not key[0] or not key[1]:
            continue
        cur = by.setdefault(
            key,
            {"cod_ibge": key[0], "ano": key[1], "retrieved_at": r.get("retrieved_at")},
        )
        for m in METRIC_ALIASES:
            if r.get(m) is not None and cur.get(m) is None:
                cur[m] = r[m]
    return list(by.values())


def unpack_zip(path: Path, dest_dir: Path) -> list[Path]:
    out: list[Path] = []
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            low = name.lower()
            if not (low.endswith(".xlsx") or low.endswith(".csv") or low.endswith(".xls")):
                continue
            # prioriza base municipal indicadores
            target = dest_dir / Path(name).name
            target.write_bytes(z.read(name))
            out.append(target)
    # ordena: Indicadores + Municipal primeiro
    def score(p: Path) -> tuple:
        n = p.name.lower()
        return (
            0 if "indicador" in n else 1,
            0 if "municipal" in n else 1,
            0 if "agua" in n or "esgoto" in n else 1,
            n,
        )
    return sorted(out, key=score)


def extract_from_file(path: Path) -> list[dict]:
    suf = path.suffix.lower()
    if suf == ".csv":
        return rows_from_csv_text(path.read_text(encoding="utf-8", errors="replace"))
    if suf in (".xlsx", ".xlsm"):
        return rows_from_xlsx(path)
    if suf == ".zip":
        tmp = path.parent / f"_unz_{path.stem}"
        files = unpack_zip(path, tmp)
        rows: list[dict] = []
        for f in files:
            rows.extend(extract_from_file(f))
        return merge_rows(rows)
    return []


def scrape_gov_links(outdir: Path) -> list[dict]:
    pages = [
        "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa/resultados-sinisa",
        "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa/planilhas-de-informacoes-e-indicadores",
    ]
    metas = []
    for page in pages:
        try:
            throttle()
            r = httpx.get(page, headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
            if r.status_code != 200:
                metas.append({"page": page, "error": f"HTTP {r.status_code}"})
                continue
            links = re.findall(r'href="([^"]+)"', r.text)
            for href in links:
                low = href.lower()
                if not any(low.endswith(ext) for ext in (".zip", ".xlsx", ".xls", ".csv")):
                    continue
                if "barragem" in low or "pluvial" in low or "residuo" in low:
                    continue
                if href.startswith("/"):
                    href = "https://www.gov.br" + href
                dest = outdir / Path(href.split("?")[0]).name
                if dest.exists() and dest.stat().st_size > 1000:
                    metas.append({"url": href, "file": dest.name, "via": "cache"})
                    continue
                metas.append(download_bytes(href, dest))
        except Exception as e:
            metas.append({"page": page, "error": str(e)})
    return metas


def try_ckan(outdir: Path) -> list[dict]:
    metas = []
    try:
        throttle()
        r = httpx.get(CKAN, params={"q": "snis", "rows": 10}, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        for pkg in r.json().get("result", {}).get("results", []):
            for res in pkg.get("resources") or []:
                url = res.get("url") or ""
                fmt = (res.get("format") or "").lower()
                if not url:
                    continue
                if fmt in ("csv", "xlsx", "xls", "zip") or any(
                    url.lower().endswith(ext) for ext in (".csv", ".xlsx", ".xls", ".zip")
                ):
                    dest = outdir / f"ckan_{Path(url.split('?')[0]).name}"
                    metas.append(download_bytes(url, dest))
    except Exception as e:
        metas.append({"error": f"ckan: {e}"})
    return metas


def collect_from_paths(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        if not p.exists():
            continue
        try:
            got = extract_from_file(p)
            if got:
                print(f"  parse {p.name}: {len(got)} rows", flush=True)
                rows.extend(got)
        except Exception as e:
            print(f"  skip parse {p.name}: {e}", flush=True)
    return merge_rows(rows)


def main() -> int:
    run = start_run("snis", "snis.ae_municipal")
    out = bronze_dir("snis")
    raw = out / "raw"
    raw.mkdir(exist_ok=True)
    messages: list[str] = []
    files_meta: list[dict] = []
    rows: list[dict] = []

    local = os.getenv("ATLAS_SNIS_FILE") or os.getenv("ATLAS_SNIS_CSV")
    if local:
        p = Path(local)
        if p.is_file():
            print(f"  usando arquivo local {p}", flush=True)
            rows = merge_rows(extract_from_file(p))
            files_meta.append({"file": str(p), "via": "ATLAS_SNIS_FILE", "rows": len(rows)})
        else:
            messages.append(f"ATLAS_SNIS_FILE não encontrado: {local}")

    # reutiliza zips/xlsx já baixados no bronze do dia
    if not rows:
        cached = [
            p
            for p in list(raw.glob("_tmp_SINISA_*Indicadores*Municipal*.xlsx"))
            + list(raw.glob("SINISA_Resultados_Ref*.zip"))
            + list(raw.glob("SINISA_*Planilhas*.zip"))
            if p.is_file()
        ]
        # dedupe por nome canônico
        seen = set()
        uniq = []
        for p in cached:
            key = p.name.lower().replace("_tmp_", "")
            if key in seen:
                continue
            seen.add(key)
            uniq.append(p)
        if uniq:
            rows = collect_from_paths(uniq)

    if not rows:
        for url in CANDIDATE_URLS:
            dest = raw / Path(url.split("?")[0]).name
            meta = download_bytes(url, dest) if not dest.exists() else {"url": url, "file": dest.name, "via": "cache"}
            files_meta.append(meta)
            if meta.get("error"):
                continue
            rows = collect_from_paths([dest])
            if rows:
                break

    if not rows:
        files_meta.extend(scrape_gov_links(raw))
        paths = [
            raw / m["file"]
            for m in files_meta
            if m.get("file") and not m.get("error") and (raw / m["file"]).exists()
        ]
        rows = collect_from_paths(paths)

    if not rows:
        files_meta.extend(try_ckan(raw))
        paths = [
            raw / m["file"]
            for m in files_meta
            if m.get("file") and not m.get("error") and (raw / m["file"]).exists()
        ]
        rows = collect_from_paths(paths)

    extract = out / "snis_ae_extract.jsonl"
    if rows:
        write_jsonl(extract, rows)
        messages.append(f"extract={len(rows)} linhas")
    else:
        messages.append(
            "Sem dump SNIS/SINISA utilizável. Defina ATLAS_SNIS_FILE=caminho.xlsx "
            "(planilha municipal com cod_IBGE + IAG0001/IES0001/IES2004 ou IN055/IN015/IN016)."
        )
        print(messages[-1], file=sys.stderr)

    write_json(
        out / "snis_meta.json",
        {
            "em": utc_now(),
            "fonte": "snis",
            "files": files_meta,
            "messages": messages,
            "rows": len(rows),
            "extract": extract.name if rows else None,
            "ingestion_run_id": run["ingestion_run_id"],
            "day": day_stamp(),
            "portal": "https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa",
            "codes": "IAG0001/IES0001/IES2004 (SINISA) ou IN055/IN015/IN016 (SNIS)",
        },
    )
    mark_ingested(
        "snis",
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        ok=len(rows) > 0,
        error=None if rows else messages[-1],
        dataset_id="snis.ae",
    )
    print(f"OK SNIS AE: rows={len(rows)} -> {out}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
