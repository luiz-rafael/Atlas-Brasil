#!/usr/bin/env python3
"""
Ingest INEP Saeb — resultados agregados (LP/MT) UF/município.

Ordem:
  1) ATLAS_SAEB_FILE (xlsx/csv/zip local)
  2) Microdados Saeb (download.inep.gov.br/microdados) — planilha TS_MUNICIPIO
  3) Planilhas IDEB municipais (VL_NOTA_PORTUGUES / VL_NOTA_MATEMATICA)
  4) Scrape página gov.br microdados/saeb
  5) SKIPPED exit 0 se nada utilizável

Bronze: saeb_extract.jsonl
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

UA = os.getenv("ATLAS_USER_AGENT", "ATLAS-BRASIL-Ingestor/5.1 (+pesquisa Saeb/INEP)")

CANDIDATE_URLS = [
    "https://download.inep.gov.br/microdados/microdados_saeb_2023.zip",
    "https://download.inep.gov.br/microdados/microdados_saeb_2021_ensino_fundamental_e_medio.zip",
    "https://download.inep.gov.br/microdados/microdados_saeb_2019.zip",
]

IDEB_URLS = [
    "https://download.inep.gov.br/ideb/resultados/divulgacao_anos_iniciais_municipios_2025.zip",
    "https://download.inep.gov.br/ideb/resultados/divulgacao_anos_finais_municipios_2025.zip",
    "https://download.inep.gov.br/ideb/resultados/divulgacao_regioes_ufs_ideb_2025.zip",
]

MICRODADOS_PAGE = "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/saeb"

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
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=300.0, follow_redirects=True, verify=False)
        if r.status_code == 404:
            return {"url": url, "error": "HTTP 404"}
        if r.status_code == 200 and r.content and len(r.content) > 500:
            head = r.content[:200].lstrip().lower()
            if head.startswith(b"<!doctype") or head.startswith(b"<html"):
                raise RuntimeError("resposta HTML")
            dest.write_bytes(r.content)
            return {"url": url, "file": dest.name, "bytes": len(r.content), "via": "httpx"}
        raise RuntimeError(f"HTTP {r.status_code}")
    except Exception as first:
        if "404" in str(first):
            return {"url": url, "error": str(first)}
        print(f"  httpx falhou ({first}); tentando curl …", flush=True)
        cmd = [
            "curl.exe" if sys.platform == "win32" else "curl",
            "-L",
            "--retry",
            "3",
            "--retry-delay",
            "2",
            "--max-time",
            "900",
            "-A",
            UA,
            "-o",
            str(dest),
            url,
        ]
        try:
            subprocess.run(cmd, check=True, timeout=950)
            if dest.exists() and dest.stat().st_size > 500:
                head = dest.read_bytes()[:200].lstrip().lower()
                if head.startswith(b"<!doctype") or head.startswith(b"<html"):
                    dest.unlink(missing_ok=True)
                    return {"url": url, "error": f"{first}; curl: HTML"}
                return {"url": url, "file": dest.name, "bytes": dest.stat().st_size, "via": "curl"}
        except Exception as second:
            return {"url": url, "error": f"{first}; curl: {second}"}
        return {"url": url, "error": str(first)}


def _parse_float(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace("%", "")
    if not s or s.lower() in ("na", "nan", "-", "*", "nd", "#n/d", ""):
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _pick(fields: list[str], aliases: list[str]) -> str | None:
    norms = {_norm(f): f for f in fields}
    for a in aliases:
        na = _norm(a)
        if na in norms:
            return norms[na]
        for nk, orig in norms.items():
            if na and len(na) >= 4 and na in nk:
                return orig
    return None


def rows_from_matrix(matrix: list[list], default_year: int | None = None) -> list[dict]:
    """Parser genérico + IDEB (VL_NOTA_*) + Saeb TS_MUNICIPIO (MEDIA_*_LP/MT)."""
    # --- IDEB: header com SG_UF / CO_MUNICIPIO e VL_NOTA_PORTUGUES_YYYY ---
    ideb = _rows_from_ideb(matrix)
    if ideb:
        return ideb
    # --- Saeb TS_MUNICIPIO ---
    ts = _rows_from_ts_municipio(matrix, default_year)
    if ts:
        return ts

    header_idx = None
    for i, row in enumerate(matrix[:50]):
        norms = [_norm(str(c or "")) for c in row]
        if any("ibge" in n or n in ("codmunicipio", "co_municipio", "codigo") for n in norms) or any(
            "uf" == n or n.startswith("sguf") for n in norms
        ):
            if any("lp" in n or "portug" in n or "leitura" in n or "mt" in n or "matem" in n or "media" in n for n in norms):
                header_idx = i
                break
            if any("ibge" in n or "municip" in n for n in norms):
                header_idx = i
                break
    if header_idx is None:
        return []
    fields = [str(c or f"c{j}") for j, c in enumerate(matrix[header_idx])]
    col_ibge = _pick(fields, ["cod_ibge", "co_municipio", "codigo_municipio", "codmunicipio", "ibge"])
    col_uf = _pick(fields, ["sg_uf", "uf", "sigla_uf", "estado"])
    col_lp = _pick(fields, ["media_lp", "lp", "portugues", "lingua_portuguesa", "leitura", "proficiencia_lp"])
    col_mt = _pick(fields, ["media_mt", "mt", "matematica", "proficiencia_mt"])
    col_media = _pick(fields, ["media", "media_saeb", "nota_media"])
    col_ano = _pick(fields, ["ano", "nu_ano", "ano_saeb", "edicao"])
    year = default_year or int(os.getenv("ATLAS_SAEB_YEAR", "2023"))
    out = []
    now = utc_now()
    for row in matrix[header_idx + 1 :]:
        d = {fields[j]: row[j] if j < len(row) else None for j in range(len(fields))}
        y = year
        if col_ano and d.get(col_ano) is not None:
            ys = re.sub(r"\D", "", str(d[col_ano]))[:4]
            if ys.isdigit():
                y = int(ys)
        code = ""
        if col_ibge:
            code = re.sub(r"\D", "", str(d.get(col_ibge) or ""))
            if len(code) >= 6:
                code = code[:7] if len(code) >= 7 else code[:6]
            else:
                code = ""
        uf = str(d.get(col_uf) or "").upper()[:2] if col_uf else ""
        if code and code[:2] not in UF_PREFIXES:
            continue
        lp = _parse_float(d.get(col_lp)) if col_lp else None
        mt = _parse_float(d.get(col_mt)) if col_mt else None
        media = _parse_float(d.get(col_media)) if col_media else None
        if lp is None and mt is None and media is None:
            continue
        if code:
            nivel, tid = "MUNICIPALITY", f"mun_{code}"
        elif uf and uf.isalpha():
            nivel, tid, code = "STATE", f"uf_{uf}", uf
        else:
            continue
        out.append(
            {
                "nivel": nivel,
                "territory_id": tid,
                "cod_ibge": code,
                "uf": uf,
                "ano": y,
                "saeb_lp": lp,
                "saeb_mt": mt,
                "saeb_media": media,
                "retrieved_at": now,
                "fonte": "inep_saeb",
            }
        )
    return out


def _rows_from_ideb(matrix: list[list]) -> list[dict]:
    header_idx = None
    for i, row in enumerate(matrix[:40]):
        vals = [str(c or "") for c in row]
        if "CO_MUNICIPIO" in vals or "SG_UF" in vals:
            if any(v.startswith("VL_NOTA_PORTUGUES_") or v.startswith("VL_NOTA_MATEMATICA_") for v in vals):
                header_idx = i
                break
    if header_idx is None:
        return []
    fields = [str(c or f"c{j}") for j, c in enumerate(matrix[header_idx])]
    years = sorted(
        {
            int(m.group(1))
            for f in fields
            for m in [re.match(r"VL_NOTA_(?:PORTUGUES|MATEMATICA|MEDIA)_(\d{4})$", f)]
            if m
        },
        reverse=True,
    )
    if not years:
        return []
    # escolher o ano mais recente com pelo menos um valor numérico nas primeiras linhas
    year = None
    for y in years:
        cols = [f"VL_NOTA_PORTUGUES_{y}", f"VL_NOTA_MATEMATICA_{y}", f"VL_NOTA_MEDIA_{y}"]
        hit = False
        for row in matrix[header_idx + 1 : header_idx + 80]:
            d = {fields[j]: row[j] if j < len(row) else None for j in range(len(fields))}
            if any(_parse_float(d.get(c)) is not None for c in cols if c in fields):
                hit = True
                break
        if hit:
            year = y
            break
    if year is None:
        year = years[0]
    col_ibge = "CO_MUNICIPIO" if "CO_MUNICIPIO" in fields else None
    col_uf = "SG_UF" if "SG_UF" in fields else None
    col_rede = "REDE" if "REDE" in fields else None
    col_lp = f"VL_NOTA_PORTUGUES_{year}"
    col_mt = f"VL_NOTA_MATEMATICA_{year}"
    # NÃO usar VL_NOTA_MEDIA_* — no IDEB isso é o componente/nota agregada na escala do Ideb (~0–10),
    # não a média de proficiência Saeb (escala ~0–500).
    if col_lp not in fields and col_mt not in fields:
        return []
    now = utc_now()
    out = []
    for row in matrix[header_idx + 1 :]:
        d = {fields[j]: row[j] if j < len(row) else None for j in range(len(fields))}
        if col_rede:
            rede = _norm(str(d.get(col_rede) or ""))
            # preferir rede pública agregada; pular estadual/municipal isolados quando houver pública
            if rede and rede not in ("publica", "total", "pública"):
                # aceitar se não for fragmento
                if rede in ("estadual", "municipal", "privada", "federal"):
                    continue
        code = re.sub(r"\D", "", str(d.get(col_ibge) or "")) if col_ibge else ""
        if len(code) >= 6:
            code = code[:7] if len(code) >= 7 else code[:6]
        else:
            code = ""
        uf = str(d.get(col_uf) or "").upper()[:2] if col_uf else ""
        if code and code[:2] not in UF_PREFIXES:
            continue
        lp = _parse_float(d.get(col_lp)) if col_lp in fields else None
        mt = _parse_float(d.get(col_mt)) if col_mt in fields else None
        media = None
        if lp is not None and mt is not None:
            media = (lp + mt) / 2.0
        if lp is None and mt is None:
            continue
        if code:
            nivel, tid = "MUNICIPALITY", f"mun_{code}"
        elif uf and uf.isalpha():
            nivel, tid, code = "STATE", f"uf_{uf}", uf
        else:
            continue
        out.append(
            {
                "nivel": nivel,
                "territory_id": tid,
                "cod_ibge": code,
                "uf": uf,
                "ano": year,
                "saeb_lp": lp,
                "saeb_mt": mt,
                "saeb_media": media,
                "retrieved_at": now,
                "fonte": "inep_ideb_saeb",
            }
        )
    return out


def _rows_from_ts_municipio(matrix: list[list], default_year: int | None) -> list[dict]:
    if not matrix:
        return []
    fields = [str(c or f"c{j}") for j, c in enumerate(matrix[0])]
    norms = [_norm(f) for f in fields]
    if "comunicipio" not in norms and "codmunicipio" not in "".join(norms):
        return []
    lp_cols = [f for f in fields if re.match(r"(?i)MEDIA_\d+_LP$", str(f))]
    mt_cols = [f for f in fields if re.match(r"(?i)MEDIA_\d+_MT$", str(f))]
    if not lp_cols and not mt_cols:
        return []
    col_ibge = _pick(fields, ["CO_MUNICIPIO", "cod_municipio", "ibge"])
    col_uf = _pick(fields, ["CO_UF", "SG_UF", "NO_UF", "uf"])
    col_dep = _pick(fields, ["DEPENDENCIA_ADM", "dependencia"])
    col_loc = _pick(fields, ["LOCALIZACAO", "localizacao"])
    year = default_year or int(os.getenv("ATLAS_SAEB_YEAR", "2019"))
    # infer year from filename context via env if set
    now = utc_now()
    out = []
    for row in matrix[1:]:
        d = {fields[j]: row[j] if j < len(row) else None for j in range(len(fields))}
        if col_loc:
            loc = _norm(str(d.get(col_loc) or ""))
            if loc and loc not in ("total", "todas"):
                continue
        if col_dep:
            dep = _norm(str(d.get(col_dep) or ""))
            if dep and dep not in ("total", "publica", "pública"):
                continue
        code = re.sub(r"\D", "", str(d.get(col_ibge) or "")) if col_ibge else ""
        if len(code) >= 6:
            code = code[:7] if len(code) >= 7 else code[:6]
        else:
            code = ""
        uf_raw = str(d.get(col_uf) or "") if col_uf else ""
        uf = uf_raw.upper()[:2] if uf_raw and uf_raw[:1].isalpha() else ""
        if code and code[:2] not in UF_PREFIXES:
            continue
        lps = [_parse_float(d.get(c)) for c in lp_cols]
        mts = [_parse_float(d.get(c)) for c in mt_cols]
        lps = [v for v in lps if v is not None]
        mts = [v for v in mts if v is not None]
        lp = sum(lps) / len(lps) if lps else None
        mt = sum(mts) / len(mts) if mts else None
        media = None
        if lp is not None and mt is not None:
            media = (lp + mt) / 2.0
        elif lp is not None:
            media = lp
        elif mt is not None:
            media = mt
        if lp is None and mt is None:
            continue
        if code:
            nivel, tid = "MUNICIPALITY", f"mun_{code}"
        elif uf:
            nivel, tid, code = "STATE", f"uf_{uf}", uf
        else:
            continue
        out.append(
            {
                "nivel": nivel,
                "territory_id": tid,
                "cod_ibge": code,
                "uf": uf,
                "ano": year,
                "saeb_lp": lp,
                "saeb_mt": mt,
                "saeb_media": media,
                "retrieved_at": now,
                "fonte": "inep_saeb_ts_municipio",
            }
        )
    return out


def _year_from_name(name: str) -> int | None:
    m = re.search(r"(20\d{2})", name)
    return int(m.group(1)) if m else None


def extract_file(path: Path) -> list[dict]:
    suf = path.suffix.lower()
    year_hint = _year_from_name(path.name)
    if suf == ".csv":
        text = path.read_text(encoding="utf-8", errors="replace")
        sample = text[:4096]
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        matrix = [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]
        return rows_from_matrix(matrix, year_hint)
    if suf in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            return []
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception as e:
            print(f"  skip xlsx {path.name}: {e}", flush=True)
            return []
        rows: list[dict] = []
        for name in wb.sheetnames:
            sh = wb[name]
            matrix = [list(r) for r in sh.iter_rows(values_only=True)]
            rows.extend(rows_from_matrix(matrix, year_hint))
        return rows
    if suf == ".zip":
        try:
            zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            print(f"  skip zip inválido {path.name}", flush=True)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return []
        tmp = path.parent / f"_unz_saeb_{path.stem}"
        tmp.mkdir(exist_ok=True)
        rows = []
        year_hint = _year_from_name(path.name) or year_hint
        with zf as z:
            names = z.namelist()
            # priorizar planilha municipal de resultados Saeb / IDEB
            ranked = sorted(
                names,
                key=lambda n: (
                    0
                    if "ts_municipio" in n.lower()
                    else 1
                    if "municip" in n.lower() and n.lower().endswith((".xlsx", ".csv"))
                    else 2
                    if n.lower().endswith((".xlsx", ".csv"))
                    else 9,
                    len(n),
                ),
            )
            for name in ranked:
                low = name.lower()
                if not any(low.endswith(ext) for ext in (".xlsx", ".csv", ".xls")):
                    continue
                # evitar microdados aluno gigantes
                info = z.getinfo(name)
                if info.file_size > 80_000_000 and "municip" not in low:
                    continue
                if "aluno" in low or "professor" in low or "diretor" in low:
                    continue
                dest = tmp / Path(name).name
                if not dest.exists() or dest.stat().st_size != info.file_size:
                    dest.write_bytes(z.read(name))
                # year from parent zip if member name lacks it
                y = _year_from_name(name) or year_hint
                got = extract_file(dest) if y is None else rows_from_matrix(
                    _load_matrix(dest), y
                )
                if got:
                    rows.extend(got)
                    if len(rows) > 100:
                        break
        # dedupe territory+ano preferindo fonte com mais campos
        by_key: dict[tuple, dict] = {}
        for r in rows:
            key = (r.get("territory_id"), r.get("ano"))
            prev = by_key.get(key)
            if prev is None or _score_row(r) >= _score_row(prev):
                by_key[key] = r
        return list(by_key.values())
    return []


def _load_matrix(path: Path) -> list[list]:
    suf = path.suffix.lower()
    if suf == ".csv":
        text = path.read_text(encoding="utf-8", errors="replace")
        delim = ";" if text[:4096].count(";") >= text[:4096].count(",") else ","
        return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]
    if suf in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sh = wb[wb.sheetnames[0]]
        return [list(r) for r in sh.iter_rows(values_only=True)]
    return []


def _score_row(r: dict) -> int:
    return sum(1 for k in ("saeb_lp", "saeb_mt", "saeb_media") if r.get(k) is not None)


def scrape_links(outdir: Path) -> list[dict]:
    metas = []
    try:
        throttle()
        r = httpx.get(MICRODADOS_PAGE, headers={"User-Agent": UA}, timeout=45, follow_redirects=True)
        if r.status_code != 200:
            return [{"page": MICRODADOS_PAGE, "error": f"HTTP {r.status_code}"}]
        hrefs = []
        for href in re.findall(r'href="([^"]+)"', r.text):
            low = href.lower()
            if not (low.endswith(".zip") or "microdados_saeb" in low):
                continue
            if href.startswith("/"):
                href = "https://www.gov.br" + href
            hrefs.append(href)
        for href in hrefs[:4]:
            dest = outdir / Path(href.split("?")[0]).name
            if dest.exists() and dest.stat().st_size > 1000:
                metas.append({"url": href, "file": dest.name, "via": "cache"})
            else:
                metas.append(download_bytes(href, dest))
    except Exception as e:
        metas.append({"page": MICRODADOS_PAGE, "error": str(e)})
    return metas


def main() -> int:
    run = start_run("inep_saeb", "inep.saeb")
    out = bronze_dir("inep_saeb")
    raw = out / "raw"
    raw.mkdir(exist_ok=True)
    files_meta: list[dict] = []
    rows: list[dict] = []
    messages: list[str] = []

    local = os.getenv("ATLAS_SAEB_FILE")
    if local:
        p = Path(local)
        if p.is_file():
            rows = extract_file(p)
            files_meta.append({"file": str(p), "via": "ATLAS_SAEB_FILE", "rows": len(rows)})
        else:
            messages.append(f"ATLAS_SAEB_FILE ausente: {local}")

    # IDEB municipal (leve, VL_NOTA LP/MT) — preferir antes do microdado Saeb gigante
    if not rows:
        for url in IDEB_URLS:
            dest = raw / Path(url.split("?")[0]).name
            # reutilizar bronze inep do dia se existir
            alt = LAKE_INEP_CANDIDATES(dest.name)
            src = alt if alt else dest
            if not src.exists():
                meta = download_bytes(url, dest)
                files_meta.append(meta)
                if meta.get("error"):
                    continue
                src = dest
            else:
                files_meta.append({"url": url, "file": src.name, "via": "reuse/cache"})
            got = extract_file(src)
            if got:
                rows = got
                messages.append(f"IDEB/Saeb notas via {src.name}: {len(got)}")
                break

    if not rows:
        for url in CANDIDATE_URLS:
            dest = raw / Path(url.split("?")[0]).name
            # reuse probe cache
            probe = ROOT / "data" / "lake" / "_probe" / dest.name
            src = dest
            if probe.exists() and probe.stat().st_size > 1000:
                src = probe
                files_meta.append(
                    {"url": url, "file": str(probe), "via": "probe_cache", "bytes": probe.stat().st_size}
                )
            elif dest.exists() and dest.stat().st_size > 1000:
                files_meta.append({"url": url, "file": dest.name, "via": "cache"})
            else:
                meta = download_bytes(url, dest)
                files_meta.append(meta)
                if meta.get("error"):
                    continue
                src = dest
            got = extract_file(src)
            if got:
                rows = got
                messages.append(f"Saeb microdados {src.name}: {len(got)}")
                break

    if not rows:
        if os.getenv("ATLAS_SAEB_SCRAPE", "1").strip().lower() in ("1", "true", "yes"):
            try:
                files_meta.extend(scrape_links(raw))
            except Exception as e:
                messages.append(f"scrape falhou: {e}")
            for m in files_meta:
                if m.get("file") and not m.get("error"):
                    p = raw / Path(m["file"]).name
                    if not p.exists():
                        p = Path(m["file"])
                    if p.exists():
                        got = extract_file(p)
                        if got:
                            rows = got
                            break

    if rows:
        write_jsonl(out / "saeb_extract.jsonl", rows)
    else:
        messages.append(
            "SKIPPED inep_saeb: sem planilha utilizável. "
            "Defina ATLAS_SAEB_FILE=caminho.xlsx (colunas IBGE + LP/MT)."
        )
        print(messages[-1], flush=True)

    write_json(
        out / "saeb_meta.json",
        {
            "em": utc_now(),
            "fonte": "inep_saeb",
            "rows": len(rows),
            "files": files_meta,
            "messages": messages,
            "ingestion_run_id": run["ingestion_run_id"],
            "day": day_stamp(),
            "portal": MICRODADOS_PAGE,
        },
    )
    mark_ingested(
        "inep_saeb",
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        ok=len(rows) > 0,
        error=None if rows else (messages[-1] if messages else "sem dados"),
        dataset_id="inep.saeb",
    )
    print(f"OK INEP Saeb: rows={len(rows)} -> {out}")
    return 0


def LAKE_INEP_CANDIDATES(name: str) -> Path | None:
    base = ROOT / "data" / "lake" / "bronze" / "inep"
    if not base.exists():
        return None
    for day in sorted(base.iterdir(), reverse=True):
        if not day.is_dir():
            continue
        p = day / name
        if p.exists() and p.stat().st_size > 1000:
            return p
    return None


if __name__ == "__main__":
    raise SystemExit(main())
