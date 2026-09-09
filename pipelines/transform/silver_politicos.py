#!/usr/bin/env python3
"""Bronze -> silver políticos (JSONL canônico)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_jsonl  # noqa: E402

SILVER = LAKE / "silver" / "politicos"


def latest_bronze(fonte: str, required_name: str | None = None) -> Path | None:
    """Prefere pasta dia YYYY-MM-DD com arquivo canônico; evita raw run-id vazio."""
    base = LAKE / "bronze" / fonte
    if not base.exists():
        return None
    dirs = [p for p in base.iterdir() if p.is_dir()]

    def score(p: Path) -> tuple:
        has_req = 0
        if required_name and (p / required_name).exists():
            has_req = 2
        elif required_name:
            stem = required_name.rsplit(".", 1)[0]
            if any(p.glob(f"{stem}_*.jsonl")) or any(p.glob(f"{stem}*.jsonl")):
                has_req = 1
        else:
            # TSE etc.: prefer pasta dia com pacotes, não só raw_index
            if any(x.is_dir() for x in p.iterdir()):
                has_req = 2
            elif any(p.glob("*.csv")) or any(p.glob("*.zip")):
                has_req = 1
        is_day = 1 if len(p.name) == 10 and p.name[4] == "-" else 0
        return (has_req, is_day, p.name)

    dirs.sort(key=score, reverse=True)
    return dirs[0] if dirs else None


def _jsonl_path(day_dir: Path, canonical: str) -> Path | None:
    p = day_dir / canonical
    if p.exists():
        return p
    stem = canonical.rsplit(".", 1)[0]
    cands = sorted(day_dir.glob(f"{stem}_*.jsonl"), reverse=True)
    if cands:
        return cands[0]
    cands = sorted(day_dir.glob(f"{stem}*.jsonl"), reverse=True)
    return cands[0] if cands else None


def norm_uf(u: str | None) -> str | None:
    if not u:
        return None
    u = str(u).strip().upper()
    return u[:2] if len(u) >= 2 else u


def from_camara(day_dir: Path) -> list[dict]:
    path = _jsonl_path(day_dir, "deputados.jsonl")
    if not path:
        return []
    out = []
    fetched = utc_now()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        did = d.get("id")
        if not did:
            continue
        out.append(
            {
                "id_externo": f"cam:{did}",
                "fonte": "camara_v2",
                "nome": d.get("nome") or d.get("nomeCivil") or "",
                "nome_urna": d.get("nome"),
                "partido_sigla": (d.get("siglaPartido") or "").upper() or None,
                "uf": norm_uf(d.get("siglaUf")),
                "cargo": "Deputado Federal",
                "em_exercicio": bool(d.get("_status_atual"))
                or (not d.get("_legislaturas")),
                "situacao": (
                    "exercicio"
                    if (
                        bool(d.get("_status_atual"))
                        or (not d.get("_legislaturas"))
                    )
                    else "historico"
                ),
                "legislaturas": d.get("_legislaturas"),
                "legislatura": d.get("idLegislatura") or (
                    max(d["_legislaturas"]) if d.get("_legislaturas") else None
                ),
                "eleicao_ano": None,
                "email": d.get("email"),
                "url_foto": d.get("urlFoto"),
                "url_fonte": d.get("uri") or f"https://dadosabertos.camara.leg.br/api/v2/deputados/{did}",
                "sexo": None,
                "data_nascimento": None,
                "municipio": None,
                "raw_ref": f"bronze/camara_v2/{day_dir.name}/{path.name}#{did}",
                "fetched_at": fetched,
            }
        )
    return out


def from_senado(day_dir: Path) -> list[dict]:
    path = _jsonl_path(day_dir, "senadores.jsonl")
    if not path:
        return []
    out = []
    fetched = utc_now()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        code = d.get("CodigoParlamentar")
        if not code:
            continue
        nome = d.get("NomeCompletoParlamentar") or d.get("NomeParlamentar") or ""
        out.append(
            {
                "id_externo": f"sen:{code}",
                "fonte": "senado_legis",
                "nome": nome,
                "nome_urna": d.get("NomeParlamentar"),
                "partido_sigla": (d.get("SiglaPartidoParlamentar") or "").upper() or None,
                "uf": norm_uf(d.get("UfParlamentar")),
                "cargo": "Senador",
                "situacao": "exercicio",
                "legislatura": None,
                "eleicao_ano": None,
                "email": d.get("EmailParlamentar"),
                "url_foto": d.get("UrlFotoParlamentar"),
                "url_fonte": d.get("UrlPaginaParlamentar")
                or f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{code}",
                "sexo": None,
                "data_nascimento": None,
                "municipio": None,
                "raw_ref": f"bronze/senado_legis/{day_dir.name}/{path.name}#{code}",
                "fetched_at": fetched,
            }
        )
    return out


def _find_cand_csvs(day_dir: Path) -> list[Path]:
    found = []
    for p in day_dir.rglob("*.csv"):
        name = p.name.lower()
        if "consulta_cand" in name or name.startswith("candidatos"):
            found.append(p)
        elif "cand" in name and "bem" not in name and "foto" not in name:
            found.append(p)
    return found


def from_tse(day_dir: Path, max_rows: int = 50000) -> list[dict]:
    """Lê CSVs TSE (latin-1 / ;). Filtra cargos federais quando possível."""
    csvs = _find_cand_csvs(day_dir)
    if not csvs:
        return []
    out = []
    fetched = utc_now()
    federal_cargos = {
        "PRESIDENTE",
        "VICE-PRESIDENTE",
        "GOVERNADOR",
        "VICE-GOVERNADOR",
        "SENADOR",
        "DEPUTADO FEDERAL",
        "DEPUTADO DISTRITAL",
        "DEPUTADO ESTADUAL",
    }
    # MVP: priorizar federal
    prefer = {"PRESIDENTE", "VICE-PRESIDENTE", "SENADOR", "DEPUTADO FEDERAL"}

    for csv_path in csvs:
        try:
            text = csv_path.read_text(encoding="latin-1")
        except Exception:
            text = csv_path.read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(text.splitlines(), delimiter=";")
        for row in reader:
            cargo = (row.get("DS_CARGO") or row.get("ds_cargo") or "").upper().strip()
            if cargo and cargo not in prefer:
                # ainda aceita se não houver filtro claro
                if cargo in federal_cargos and cargo not in prefer:
                    continue
                if cargo not in prefer and prefer:
                    # pular prefeito/vereador no MVP silver federal
                    if cargo in ("PREFEITO", "VICE-PREFEITO", "VEREADOR"):
                        continue
            sq = row.get("SQ_CANDIDATO") or row.get("sq_candidato")
            if not sq:
                continue
            nome = row.get("NM_CANDIDATO") or row.get("nm_candidato") or ""
            urna = row.get("NM_URNA_CANDIDATO") or row.get("nm_urna_candidato")
            partido = (
                row.get("SG_PARTIDO")
                or row.get("sg_partido")
                or row.get("NR_PARTIDO")
                or ""
            )
            uf = row.get("SG_UF") or row.get("sg_uf")
            ano = row.get("ANO_ELEICAO") or row.get("ano_eleicao")
            out.append(
                {
                    "id_externo": f"tse:{sq}",
                    "fonte": "tse_ckan",
                    "nome": nome,
                    "nome_urna": urna,
                    "partido_sigla": str(partido).upper() if partido else None,
                    "uf": norm_uf(uf),
                    "cargo": cargo.title() if cargo else None,
                    "situacao": row.get("DS_SIT_TOT_TURNO") or row.get("DS_SITUACAO_CANDIDATURA"),
                    "legislatura": None,
                    "eleicao_ano": int(ano) if ano and str(ano).isdigit() else None,
                    "email": None,
                    "url_foto": None,
                    "url_fonte": "https://dadosabertos.tse.jus.br/",
                    "sexo": row.get("DS_GENERO"),
                    "data_nascimento": row.get("DT_NASCIMENTO"),
                    "municipio": row.get("NM_UE") or row.get("NM_MUNICIPIO"),
                    "raw_ref": f"{csv_path.as_posix()}#{sq}",
                    "fetched_at": fetched,
                }
            )
            if len(out) >= max_rows:
                return out
    return out


def main() -> int:
    rows: list[dict] = []
    cam = latest_bronze("camara_v2", "deputados.jsonl")
    sen = latest_bronze("senado_legis", "senadores.jsonl")
    tse = latest_bronze("tse_ckan")

    if cam:
        c = from_camara(cam)
        print(f"silver camara: {len(c)} de {cam}")
        rows.extend(c)
    else:
        print("sem bronze camara_v2")

    if sen:
        s = from_senado(sen)
        print(f"silver senado: {len(s)} de {sen}")
        rows.extend(s)
    else:
        print("sem bronze senado_legis")

    if tse:
        import os

        max_rows = int(os.getenv("TSE_SILVER_MAX", "80000"))
        t = from_tse(tse, max_rows=max_rows)
        print(f"silver tse: {len(t)} de {tse}")
        rows.extend(t)
    else:
        print("sem bronze tse_ckan")

    SILVER.mkdir(parents=True, exist_ok=True)
    out = SILVER / f"politicos_{day_stamp()}.jsonl"
    latest = SILVER / "politicos_latest.jsonl"
    write_jsonl(out, rows)
    write_jsonl(latest, rows)
    print(f"OK silver: {len(rows)} -> {out}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
