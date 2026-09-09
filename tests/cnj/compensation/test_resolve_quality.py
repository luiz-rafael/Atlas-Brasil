"""Resolução de magistrado e quality checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.pipelines.cnj.compensation.normalize import normalize_rows
from src.pipelines.cnj.compensation.quality import run_quality
from src.pipelines.cnj.compensation.resolve import resolve_magistrates


def _row(**kwargs):
    base = {
        "row_key": "k",
        "court_id": "tjsp",
        "normalized_name": "JOAO SILVA",
        "display_name": "João Silva",
        "source_person_identifier": None,
        "position": "Juiz",
        "reference_year": 2024,
        "reference_month": 3,
        "base_subsidy": 100.0,
        "gross_total": 150.0,
        "discounts": 20.0,
        "net_total": 130.0,
        "components": [],
        "raw_record_id": "raw1",
        "layout_id": "cnj_portaria_63",
    }
    base.update(kwargs)
    return base


class ResolveTests(unittest.TestCase):
    def test_same_name_different_courts_are_distinct(self):
        a = _row(row_key="a", court_id="tjsp")
        b = _row(row_key="b", court_id="tjrj")
        n = normalize_rows([a, b], retrieved_at="2026-01-01T00:00:00+00:00")
        r = resolve_magistrates(n["compensations"])
        ids = {m["court_id"]: m["magistrate_id"] for m in r["magistrates"]}
        self.assertNotEqual(ids["tjsp"], ids["tjrj"])
        self.assertEqual(len(r["magistrates"]), 2)

    def test_official_id_beats_name(self):
        a = _row(row_key="a", source_person_identifier="***111***")
        b = _row(row_key="b", source_person_identifier="***222***")
        n = normalize_rows([a, b], retrieved_at="2026-01-01T00:00:00+00:00")
        r = resolve_magistrates(n["compensations"])
        self.assertEqual(len(r["magistrates"]), 2)
        methods = {m["resolution_method"] for m in r["magistrates"]}
        self.assertEqual(methods, {"court_official_identifier"})

    def test_ambiguous_without_id_and_distinct_positions(self):
        a = _row(row_key="a", position="Juiz")
        b = _row(row_key="b", position="Desembargador", reference_month=4)
        n = normalize_rows([a, b], retrieved_at="2026-01-01T00:00:00+00:00")
        r = resolve_magistrates(n["compensations"])
        self.assertTrue(any(q["reason_code"] == "AMBIGUOUS_MAGISTRATE" for q in r["quarantine"]))


class QualityTests(unittest.TestCase):
    def test_gross_minus_discount_not_assumed(self):
        row = _row(gross_total=100, discounts=10, net_total=50)
        n = normalize_rows([row], retrieved_at="2026-01-01T00:00:00+00:00")
        r = resolve_magistrates(n["compensations"])
        q = run_quality(
            magistrates=r["magistrates"],
            compensations=r["compensations"],
            components=[],
            quarantine=[],
            layouts=[],
        )
        self.assertTrue(q["ok"])
        self.assertTrue(
            any(w["code"] == "GROSS_MINUS_DISCOUNTS_NE_NET" for w in q["warnings"])
        )

    def test_missing_field_stays_none(self):
        row = _row()
        row["indemnities"] = None
        n = normalize_rows([row], retrieved_at="2026-01-01T00:00:00+00:00")
        self.assertIsNone(n["compensations"][0]["indemnities"])


if __name__ == "__main__":
    unittest.main()
