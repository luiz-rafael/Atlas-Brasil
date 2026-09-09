"""Catálogo de tribunais — sem colisão STJ/TJ e TRT1/TRT12."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.connectors.cnj.compensation.courts import COURTS, match_court


class CourtMatchTests(unittest.TestCase):
    def test_catalog_size(self):
        self.assertGreaterEqual(len(COURTS), 90)

    def test_tjsp_from_path(self):
        c = match_court("tjsp/2024/03/contracheque.xlsx")
        self.assertIsNotNone(c)
        self.assertEqual(c.court_id, "tjsp")

    def test_stj_is_not_tj(self):
        c = match_court("planilha_STJ_2024.xlsx")
        self.assertIsNotNone(c)
        self.assertEqual(c.court_id, "stj")

    def test_trt12_not_trt1(self):
        c = match_court("TRT12_remuneracao_202401.xlsx")
        self.assertIsNotNone(c)
        self.assertEqual(c.court_id, "trt12")

    def test_tjdft(self):
        c = match_court("https://www.tjdft.jus.br/transparencia/magistrados.xlsx")
        self.assertIsNotNone(c)
        self.assertEqual(c.court_id, "tjdf")


if __name__ == "__main__":
    unittest.main()
