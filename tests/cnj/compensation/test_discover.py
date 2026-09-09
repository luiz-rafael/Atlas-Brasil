"""Descoberta HTML + inbox."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.connectors.cnj.compensation.discover import discover_from_html, infer_period, scan_inbox

HTML = """
<html><body>
<a href="https://www.tjsp.jus.br/transparencia/magistrados">TJSP Remuneração</a>
<a href="/wp-content/uploads/2024/03/contracheque-tjsp-2024-03.xlsx">Contracheque março 2024</a>
<a href="https://paineis.cnj.jus.br/foo">Painel</a>
</body></html>
"""


class DiscoverTests(unittest.TestCase):
    def test_portal_html_files_and_court_pages(self):
        files, pages = discover_from_html(
            HTML,
            "https://www.cnj.jus.br/transparencia-cnj/remuneracao-dos-magistrados/",
            page_role="cnj_portal",
        )
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["court_id"], "tjsp")
        self.assertEqual(files[0]["reference_year"], 2024)
        self.assertEqual(files[0]["reference_month"], 3)
        self.assertEqual(files[0]["original_source_url"].startswith("https://www.cnj.jus.br"), True)
        ids = {p["court_id"] for p in pages}
        self.assertIn("tjsp", ids)

    def test_infer_period_jul2026(self):
        y, m = infer_period("Transparencia_TRT7_Referente_Jul2026.ods")
        self.assertEqual((y, m), (2026, 7))

    def test_infer_period_compact_month_year(self):
        y, m = infer_period("ANEXO-VIII_072026_ATIVOS.ods")
        self.assertEqual((y, m), (2026, 7))

    def test_inbox_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest = base / "tjsp" / "2024" / "03"
            dest.mkdir(parents=True)
            (dest / "contracheque.xlsx").write_bytes(b"fake")
            found = scan_inbox(base)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["court_id"], "tjsp")
            self.assertEqual(found[0]["reference_year"], 2024)
            self.assertEqual(found[0]["reference_month"], 3)
            self.assertEqual(found[0]["origin"], "inbox")


if __name__ == "__main__":
    unittest.main()
