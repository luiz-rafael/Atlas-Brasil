#!/usr/bin/env python3
"""Silver F1: bens TSE, contratos PNCP, orgaos Camara, transferencias."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.common import LAKE, day_stamp, utc_now, write_jsonl  # noqa: E402

SILVER = LAKE / "silver"


def latest_bronze(fonte: str) -> Path | None:
    """Prefere pasta do dia (YYYY-MM-DD) com dados; senão a mais recente por mtime."""
    base = LAKE / "bronze" / fonte
    if not base.exists():
        return None
    dirs = [p for p in base.iterdir() if p.is_dir()]
    if not dirs:
        return None
    day_dirs = [p for p in dirs if len(p.name) == 10 and p.name[4] == "-"]
    if day_dirs:
        return max(day_dirs, key=lambda p: p.name)
    return max(dirs, key=lambda p: p.stat().st_mtime)


def only_digits(s: str | None) -> str | None:
    if not s:
        return None
    d = re.sub(r"\D", "", str(s))
    return d or None


def silver_bens(max_rows: int = 30000) -> list[dict]:
    day = latest_bronze("tse_bens")
    if not day:
        return []
    rows = []
    for csv_path in day.rglob("*.csv"):
        if "bem" not in csv_path.name.lower() and "bem" not in str(csv_path.parent).lower():
            # ainda tenta
            pass
        try:
            text = csv_path.read_text(encoding="latin-1")
        except Exception:
            continue
        reader = csv.DictReader(text.splitlines(), delimiter=";")
        for row in reader:
            sq = row.get("SQ_CANDIDATO") or row.get("sq_candidato")
            if not sq:
                continue
            rows.append(
                {
                    "id_externo": f"tse_bem:{sq}:{row.get('NR_ORDEM_BEM_CANDIDATO') or len(rows)}",
                    "fonte": "tse_bens",
                    "sq_candidato": sq,
                    "person_id": f"p_tse_{sq}",
                    "tipo_bem": row.get("DS_TIPO_BEM_CANDIDATO") or row.get("DS_BEM"),
                    "descricao": row.get("DS_BEM_CANDIDATO") or row.get("DS_BEM"),
                    "valor": _float(row.get("VR_BEM_CANDIDATO") or row.get("VR_BEM")),
                    "fetched_at": utc_now(),
                }
            )
            if len(rows) >= max_rows:
                return rows
    return rows


def _float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if "," in str(v) else float(v)
    except Exception:
        try:
            return float(str(v).replace(",", "."))
        except Exception:
            return None


def _iter_jsonl_rows(path: Path):
    """Aceita jsonl linha-a-linha ou um único JSON array (raw_record)."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return
    if text.startswith("["):
        data = json.loads(text)
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    yield row
            return
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            yield row
        elif isinstance(row, list):
            for x in row:
                if isinstance(x, dict):
                    yield x


def _pncp_contratos_path(day: Path) -> Path | None:
    direct = day / "contratos.jsonl"
    if direct.exists():
        return direct
    cands = sorted(
        day.glob("contratos_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return cands[0] if cands else None


def silver_contratos() -> list[dict]:
    day = latest_bronze("pncp")
    if not day:
        return []
    path = _pncp_contratos_path(day)
    if not path:
        return []
    out = []
    for row in _iter_jsonl_rows(path):
        orgao = row.get("orgaoEntidade") or row.get("nomeOrgao") or row.get("razaoSocial")
        orgao_cnpj = None
        if isinstance(orgao, dict):
            orgao_cnpj = only_digits(orgao.get("cnpj"))
            orgao = orgao.get("razaoSocial") or orgao.get("nome") or orgao.get("cnpj")
        cnpj = only_digits(
            row.get("niFornecedor")
            or row.get("cnpj")
            or row.get("cpfFormatado")
            or row.get("niFornecedorContrato")
        )
        num = (
            row.get("numeroControlePNCP")
            or row.get("numeroControlePncpCompra")
            or row.get("numeroContratoEmpenho")
            or row.get("id")
            or f"idx{len(out)}"
        )
        compra = row.get("numeroControlePncpCompra")
        nome_forn = row.get("nomeRazaoSocialFornecedor") or row.get("nomeFornecedor")
        uf = None
        uo = row.get("unidadeOrgao")
        if isinstance(uo, dict):
            uf = uo.get("ufNome") or uo.get("uf") or uo.get("siglaUf")
        out.append(
            {
                "id_externo": f"pncp:{num}",
                "fonte": "pncp",
                "numero": str(num),
                "compra_pncp": str(compra) if compra else None,
                "objeto": row.get("objetoContrato") or row.get("objeto") or row.get("titulo"),
                "valor": _float(
                    row.get("valorGlobal")
                    or row.get("valorInicial")
                    or row.get("valor")
                ),
                "cnpj": cnpj,
                "nome_fornecedor": nome_forn,
                "orgao": orgao,
                "orgao_cnpj": orgao_cnpj,
                "uf": uf or row.get("uf") or row.get("siglaUf"),
                "data": row.get("dataAssinatura") or row.get("dataPublicacaoPncp"),
                "emenda_parlamentar": bool(row.get("emendaParlamentar")),
                "raw_ref": f"bronze/pncp/{day.name}",
                "fetched_at": utc_now(),
            }
        )
    return out


def silver_orgaos() -> tuple[list[dict], list[dict]]:
    day = latest_bronze("camara_orgaos")
    if not day:
        return [], []
    orgaos = []
    membros = []
    op = day / "orgaos.jsonl"
    if op.exists():
        for line in op.read_text(encoding="utf-8").splitlines():
            if line.strip():
                o = json.loads(line)
                oid = o.get("id")
                if not oid:
                    continue
                orgaos.append(
                    {
                        "id_externo": f"cam_org:{oid}",
                        "fonte": "camara_orgaos",
                        "nome": o.get("nome") or o.get("sigla"),
                        "sigla": o.get("sigla"),
                        "tipo": o.get("tipoOrgao") or o.get("nomeTipoOrgao"),
                        "fetched_at": utc_now(),
                    }
                )
    fp = day / "frentes.jsonl"
    if fp.exists():
        for line in fp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                o = json.loads(line)
                oid = o.get("id")
                if not oid:
                    continue
                orgaos.append(
                    {
                        "id_externo": f"cam_frente:{oid}",
                        "fonte": "camara_orgaos",
                        "nome": o.get("titulo") or o.get("nome"),
                        "sigla": None,
                        "tipo": "Frente Parlamentar",
                        "fetched_at": utc_now(),
                    }
                )
    mp = day / "frente_membros.jsonl"
    if mp.exists():
        for line in mp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                m = json.loads(line)
                did = m.get("id") or (m.get("deputado_") or {}).get("id")
                if not did:
                    continue
                membros.append(
                    {
                        "person_id": f"p_cam_{did}",
                        "org_id": f"cam_frente:{m.get('_frente_id')}",
                        "titulo": m.get("_frente_titulo"),
                        "fonte": "camara_orgaos",
                    }
                )
    return orgaos, membros


def silver_transferencias() -> list[dict]:
    day = latest_bronze("transferegov")
    if not day:
        return []
    path = day / "transferencias.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "id_externo": f"tg:{row.get('id') or row.get('codigo') or len(out)}",
                "fonte": "transferegov",
                "nome": (
                    row.get("nome")
                    or row.get("nm_programa")
                    or row.get("descricao")
                    or row.get("titulo")
                    or row.get("cd_programa")
                ),
                "valor": _float(
                    row.get("valor")
                    or row.get("valorRepasse")
                    or row.get("vl_global_programa")
                    or row.get("vl_total_planejamento_gastos")
                ),
                "uf": row.get("uf") or row.get("siglaUf") or row.get("sg_uf_recebedor"),
                "cnpj": only_digits(
                    row.get("cnpj")
                    or row.get("cnpjBeneficiario")
                    or row.get("cnpj_ente_recebedor")
                    or row.get("cnpj_proponente")
                ),
                "fetched_at": utc_now(),
            }
        )
    return out


def main() -> int:
    bens = silver_bens()
    contratos = silver_contratos()
    orgaos, membros = silver_orgaos()
    transf = silver_transferencias()

    (SILVER / "bens").mkdir(parents=True, exist_ok=True)
    (SILVER / "contratos").mkdir(parents=True, exist_ok=True)
    (SILVER / "orgaos").mkdir(parents=True, exist_ok=True)
    (SILVER / "transferencias").mkdir(parents=True, exist_ok=True)

    stamp = day_stamp()
    write_jsonl(SILVER / "bens" / f"bens_{stamp}.jsonl", bens)
    write_jsonl(SILVER / "bens" / "bens_latest.jsonl", bens)
    write_jsonl(SILVER / "contratos" / f"contratos_{stamp}.jsonl", contratos)
    write_jsonl(SILVER / "contratos" / "contratos_latest.jsonl", contratos)
    write_jsonl(SILVER / "orgaos" / f"orgaos_{stamp}.jsonl", orgaos)
    write_jsonl(SILVER / "orgaos" / "orgaos_latest.jsonl", orgaos)
    write_jsonl(SILVER / "orgaos" / "membros_latest.jsonl", membros)
    write_jsonl(SILVER / "transferencias" / "transferencias_latest.jsonl", transf)

    print(
        f"OK silver F1: bens={len(bens)} contratos={len(contratos)} "
        f"orgaos={len(orgaos)} membros={len(membros)} transf={len(transf)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
