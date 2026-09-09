#!/usr/bin/env python3
"""
Ingest INEP Censo Escolar — matrículas educação básica (slice).

Ordem:
  1) ATLAS_CENSO_FILE (csv/xlsx/zip local com matriculas + IBGE/UF)
  2) Microdados Censo (download.inep.gov.br/dados_abertos) — QT_MAT_BAS
  3) SKIPPED exit 0

IMPORTANTE: taxas de rendimento (tx_rend_*) NÃO são usadas como matrículas.
Bronze: censo_escolar_extract.jsonl
"""

from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import bronze_dir, day_stamp, throttle, utc_now, write_json, write_jsonl  # noqa: E402
from pipelines.registry import mark_ingested, start_run  # noqa: E402

UA = os.getenv("ATLAS_USER_AGENT", "ATLAS-BRASIL-Ingestor/5.1 (+pesquisa Censo Escolar/INEP)")
YEAR = os.getenv("ATLAS_CENSO_YEAR", "2024")

CANDIDATE_URLS = [
    f"https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_{YEAR}.zip",
    "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2024.zip",
    "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2023.zip",
    "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2025_.zip",
]

MICRODADOS_PAGE = (
    "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar"
)


def _norm(s: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", s or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", t.lower())


def download_bytes(url: str, dest: Path) -> dict:
    if "tx_rend" in url.lower():
        return {"url": url, "error": "tx_rend ignorado (não é matrícula)"}
    if url.rstrip("/").endswith("censo-escolar") and not any(
        url.lower().endswith(ext) for ext in (".zip", ".csv", ".xlsx")
    ):
        return {"url": url, "error": "página HTML, não arquivo"}
    throttle()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=600.0, follow_redirects=True, verify=False)
        if r.status_code == 200 and r.content and len(r.content) > 500:
            head = r.content[:200].lstrip().lower()
            if head.startswith(b"<!doctype") or head.startswith(b"<html"):
                raise RuntimeError("resposta HTML")
            dest.write_bytes(r.content)
            return {"url": url, "file": dest.name, "bytes": len(r.content), "via": "httpx"}
        raise RuntimeError(f"HTTP {r.status_code}")
    except Exception as first:
        print(f"  httpx falhou ({first}); tentando curl …", flush=True)
        cmd = [
            "curl.exe" if sys.platform == "win32" else "curl",
            "-L",
            "--retry",
            "5",
            "--retry-delay",
            "2",
            "-A",
            UA,
            "-o",
            str(dest),
            url,
        ]
        try:
            subprocess.run(cmd, check=True, timeout=900)
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
    s = str(v).strip()
    if not s or s.lower() in ("na", "nan", "-", "*", ""):
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    else:
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
            if na and len(na) >= 5 and na in nk:
                return orig
    return None


def rows_from_matrix(matrix: list[list], default_year: int) -> list[dict]:
    header_idx = None
    for i, row in enumerate(matrix[:40]):
        norms = [_norm(str(c or "")) for c in row]
        # rejeitar taxas de rendimento disfarçadas
        if any("txrend" in n or "aprovacao" in n or "reprovacao" in n or "abandono" in n for n in norms):
            if not any("matricul" in n or "qtmat" in n for n in norms):
                continue
        if any("matricul" in n or "matricula" in n or n.startswith("qtmat") for n in norms):
            if any("ibge" in n or "municip" in n or n in ("uf", "sguf", "couf") for n in norms):
                header_idx = i
                break
        if any(n in ("comunicipio", "codmunicipio") or "qtmatbas" in n for n in norms):
            header_idx = i
            break
    if header_idx is None:
        return []
    fields = [str(c or f"c{j}") for j, c in enumerate(matrix[header_idx])]
    # bloquear se parecer só rendimento
    joined = " ".join(_norm(f) for f in fields)
    if ("txrend" in joined or "aprovacao" in joined) and "qtmat" not in joined and "matricul" not in joined:
        return []
    col_ibge = _pick(fields, ["cod_ibge", "co_municipio", "codigo_municipio", "co_mun", "ibge"])
    col_uf = _pick(fields, ["sg_uf", "uf", "co_uf", "sigla"])
    col_mat = _pick(
        fields,
        [
            "qt_mat_bas",
            "matriculas",
            "matricula",
            "qt_matriculas_basica",
            "matriculas_educacao_basica",
            "nu_matriculas",
            "total_matriculas",
        ],
    )
    if not col_mat:
        return []
    out = []
    now = utc_now()
    # se for arquivo escola-a-escola, agregar por município
    sums: dict[tuple, float] = defaultdict(float)
    meta: dict[tuple, dict] = {}
    for row in matrix[header_idx + 1 :]:
        d = {fields[j]: row[j] if j < len(row) else None for j in range(len(fields))}
        mat = _parse_float(d.get(col_mat))
        if mat is None:
            continue
        code = re.sub(r"\D", "", str(d.get(col_ibge) or "")) if col_ibge else ""
        uf = str(d.get(col_uf) or "").upper()[:2] if col_uf else ""
        if len(code) >= 6:
            code = code[:7] if len(code) >= 7 else code[:6]
            nivel, tid = "MUNICIPALITY", f"mun_{code}"
        elif uf.isalpha():
            nivel, tid, code = "STATE", f"uf_{uf}", uf
        else:
            continue
        key = (tid, default_year)
        sums[key] += mat
        meta[key] = {"nivel": nivel, "territory_id": tid, "cod_ibge": code, "uf": uf, "ano": default_year}
    for key, total in sums.items():
        m = meta[key]
        out.append(
            {
                **m,
                "matriculas_basica": total,
                "retrieved_at": now,
                "fonte": "inep_censo",
            }
        )
    return out


def aggregate_ed_basica_csv(path: Path, year: int) -> list[dict]:
    """Stream CSV microdados_ed_basica — soma QT_MAT_BAS por CO_MUNICIPIO."""
    # detectar encoding
    raw = path.read_bytes()[:4096]
    text_sample = raw.decode("latin-1", errors="replace")
    delim = ";" if text_sample.count(";") >= text_sample.count(",") else ","
    enc = "latin-1"
    sums: dict[str, float] = defaultdict(float)
    ufs: dict[str, str] = {}
    now = utc_now()
    with path.open("r", encoding=enc, errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=delim)
        if not reader.fieldnames:
            return []
        fields = list(reader.fieldnames)
        col_ibge = _pick(fields, ["CO_MUNICIPIO", "co_municipio", "cod_ibge"])
        col_uf = _pick(fields, ["SG_UF", "uf", "CO_UF"])
        col_mat = _pick(fields, ["QT_MAT_BAS", "qt_mat_bas", "matriculas"])
        col_ano = _pick(fields, ["NU_ANO_CENSO", "ano", "nu_ano"])
        if not col_ibge or not col_mat:
            return []
        n = 0
        for row in reader:
            n += 1
            mat = _parse_float(row.get(col_mat))
            if mat is None:
                continue
            code = re.sub(r"\D", "", str(row.get(col_ibge) or ""))
            if len(code) < 6:
                continue
            code = code[:7] if len(code) >= 7 else code[:6]
            y = year
            if col_ano and row.get(col_ano):
                ys = re.sub(r"\D", "", str(row[col_ano]))[:4]
                if ys.isdigit():
                    y = int(ys)
            key = f"{code}|{y}"
            sums[key] += mat
            if col_uf:
                uf = str(row.get(col_uf) or "").upper()[:2]
                if uf.isalpha():
                    ufs[key] = uf
            if n % 200000 == 0:
                print(f"  censo rows lidas={n} mun_keys={len(sums)}", flush=True)
    out = []
    for key, total in sums.items():
        code, ys = key.split("|", 1)
        out.append(
            {
                "nivel": "MUNICIPALITY",
                "territory_id": f"mun_{code}",
                "cod_ibge": code,
                "uf": ufs.get(key, ""),
                "ano": int(ys),
                "matriculas_basica": total,
                "retrieved_at": now,
                "fonte": "inep_censo",
            }
        )
    return out


def extract_file(path: Path, year: int) -> list[dict]:
    suf = path.suffix.lower()
    if "tx_rend" in path.name.lower():
        print(f"  skip {path.name}: taxas de rendimento (não inventar matrículas)", flush=True)
        return []
    if suf == ".csv":
        # microdados ed_basica costuma ser grande — agregação streaming
        if path.stat().st_size > 5_000_000 or "ed_basica" in path.name.lower() or "microdados" in path.name.lower():
            return aggregate_ed_basica_csv(path, year)
        text = path.read_text(encoding="utf-8", errors="replace")
        delim = ";" if text[:2048].count(";") >= text[:2048].count(",") else ","
        matrix = [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]
        return rows_from_matrix(matrix, year)
    if suf in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            return []
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = []
        for name in wb.sheetnames:
            sh = wb[name]
            matrix = [list(r) for r in sh.iter_rows(values_only=True)]
            rows.extend(rows_from_matrix(matrix, year))
        return rows
    if suf == ".zip":
        tmp = path.parent / f"_unz_censo_{path.stem}"
        tmp.mkdir(exist_ok=True)
        rows = []
        with zipfile.ZipFile(path) as z:
            names = sorted(
                z.namelist(),
                key=lambda n: (
                    0 if "ed_basica" in n.lower() and n.lower().endswith(".csv") else 1,
                    0 if "municip" in n.lower() else 1,
                    len(n),
                ),
            )
            for name in names:
                low = name.lower()
                if "tx_rend" in low:
                    continue
                if not any(low.endswith(ext) for ext in (".csv", ".xlsx")):
                    continue
                info = z.getinfo(name)
                # preferir CSV ed_basica mesmo grande
                if info.file_size > 500_000_000 and "ed_basica" not in low and "matricul" not in low:
                    continue
                dest = tmp / Path(name).name
                if not dest.exists() or dest.stat().st_size != info.file_size:
                    print(f"  extraindo {name} ({info.file_size} bytes)…", flush=True)
                    dest.write_bytes(z.read(name))
                y = year
                m = re.search(r"(20\d{2})", name)
                if m:
                    y = int(m.group(1))
                got = extract_file(dest, y)
                if got:
                    rows.extend(got)
                    if len(rows) > 100:
                        break
        return rows
    return []


def scrape_microdados_links(outdir: Path) -> list[dict]:
    metas = []
    try:
        throttle()
        r = httpx.get(MICRODADOS_PAGE, headers={"User-Agent": UA}, timeout=45, follow_redirects=True)
        if r.status_code != 200:
            return [{"page": MICRODADOS_PAGE, "error": f"HTTP {r.status_code}"}]
        hrefs = []
        for href in re.findall(r'href="([^"]+)"', r.text):
            low = href.lower()
            if "microdados_censo_escolar" not in low or not low.endswith(".zip"):
                continue
            if "tx_rend" in low:
                continue
            hrefs.append(href)
        for href in hrefs[:3]:
            dest = outdir / Path(href.split("?")[0]).name
            if dest.exists() and dest.stat().st_size > 1000:
                metas.append({"url": href, "file": dest.name, "via": "cache"})
            else:
                metas.append(download_bytes(href, dest))
    except Exception as e:
        metas.append({"page": MICRODADOS_PAGE, "error": str(e)})
    return metas


def main() -> int:
    run = start_run("inep_censo", "inep.censo_escolar")
    out = bronze_dir("inep_censo")
    raw = out / "raw"
    raw.mkdir(exist_ok=True)
    year = int(YEAR)
    rows: list[dict] = []
    files_meta: list[dict] = []
    messages: list[str] = []

    local = os.getenv("ATLAS_CENSO_FILE")
    if local:
        p = Path(local)
        if p.is_file():
            rows = extract_file(p, year)
            files_meta.append({"file": str(p), "via": "ATLAS_CENSO_FILE", "rows": len(rows)})
        else:
            messages.append(f"ATLAS_CENSO_FILE ausente: {local}")

    if not rows:
        for url in CANDIDATE_URLS:
            dest = raw / Path(url.split("?")[0]).name
            if not dest.suffix:
                continue
            probe = ROOT / "data" / "lake" / "_probe" / dest.name
            src = dest
            if probe.exists() and probe.stat().st_size > 1000:
                src = probe
                files_meta.append({"url": url, "file": str(probe), "via": "probe_cache", "bytes": probe.stat().st_size})
            elif dest.exists() and dest.stat().st_size > 1000:
                files_meta.append({"url": url, "file": dest.name, "via": "cache"})
            else:
                meta = download_bytes(url, dest)
                files_meta.append(meta)
                if meta.get("error"):
                    continue
                src = dest
            got = extract_file(src, year)
            if got:
                rows = got
                messages.append(f"Censo via {src.name}: {len(got)}")
                break

    if not rows:
        files_meta.extend(scrape_microdados_links(raw))
        for m in files_meta:
            if m.get("file") and not m.get("error"):
                p = Path(m["file"]) if Path(m["file"]).exists() else raw / Path(m["file"]).name
                if p.exists():
                    got = extract_file(p, year)
                    if got:
                        rows = got
                        break

    if rows:
        write_jsonl(out / "censo_escolar_extract.jsonl", rows)
    else:
        messages.append(
            "SKIPPED inep_censo: sem arquivo de matrículas. "
            "Defina ATLAS_CENSO_FILE=caminho.csv|xlsx|zip com QT_MAT_BAS "
            "(tx_rend não é usado)."
        )
        print(messages[-1], flush=True)

    write_json(
        out / "censo_meta.json",
        {
            "em": utc_now(),
            "fonte": "inep_censo",
            "year": year,
            "rows": len(rows),
            "files": files_meta,
            "messages": messages,
            "ingestion_run_id": run["ingestion_run_id"],
            "day": day_stamp(),
            "portal": MICRODADOS_PAGE,
        },
    )
    mark_ingested(
        "inep_censo",
        run_id=run["ingestion_run_id"],
        counts={"rows": len(rows)},
        ok=len(rows) > 0,
        error=None if rows else (messages[-1] if messages else "sem dados"),
        dataset_id="inep.censo_escolar",
    )
    print(f"OK INEP Censo: rows={len(rows)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
