#!/usr/bin/env python3
"""Garante bucket MinIO do warehouse Iceberg (Fase 2)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.lakehouse.config import (  # noqa: E402
    ICEBERG_S3_BUCKET,
    minio_access_key,
    minio_endpoint,
    minio_region,
    minio_secret_key,
)


def ensure_iceberg_bucket() -> bool:
    try:
        import boto3
        from botocore.client import Config
    except ImportError:
        print("boto3 ausente")
        return False

    client = boto3.client(
        "s3",
        endpoint_url=minio_endpoint(),
        aws_access_key_id=minio_access_key(),
        aws_secret_access_key=minio_secret_key(),
        region_name=minio_region(),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    try:
        names = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
        if ICEBERG_S3_BUCKET not in names:
            client.create_bucket(Bucket=ICEBERG_S3_BUCKET)
            print(f"created bucket={ICEBERG_S3_BUCKET}")
        else:
            print(f"exists bucket={ICEBERG_S3_BUCKET}")
        return True
    except Exception as e:
        print(f"ensure_iceberg_bucket: {e}")
        return False


def main() -> int:
    ok = ensure_iceberg_bucket()
    print(f"MinIO {minio_endpoint()} iceberg_bucket={ICEBERG_S3_BUCKET} ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
