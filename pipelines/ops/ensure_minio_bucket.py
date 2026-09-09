#!/usr/bin/env python3
"""Garante bucket MinIO atlas-raw (compose)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# bootstrap força tentativa mesmo sem ATLAS_MINIO_ENABLED
os.environ.setdefault("ATLAS_MINIO_BOOTSTRAP", "1")
os.environ.setdefault("ATLAS_MINIO_ENABLED", "1")

from pipelines.raw_store import MINIO_BUCKET, MINIO_ENDPOINT, ensure_bucket  # noqa: E402


def main() -> int:
    ok = ensure_bucket()
    print(f"MinIO {MINIO_ENDPOINT} bucket={MINIO_BUCKET} ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
