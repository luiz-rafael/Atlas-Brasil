#!/usr/bin/env python3
"""Exporta gold -> data/atlas-brasil-kb-gold.json (já feito em gold_kb) + espelha como KB ativa."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD = Path(os.getenv("GOLD_KB_PATH", ROOT / "data" / "atlas-brasil-kb-gold.json"))
ACTIVE = Path(os.getenv("KB_ACTIVE_PATH", ROOT / "data" / "atlas-brasil-kb-active.json"))
# ponte: front/api passam a preferir active -> gold
LEGACY = ROOT / "data" / "atlas-brasil-kb-v2.json"


def main() -> int:
    src = GOLD if GOLD.exists() else (ROOT / "data" / "lake" / "gold" / "kb.json")
    if not src.exists():
        print("gold ausente", file=sys.stderr)
        return 1
    shutil.copy2(src, ACTIVE)
    # opcional: sobrescrever v2 apenas se ATLAS_REPLACE_LEGACY_KB=1
    if os.getenv("ATLAS_REPLACE_LEGACY_KB", "1") == "1":
        # backup legado uma vez
        bak = LEGACY.with_suffix(".json.bak-manual")
        if LEGACY.exists() and not bak.exists():
            shutil.copy2(LEGACY, bak)
        shutil.copy2(src, LEGACY)
        print(f"KB ativa atualizada: {ACTIVE} e {LEGACY} (backup {bak.name if bak.exists() else 'n/a'})")
    else:
        print(f"KB ativa: {ACTIVE} (legado preservado)")

    kb = json.loads(src.read_text(encoding="utf-8"))
    print(
        f"export: {len(kb.get('entidades') or [])} entidades, "
        f"{len(kb.get('relacoes') or [])} relações"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
