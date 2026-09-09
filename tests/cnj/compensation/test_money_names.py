"""Testes de dinheiro e nomes — ausência não vira zero."""

from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.models.compensation.money import is_missing_amount, parse_amount
from src.models.compensation.names import looks_like_total_label, normalize_person_name, slug_header


class MoneyTests(unittest.TestCase):
    def test_missing_is_none_not_zero(self):
        for raw in (None, "", "-", "n/a", "Não informado", "—"):
            self.assertIsNone(parse_amount(raw), msg=repr(raw))
            self.assertTrue(is_missing_amount(raw))

    def test_explicit_zero(self):
        self.assertEqual(parse_amount(0), Decimal("0"))
        self.assertEqual(parse_amount("0,00"), Decimal("0.00"))
        self.assertEqual(parse_amount("0.00"), Decimal("0.00"))

    def test_brazilian_thousands(self):
        self.assertEqual(parse_amount("R$ 1.234.567,89"), Decimal("1234567.89"))

    def test_us_format(self):
        self.assertEqual(parse_amount("1234567.89"), Decimal("1234567.89"))

    def test_parentheses_negative(self):
        self.assertEqual(parse_amount("(10,50)"), Decimal("-10.50"))


class NameTests(unittest.TestCase):
    def test_strips_title(self):
        self.assertEqual(
            normalize_person_name("Desembargador João da Silva"),
            "JOAO DA SILVA",
        )

    def test_total_label(self):
        self.assertTrue(looks_like_total_label("TOTAL GERAL"))
        self.assertTrue(looks_like_total_label("Soma"))
        self.assertFalse(looks_like_total_label("Maria Totalina"))

    def test_slug_header(self):
        self.assertEqual(slug_header("Subsídio"), "subsidio")
        self.assertEqual(slug_header("Rendimento Líquido"), "rendimento_liquido")


if __name__ == "__main__":
    unittest.main()
