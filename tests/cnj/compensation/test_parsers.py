"""Parsers Portaria 63 + linhas de total + schema."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.pipelines.cnj.compensation.parsers.detect import detect_layout, read_tabular
from src.pipelines.cnj.compensation.parsers.generic import parse_generic_sheet
from src.pipelines.cnj.compensation.parsers.totals import is_total_row


def _write_cnj_xlsx(path: Path) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contracheque"
    ws.append(["Documento padrão CNJ — instruções, não usar esta linha"])
    ws.append([])
    ws.append(
        [
            "CPF",
            "Nome",
            "Cargo",
            "Lotação",
            "Subsídio",
            "Direitos Pessoais",
            "Indenizações",
            "Direitos Eventuais",
            "Total de Rendimentos",
            "Descontos Previdência Pública",
            "Imposto de Renda",
            "Descontos Diversos",
            "Retenção por Teto Constitucional",
            "Total de Descontos",
            "Rendimento Líquido",
        ]
    )
    ws.append(
        [
            "***123.456-**",
            "Juiz Maria Souza",
            "Juiz de Direito",
            "1ª Vara",
            "33743.00",
            "1000,00",
            "",
            "500,00",
            "35243.00",
            "3000",
            "5000",
            "-",
            "0,00",
            "8000",
            "27243.00",
        ]
    )
    ws.append(["", "TOTAL GERAL", "", "", 33743, 1000, 0, 500, 35243, 3000, 5000, 0, 0, 8000, 27243])

    wp = wb.create_sheet("Direitos Eventuais")
    wp.append(["CPF", "Nome", "Gratificação natalina", "Pagamentos retroativos", "Total"])
    wp.append(["***123.456-**", "Maria Souza", 0, "200,00", 200])
    wb.save(path)
    wb.close()


class ParserTests(unittest.TestCase):
    def test_total_row(self):
        self.assertTrue(is_total_row({"nome": "TOTAL GERAL", "subsidio": 1}))
        self.assertFalse(is_total_row({"nome": "Maria Souza", "cpf": "1", "subsidio": 1}))

    def test_xlsx_portaria_63(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("openpyxl ausente")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cnj.xlsx"
            _write_cnj_xlsx(path)
            parsed = read_tabular(path)
            self.assertTrue(parsed["ok"])
            contra = next(s for s in parsed["sheets"] if s["name"] == "Contracheque")
            self.assertEqual(contra["layout"]["layout_id"], "cnj_portaria_63")
            self.assertGreaterEqual(contra["layout"]["score"], 0.28)
            people = [r for r in contra["records"] if not is_total_row(r)]
            self.assertEqual(len(people), 1)
            rows = parse_generic_sheet(
                people,
                contra["layout"],
                court_id="tjsp",
                year=2024,
                month=3,
                raw_record_id="raw_test",
            )
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["normalized_name"], "MARIA SOUZA")
            self.assertEqual(row["base_subsidy"], 33743.0)
            self.assertIsNone(row["indemnities"])  # campo vazio não vira zero
            self.assertEqual(row["gross_total"], 35243.0)
            self.assertEqual(row["net_total"], 27243.0)
            self.assertEqual(row["discounts"], 8000.0)

            eventuais = next(s for s in parsed["sheets"] if "Eventuais" in s["name"])
            ev_rows = parse_generic_sheet(
                eventuais["records"],
                eventuais["layout"],
                court_id="tjsp",
                year=2024,
                month=3,
                raw_record_id="raw_test",
            )
            self.assertEqual(len(ev_rows), 1)
            codes = {c["component_code"] for c in ev_rows[0]["components"]}
            self.assertTrue(any("retroativ" in c for c in codes))

    def test_schema_changed(self):
        layout = detect_layout(["foo", "bar", "baz"], sheet_name="Plan1")
        self.assertEqual(layout["layout_id"], "unknown")
        self.assertEqual(layout["confidence"], "none")


if __name__ == "__main__":
    unittest.main()
