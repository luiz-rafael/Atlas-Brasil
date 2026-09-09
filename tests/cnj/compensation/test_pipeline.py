"""Pipeline local: inbox → bronze → gold (sem rede)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def _write_cnj_xlsx(path: Path) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contracheque"
    ws.append(
        [
            "CPF",
            "Nome",
            "Cargo",
            "Subsídio",
            "Direitos Pessoais",
            "Indenizações",
            "Direitos Eventuais",
            "Total de Rendimentos",
            "Total de Descontos",
            "Rendimento Líquido",
        ]
    )
    ws.append(
        [
            "12345678900",
            "Ana Lima",
            "Juíza",
            "10000",
            "100",
            None,
            "50",
            "10150",
            "2000",
            "8150",
        ]
    )
    wb.save(path)
    wb.close()


class PipelineTests(unittest.TestCase):
    def test_inbox_to_gold(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("openpyxl ausente")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            inbox = tmp_path / "inbox" / "tjsp" / "2024" / "03"
            inbox.mkdir(parents=True)
            xlsx = inbox / "contracheque.xlsx"
            _write_cnj_xlsx(xlsx)
            lake = tmp_path / "lake"
            env = {
                "LAKE_PATH": str(lake),
                "ATLAS_CNJ_COMP_INBOX": str(tmp_path / "inbox"),
                "ATLAS_CNJ_COMP_FOLLOW_COURTS": "0",
            }
            with patch.dict(os.environ, env, clear=False):
                import pipelines.common as common

                common.LAKE = lake
                from src.connectors.cnj.compensation import discover as discover_mod
                from src.pipelines.cnj.compensation import bronze as bronze
                from src.pipelines.cnj.compensation import gold as gold_mod

                bronze.LAKE = lake
                gold_mod.LAKE = lake

                with patch.object(discover_mod, "fetch_html", return_value=(None, "offline")):
                    discovery = discover_mod.discover_sources(follow_courts=False)
                self.assertGreaterEqual(discovery["counts"]["inbox"], 1)

                from src.connectors.cnj.compensation.download import download_discovered
                from src.pipelines.cnj.compensation.bronze import build_bronze
                from src.pipelines.cnj.compensation.normalize import normalize_rows
                from src.pipelines.cnj.compensation.quality import build_coverage, run_quality
                from src.pipelines.cnj.compensation.resolve import resolve_magistrates
                from src.pipelines.cnj.compensation.gold import write_gold, write_silver

                dl = download_discovered(discovery, run_id="TEST1")
                self.assertGreaterEqual(dl["counts"]["saved"], 1)
                br = build_bronze(dl, run_id="TEST1")
                self.assertGreaterEqual(len(br["rows"]), 1)
                self.assertIsNone(br["rows"][0].get("indemnities"))
                norm = normalize_rows(br["rows"], retrieved_at="2026-09-07T00:00:00+00:00")
                resolved = resolve_magistrates(norm["compensations"])
                quality = run_quality(
                    magistrates=resolved["magistrates"],
                    compensations=resolved["compensations"],
                    components=norm["components"],
                    quarantine=br["quarantine"] + norm["quarantine"] + resolved["quarantine"],
                    layouts=br["layouts"],
                    discovery=discovery,
                )
                self.assertTrue(quality["ok"])
                coverage = build_coverage(
                    discovery=discovery,
                    download=dl,
                    quality=quality,
                    magistrates=resolved["magistrates"],
                    compensations=resolved["compensations"],
                )
                self.assertIn("tjsp", coverage["courts_found"])
                self.assertIn("2024-03", coverage["periods_found"])
                write_silver(
                    run_id="TEST1",
                    magistrates=resolved["magistrates"],
                    compensations=resolved["compensations"],
                    components=norm["components"],
                    quarantine=[],
                )
                out = write_gold(
                    run_id="TEST1",
                    magistrates=resolved["magistrates"],
                    compensations=resolved["compensations"],
                    components=norm["components"],
                    coverage=coverage,
                    quality=quality,
                    incompatibilities=discovery.get("incompatibilities") or [],
                )
                meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
                self.assertEqual(meta["counts"]["magistrates"], 1)
                mag = json.loads((out / "magistrates.jsonl").read_text(encoding="utf-8").splitlines()[0])
                self.assertEqual(mag["court_id"], "tjsp")
                self.assertEqual(mag["normalized_name"], "ANA LIMA")


if __name__ == "__main__":
    unittest.main()
