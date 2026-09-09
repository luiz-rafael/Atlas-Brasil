"""Leitura tabular + fingerprint de layout (Portaria 63 vs variante de tribunal)."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Iterable

from src.models.compensation.names import slug_header

KNOWN_ID_HEADERS = {
    "cpf",
    "nome",
    "cargo",
    "lotacao",
    "matricula",
    "magistrado",
}
KNOWN_MONEY_HEADERS = {
    "subsidio",
    "direitos_pessoais",
    "indenizacoes",
    "direitos_eventuais",
    "total_de_rendimentos",
    "total_de_descontos",
    "rendimento_liquido",
    "imposto_de_renda",
    "previdencia_publica",
    "descontos_previdencia_publica",
    "retencao_por_teto_constitucional",
    "pagamentos_retroativos",
}

HEADER_ALIASES: dict[str, str] = {
    "cpf": "cpf",
    "cpf_mascarado": "cpf",
    "nome": "nome",
    "nome_do_magistrado": "nome",
    "magistrado": "nome",
    "servidor": "nome",
    "cargo": "cargo",
    "funcao": "cargo",
    "função": "cargo",
    "cargo_efetivo": "cargo",
    "denominacao_do_cargo": "cargo",
    "descricao_do_cargo": "cargo",
    "lotacao": "lotacao",
    "lotação": "lotacao",
    "unidade": "lotacao",
    "matricula": "matricula",
    "matrícula": "matricula",
    "subsidio": "subsidio",
    "subsídio": "subsidio",
    "vencimento_basico": "subsidio",
    "vencimento_básico": "subsidio",
    "direitos_pessoais": "direitos_pessoais",
    "vantagens_pessoais": "direitos_pessoais",
    "indenizacoes": "indenizacoes",
    "indenizações": "indenizacoes",
    "verbas_indenizatorias": "indenizacoes",
    "direitos_eventuais": "direitos_eventuais",
    "vantagens_eventuais": "direitos_eventuais",
    "total_de_rendimentos": "total_de_rendimentos",
    "rendimentos_brutos": "total_de_rendimentos",
    "rendimento_bruto": "total_de_rendimentos",
    "total_bruto": "total_de_rendimentos",
    "bruto": "total_de_rendimentos",
    "descontos_previdencia_publica": "descontos_previdencia_publica",
    "previdencia_publica": "descontos_previdencia_publica",
    "previdencia": "descontos_previdencia_publica",
    "imposto_de_renda": "imposto_de_renda",
    "irrf": "imposto_de_renda",
    "ir": "imposto_de_renda",
    "descontos_diversos": "descontos_diversos",
    "retencao_por_teto_constitucional": "retencao_por_teto_constitucional",
    "retencao_teto": "retencao_por_teto_constitucional",
    "teto_constitucional": "retencao_por_teto_constitucional",
    "total_de_descontos": "total_de_descontos",
    "descontos": "total_de_descontos",
    "rendimento_liquido": "rendimento_liquido",
    "liquido": "rendimento_liquido",
    "líquido": "rendimento_liquido",
    "remuneracao_do_orgao_de_origem": "remuneracao_do_orgao_de_origem",
    "orgao_de_origem": "remuneracao_do_orgao_de_origem",
    "diarias": "diarias",
    "diárias": "diarias",
    "remuneracao_basica": "subsidio",
    "remuneracao_básica": "subsidio",
    "remuneracao_paradigma": "subsidio",
    "vencimento": "subsidio",
    "vencimentos": "subsidio",
    "total_da_remuneracao": "total_de_rendimentos",
    "total_remuneracao": "total_de_rendimentos",
    "remuneracao_bruta": "total_de_rendimentos",
    "remuneracao_liquida": "rendimento_liquido",
    "remuneracao_líquida": "rendimento_liquido",
    "categoria": "categoria",
    "vinculo": "vinculo",
    "vínculo": "vinculo",
    "tipo": "tipo",
    "pagamentos_retroativos": "pagamentos_retroativos",
    "pagamento_retroativo": "pagamentos_retroativos",
    "retroativos": "pagamentos_retroativos",
    "mes": "mes",
    "mês": "mes",
    "ano": "ano",
    "competencia": "competencia",
    "competência": "competencia",
}


def canonical_header(raw: str) -> str:
    slug = slug_header(raw)
    if slug in HEADER_ALIASES:
        return HEADER_ALIASES[slug]
    # Anexo VIII: "Nome/Servidores", "Indenizações (III)", "Rendimento Líquido (12)"
    stripped = re.sub(r"_(i{1,3}|iv|v|vi{0,3}|ix|x|\d+)$", "", slug)
    stripped = stripped.replace("nome_servidores", "nome").replace("nome_membro", "nome")
    if stripped in HEADER_ALIASES:
        return HEADER_ALIASES[stripped]
    for prefix, canon in (
        ("nome_servidor", "nome"),
        ("nome_membro", "nome"),
        ("vantagens_pessoais", "direitos_pessoais"),
        ("indenizacoes", "indenizacoes"),
        ("vantagens_eventuais", "direitos_eventuais"),
        ("total_de_creditos", "total_de_rendimentos"),
        ("total_de_debitos", "total_de_descontos"),
        ("previdencia_publica", "descontos_previdencia_publica"),
        ("imposto_de_renda", "imposto_de_renda"),
        ("descontos_diversos", "descontos_diversos"),
        ("retencao_por_teto", "retencao_por_teto_constitucional"),
        ("rendimento_liquido", "rendimento_liquido"),
        ("remuneracao_do_orgao", "remuneracao_do_orgao_de_origem"),
        ("subsidio", "subsidio"),
        ("remuneracao_paradigma", "remuneracao_paradigma"),
        ("diarias", "diarias"),
    ):
        if stripped.startswith(prefix) or slug.startswith(prefix):
            return canon
    for prefix, canon in HEADER_ALIASES.items():
        if slug == slug_header(prefix):
            return canon
    return slug


def header_score(headers: Iterable[str]) -> tuple[float, set[str]]:
    mapped = {canonical_header(h) for h in headers if h}
    known = (KNOWN_ID_HEADERS | KNOWN_MONEY_HEADERS)
    hit = mapped & known
    if not mapped:
        return 0.0, hit
    return len(hit) / max(len(known), 1), hit


def _cells_to_str(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for v in values:
        if v is None:
            out.append("")
        else:
            out.append(str(v).strip())
    return out


def find_header_row(rows: list[list[Any]], max_scan: int = 25) -> int | None:
    best_i = None
    best_score = 0.0
    limit = min(len(rows), max_scan)
    for i in range(limit):
        cells = _cells_to_str(rows[i])
        nonempty = [c for c in cells if c]
        if len(nonempty) < 3:
            continue
        score, _ = header_score(nonempty)
        # também aceita se tiver nome+cpf ou nome+subsidio
        mapped = {canonical_header(c) for c in nonempty}
        if "nome" in mapped and score > best_score:
            best_score = score
            best_i = i
        elif score > best_score:
            best_score = score
            best_i = i
    if best_i is None or best_score < 0.08:
        return None
    return best_i


def sheet_kind(name: str) -> str:
    slug = slug_header(name)
    if "contracheque" in slug or slug in {"folha", "remuneracao"}:
        return "contracheque"
    if "cadastr" in slug:
        return "cadastro"
    if "indeniz" in slug:
        return "indemnities"
    if "eventua" in slug:
        return "eventual_advantages"
    if "pesso" in slug or "dir_pes" in slug:
        return "personal_advantages"
    return "unknown"


def detect_layout(headers: list[str], *, sheet_name: str | None = None) -> dict[str, Any]:
    mapped = [canonical_header(h) for h in headers if h]
    score, hit = header_score(headers)
    kind = sheet_kind(sheet_name or "")
    fingerprint = "|".join(sorted(set(mapped)))
    if score >= 0.28 and ("nome" in mapped or "cpf" in mapped):
        layout_id = "cnj_portaria_63" if kind != "unknown" or "subsidio" in mapped else "contracheque_wide"
        if "subsidio" in mapped and "total_de_rendimentos" in mapped:
            layout_id = "cnj_portaria_63"
        confidence = "high" if score >= 0.4 else "medium"
    elif "nome" in mapped and score >= 0.12:
        layout_id = "generic_tabular"
        confidence = "low"
    else:
        layout_id = "unknown"
        confidence = "none"
    return {
        "layout_id": layout_id,
        "sheet_kind": kind,
        "score": round(score, 4),
        "confidence": confidence,
        "mapped_headers": mapped,
        "known_hits": sorted(hit),
        "fingerprint": fingerprint,
    }


def read_xlsx_sheets(path: Path) -> list[dict[str, Any]]:
    try:
        import openpyxl
    except ImportError as e:
        raise RuntimeError("openpyxl é necessário para planilhas CNJ") from e
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets: list[dict[str, Any]] = []
    try:
        for ws in wb.worksheets:
            rows: list[list[Any]] = []
            for row in ws.iter_rows(values_only=True):
                rows.append(list(row))
            sheets.append({"name": ws.title, "rows": rows})
    finally:
        wb.close()
    return sheets


def read_ods_sheets(path: Path) -> list[dict[str, Any]]:
    """Lê ODS via iterparse (stdlib). Evita ET.fromstring em XMLs de vários MB."""
    import zipfile
    from xml.etree import ElementTree as ET

    TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table"
    ROW = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-row"
    CELL = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-cell"
    COVERED = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}covered-table-cell"
    P = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p"
    NAME_ATTR = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name"
    ROWS_REP = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}number-rows-repeated"
    COLS_REP = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}number-columns-repeated"
    VALUE_ATTR = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}value"
    MAX_COLS = 60
    MAX_ROWS = 6000

    sheets: list[dict[str, Any]] = []
    cur_name = "Sheet"
    cur_rows: list[list[Any]] = []
    in_table = False

    def flush() -> None:
        nonlocal cur_rows, cur_name
        if in_table:
            sheets.append({"name": cur_name, "rows": cur_rows})
        cur_rows = []

    with zipfile.ZipFile(path) as zf:
        with zf.open("content.xml") as fh:
            for event, elem in ET.iterparse(fh, events=("start", "end")):
                tag = elem.tag
                if event == "start" and tag == TABLE:
                    flush()
                    in_table = True
                    cur_name = elem.attrib.get(NAME_ATTR) or f"Sheet{len(sheets)+1}"
                    cur_rows = []
                elif event == "end" and tag == ROW and in_table:
                    if len(cur_rows) >= MAX_ROWS:
                        elem.clear()
                        continue
                    row_repeat = int(elem.attrib.get(ROWS_REP) or 1)
                    if row_repeat > 1:
                        # Linhas vazias repetidas em ODS — ignora
                        elem.clear()
                        continue
                    cells: list[Any] = []
                    for child in elem:
                        if child.tag not in (CELL, COVERED):
                            continue
                        if len(cells) >= MAX_COLS:
                            break
                        repeat = min(int(child.attrib.get(COLS_REP) or 1), MAX_COLS - len(cells))
                        value = child.attrib.get(VALUE_ATTR)
                        if value is None:
                            texts = []
                            for p in child.iter(P):
                                t = "".join(p.itertext()).strip()
                                if t:
                                    texts.append(t)
                            value = " ".join(texts) or None
                        if value is None and repeat > 1:
                            # expansões vazias não ajudam o parse
                            cells.append(None)
                        else:
                            cells.extend([value] * repeat)
                    if any(v not in (None, "") for v in cells):
                        cur_rows.append(cells[:MAX_COLS])
                    elem.clear()
                elif event == "end" and tag == TABLE:
                    flush()
                    in_table = False
                    elem.clear()
    if in_table:
        flush()
    return sheets


def read_csv_rows(path: Path) -> list[list[Any]]:
    data = path.read_bytes()
    text = None
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError as e:
            last_err = e
            continue
    if text is None:
        raise UnicodeDecodeError("utf-8", data[:8], 0, 1, str(last_err))
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    return [list(r) for r in reader]


def rows_to_dicts(rows: list[list[Any]]) -> tuple[list[dict[str, Any]], list[str], int | None]:
    header_i = find_header_row(rows)
    if header_i is None:
        return [], [], None
    headers_raw = _cells_to_str(rows[header_i])
    headers: list[str] = []
    for i, h in enumerate(headers_raw):
        headers.append(canonical_header(h) if h else f"col_{i}")
    # desduplica nomes
    seen: dict[str, int] = {}
    uniq: list[str] = []
    for h in headers:
        n = seen.get(h, 0)
        seen[h] = n + 1
        uniq.append(h if n == 0 else f"{h}_{n+1}")
    records: list[dict[str, Any]] = []
    for row in rows[header_i + 1 :]:
        cells = list(row) + [None] * max(0, len(uniq) - len(row))
        rec = {uniq[i]: cells[i] for i in range(len(uniq))}
        if any(v not in (None, "") for v in rec.values()):
            records.append(rec)
    return records, uniq, header_i


def read_tabular(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    encoding_ok = True
    encoding_error = None
    sheets: list[dict[str, Any]]
    if suffix == ".csv":
        try:
            rows = read_csv_rows(path)
        except UnicodeDecodeError as e:
            return {
                "ok": False,
                "reason": "ENCODING_ERROR",
                "error": str(e),
                "sheets": [],
            }
        sheets = [{"name": path.stem, "rows": rows}]
    elif suffix in {".xlsx", ".xlsm"}:
        try:
            sheets = read_xlsx_sheets(path)
        except Exception as e:
            return {
                "ok": False,
                "reason": "UNSUPPORTED_FORMAT",
                "error": str(e),
                "sheets": [],
            }
    elif suffix == ".xls":
        # BIFF antigo — openpyxl não lê; xlrd opcional
        try:
            import xlrd  # type: ignore
        except ImportError:
            return {
                "ok": False,
                "reason": "UNSUPPORTED_FORMAT",
                "error": "arquivo .xls (BIFF) exige xlrd; pule ou converta para xlsx/ods",
                "sheets": [],
            }
        book = xlrd.open_workbook(path)
        sheets = []
        for sheet in book.sheets():
            rows = [sheet.row_values(i) for i in range(sheet.nrows)]
            sheets.append({"name": sheet.name, "rows": rows})
    elif suffix == ".ods":
        try:
            sheets = read_ods_sheets(path)
        except Exception as e:
            return {
                "ok": False,
                "reason": "UNSUPPORTED_FORMAT",
                "error": f"ods inválido: {e}",
                "sheets": [],
            }
    else:
        return {
            "ok": False,
            "reason": "UNSUPPORTED_FORMAT",
            "error": f"extensão não suportada: {suffix}",
            "sheets": [],
        }

    parsed_sheets = []
    for sheet in sheets:
        records, headers, header_i = rows_to_dicts(sheet["rows"])
        layout = detect_layout(headers, sheet_name=sheet["name"]) if headers else {
            "layout_id": "unknown",
            "sheet_kind": sheet_kind(sheet["name"]),
            "score": 0.0,
            "confidence": "none",
            "mapped_headers": [],
            "known_hits": [],
            "fingerprint": "",
        }
        parsed_sheets.append(
            {
                "name": sheet["name"],
                "header_row": header_i,
                "headers": headers,
                "records": records,
                "layout": layout,
                "n_rows": len(records),
                "n_raw_rows": len(sheet["rows"]),
            }
        )
    empty = all(s["n_rows"] == 0 and s["n_raw_rows"] <= 1 for s in parsed_sheets)
    return {
        "ok": True,
        "encoding_ok": encoding_ok,
        "encoding_error": encoding_error,
        "empty": empty,
        "sheets": parsed_sheets,
    }
