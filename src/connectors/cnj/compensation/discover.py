"""Descoberta de arquivos de remuneração de magistrados (portal CNJ + tribunais + inbox)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.common import http_get, utc_now  # noqa: E402
from src.connectors.cnj.compensation.courts import (  # noqa: E402
    CNJ_CORPORATIVO_URL,
    CNJ_PORTAL_URL,
    CNJ_QLIK_PANEL_URL,
    Court,
    match_court,
)
from src.models.compensation.names import slug_header  # noqa: E402

FILE_EXT = (".xlsx", ".xls", ".xlsm", ".ods", ".csv", ".zip")
FILE_HINTS = (
    "remuner",
    "magistr",
    "contracheque",
    "folha",
    "subsid",
    "indeniz",
    "verba",
    "pessoal",
    "eventua",
    "holerite",
    "portaria",
    "transparenc",
    "anexo",
)
YEAR_RE = re.compile(r"(20\d{2})")
YM_RE = re.compile(r"(20\d{2})[-_/]?(0[1-9]|1[0-2])")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._chunks).strip()))
            self._href = None
            self._chunks = []


def parse_links(html: str, base_url: str) -> list[dict[str, str]]:
    parser = _LinkParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, text in parser.links:
        abs_url = urljoin(base_url, href.strip())
        if abs_url in seen:
            continue
        seen.add(abs_url)
        out.append({"url": abs_url, "text": text or "", "path": urlparse(abs_url).path})
    return out


def _is_file_url(url: str, text: str = "") -> bool:
    path = urlparse(url).path.lower()
    blob = f"{path} {text}".lower()
    if any(path.endswith(ext) for ext in FILE_EXT):
        return True
    if "download" in blob and any(h in blob for h in FILE_HINTS):
        return True
    return False


def _looks_like_compensation(url: str, text: str = "") -> bool:
    blob = f"{url} {text}".lower()
    return any(h in blob for h in FILE_HINTS)


_MONTH_ABBR = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}
_ABBR_YEAR = re.compile(
    r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*[_-]?(20\d{2})",
    re.I,
)
_MY_COMPACT = re.compile(r"(?:^|[^\d])(0[1-9]|1[0-2])(20\d{2})(?:[^\d]|$)")


def infer_period(*texts: str | None) -> tuple[int | None, int | None]:
    blob = " ".join(t for t in texts if t) or ""
    compact = blob.replace(" ", "")
    ym = YM_RE.search(compact)
    if ym:
        return int(ym.group(1)), int(ym.group(2))
    my = _MY_COMPACT.search(compact)
    if my:
        return int(my.group(2)), int(my.group(1))
    abbr = _ABBR_YEAR.search(slug_header(blob))
    if abbr:
        return int(abbr.group(2)), _MONTH_ABBR[abbr.group(1).lower()[:3]]
    year = None
    years = YEAR_RE.findall(blob)
    if years:
        year = int(years[-1])
    month = None
    slug = slug_header(blob)
    for name, num in _MONTH_ABBR.items():
        if re.search(rf"(^|_){name}(_|$)", slug):
            month = num
            break
    return year, month


def _file_kind(url: str, text: str) -> str:
    blob = f"{url} {text}".lower()
    if "contracheque" in blob:
        return "contracheque"
    if "direito" in blob and "pessoal" in blob:
        return "personal_advantages"
    if "indeniz" in blob:
        return "indemnities"
    if "eventua" in blob:
        return "eventual_advantages"
    if "cadastr" in blob:
        return "cadastro"
    return "workbook"


def inbox_dir() -> Path:
    return Path(os.getenv("ATLAS_CNJ_COMP_INBOX") or ROOT / "data" / "inbox" / "cnj" / "compensation")


def scan_inbox(inbox: Path | None = None) -> list[dict]:
    base = inbox or inbox_dir()
    if not base.exists():
        return []
    found: list[dict] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in FILE_EXT:
            continue
        rel = path.relative_to(base).as_posix()
        parts = path.relative_to(base).parts
        court = match_court(rel, *parts)
        year, month = infer_period(rel, path.stem)
        if len(parts) >= 3 and parts[1].isdigit() and len(parts[1]) == 4:
            year = year or int(parts[1])
            if parts[2].isdigit():
                month = month or int(parts[2])
        found.append(
            {
                "kind": "local_file",
                "origin": "inbox",
                "url": path.as_uri(),
                "path": str(path),
                "filename": path.name,
                "court_id": court.court_id if court else None,
                "court_acronym": court.acronym if court else None,
                "original_source_url": None,
                "file_kind": _file_kind(path.name, rel),
                "reference_year": year,
                "reference_month": month,
                "text": rel,
            }
        )
    return found


def fetch_html(url: str, timeout: float = 45.0) -> tuple[str | None, str | None]:
    try:
        r = http_get(url, timeout=timeout)
        r.raise_for_status()
        return r.text, str(r.url)
    except Exception as exc:
        return None, str(exc)


def discover_from_html(
    html: str,
    page_url: str,
    *,
    default_court: Court | None = None,
    page_role: str,
) -> tuple[list[dict], list[dict]]:
    files: list[dict] = []
    pages: list[dict] = []
    for link in parse_links(html, page_url):
        url = link["url"]
        text = link["text"]
        court = match_court(url, text) or default_court
        if page_role != "cnj_portal":
            court = court or match_court(page_url) or default_court
        if _is_file_url(url, text) and _looks_like_compensation(url, text):
            year, month = infer_period(url, text, page_url)
            files.append(
                {
                    "kind": "remote_file",
                    "origin": page_role,
                    "url": url,
                    "path": None,
                    "filename": Path(urlparse(url).path).name or "download.bin",
                    "court_id": court.court_id if court else None,
                    "court_acronym": court.acronym if court else None,
                    "original_source_url": page_url,
                    "file_kind": _file_kind(url, text),
                    "reference_year": year,
                    "reference_month": month,
                    "text": text,
                }
            )
            continue
        if page_role == "cnj_portal" and court and url.rstrip("/") != CNJ_PORTAL_URL.rstrip("/"):
            if urlparse(url).scheme in ("http", "https"):
                pages.append(
                    {
                        "kind": "court_page",
                        "url": url,
                        "court_id": court.court_id,
                        "court_acronym": court.acronym,
                        "text": text,
                    }
                )
    return files, pages


SEED_COURT_PAGES = (
    {
        "url": (
            "https://www.trt7.jus.br/index.php?Itemid=931&catid=192"
            "&id=222%3Aanexo-viii-remuneracoes-e-diarias-pagas"
            "&option=com_content&showall=1&view=article"
        ),
        "court_id": "trt7",
        "court_acronym": "TRT7",
    },
    {
        "url": "https://www.tjes.jus.br/portal-transparencia/pessoal/folha-de-pagamento/",
        "court_id": "tjes",
        "court_acronym": "TJES",
    },
)


def wanted_period() -> tuple[int | None, int | None]:
    y = os.getenv("ATLAS_CNJ_COMP_YEAR", "").strip()
    m = os.getenv("ATLAS_CNJ_COMP_MONTH", "").strip()
    year = int(y) if y.isdigit() else None
    month = int(m) if m.isdigit() else None
    return year, month


def _matches_period(item: dict, year: int | None, month: int | None) -> bool:
    if year is None and month is None:
        return True
    iy, im = item.get("reference_year"), item.get("reference_month")
    if year is not None and iy not in (None, year):
        return False
    if month is not None and im not in (None, month):
        return False
    return True


def discover_sources(*, follow_courts: bool | None = None, max_court_pages: int | None = None) -> dict:
    """CHECK SOURCE + DISCOVER FILES."""
    if follow_courts is None:
        follow_courts = os.getenv("ATLAS_CNJ_COMP_FOLLOW_COURTS", "").lower() in (
            "1",
            "true",
            "yes",
        )
    if max_court_pages is None:
        max_court_pages = int(os.getenv("ATLAS_CNJ_COMP_MAX_COURT_PAGES", "12"))

    retrieved_at = utc_now()
    incompatibilities: list[dict] = []
    files: list[dict] = []
    court_pages: list[dict] = []

    html, final = fetch_html(CNJ_PORTAL_URL)
    portal_ok = bool(html)
    if not html:
        incompatibilities.append(
            {
                "code": "PORTAL_FETCH_FAILED",
                "detail": final,
                "url": CNJ_PORTAL_URL,
            }
        )
    else:
        portal_files, portal_pages = discover_from_html(
            html, final or CNJ_PORTAL_URL, page_role="cnj_portal"
        )
        files.extend(portal_files)
        court_pages.extend(portal_pages)
        low = html.lower()
        if "qlik" in low or "paineis.cnj" in low or "painel" in low:
            incompatibilities.append(
                {
                    "code": "QLIK_PANEL_NO_STABLE_URL",
                    "detail": (
                        "O CNJ apresenta os dados padronizados em painel Qlik/QlikSense, "
                        "sem URL lógica de download. Exportações do painel devem ir para "
                        "data/inbox/cnj/compensation/{tribunal}/{ano}/{mes}/."
                    ),
                    "url": CNJ_QLIK_PANEL_URL,
                }
            )

    incompatibilities.append(
        {
            "code": "CORPORATIVO_UPLOAD_NOT_PUBLIC",
            "detail": "Envio dos tribunais ocorre no sistema corporativo do CNJ, não como dump público.",
            "url": CNJ_CORPORATIVO_URL,
        }
    )

    if follow_courts:
        seen_pages: set[str] = set()
        for page in court_pages[: max(0, max_court_pages)]:
            url = page["url"]
            if url in seen_pages:
                continue
            seen_pages.add(url)
            page_html, page_final = fetch_html(url)
            if not page_html:
                incompatibilities.append(
                    {
                        "code": "COURT_PAGE_FETCH_FAILED",
                        "detail": page_final,
                        "url": url,
                        "court_id": page.get("court_id"),
                    }
                )
                continue
            court = match_court(page.get("court_id"), page.get("court_acronym"))
            extra_files, _ = discover_from_html(
                page_html,
                page_final or url,
                default_court=court,
                page_role="court_portal",
            )
            for item in extra_files:
                item["original_source_url"] = url
                files.append(item)

    use_seed = os.getenv("ATLAS_CNJ_COMP_SEED_PAGES", "1").lower() not in ("0", "false", "no")
    if use_seed:
        seen_seed: set[str] = set()
        for page in SEED_COURT_PAGES:
            url = page["url"]
            if url in seen_seed:
                continue
            seen_seed.add(url)
            page_html, page_final = fetch_html(url)
            if not page_html:
                incompatibilities.append(
                    {
                        "code": "COURT_PAGE_FETCH_FAILED",
                        "detail": page_final,
                        "url": url,
                        "court_id": page.get("court_id"),
                    }
                )
                continue
            court = match_court(page.get("court_id"), page.get("court_acronym"))
            extra_files, _ = discover_from_html(
                page_html,
                page_final or url,
                default_court=court,
                page_role="court_portal",
            )
            for item in extra_files:
                item["original_source_url"] = url
                if not item.get("court_id"):
                    item["court_id"] = page.get("court_id")
                    item["court_acronym"] = page.get("court_acronym")
                files.append(item)

    inbox_files = scan_inbox()
    files.extend(inbox_files)

    year_f, month_f = wanted_period()
    uniq: list[dict] = []
    seen: set[str] = set()
    for item in files:
        blob = f"{item.get('filename') or ''} {item.get('url') or ''} {item.get('text') or ''}".lower()
        if "colaborador" in blob:
            continue
        if blob.endswith(".pdf") or str(item.get("filename") or "").lower().endswith(".pdf"):
            continue
        if not _matches_period(item, year_f, month_f):
            continue
        key = item.get("path") or item.get("url") or json.dumps(item, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)

    fingerprint_src = json.dumps(
        [
            {
                "url": i.get("url"),
                "path": i.get("path"),
                "court_id": i.get("court_id"),
                "year": i.get("reference_year"),
                "month": i.get("reference_month"),
            }
            for i in uniq
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    listing_hash = hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest()

    return {
        "source_id": "cnj_magistrate_compensation",
        "dataset_id": "cnj_magistrate_compensation",
        "portal_url": CNJ_PORTAL_URL,
        "qlik_panel_url": CNJ_QLIK_PANEL_URL,
        "retrieved_at": retrieved_at,
        "portal_ok": portal_ok,
        "listing_hash": listing_hash,
        "files": uniq,
        "court_pages": court_pages,
        "incompatibilities": incompatibilities,
        "counts": {
            "files": len(uniq),
            "inbox": sum(1 for i in uniq if i.get("origin") == "inbox"),
            "remote": sum(1 for i in uniq if i.get("kind") == "remote_file"),
            "court_pages": len(court_pages),
        },
    }
