#!/usr/bin/env python3
"""
SICONFI — fatia estadual (UF + DF).

Wrapper do coletor DCA/RGF com ATLAS_SICONFI_UF_ONLY=1.
DAG: siconfi_state_fiscal / dag_siconfi_state_fiscal
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["ATLAS_SICONFI_UF_ONLY"] = "1"
os.environ.pop("ATLAS_SICONFI_SKIP_UF", None)

from pipelines.ingest.siconfi_dca import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
