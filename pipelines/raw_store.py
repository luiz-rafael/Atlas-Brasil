"""MinIO / S3 RAW store — espelho imutável do lake local."""

from __future__ import annotations

import json
import os
from typing import Any

MINIO_ENDPOINT = os.getenv("ATLAS_MINIO_ENDPOINT", "http://127.0.0.1:9000")
MINIO_ACCESS = os.getenv("ATLAS_MINIO_ACCESS_KEY", "atlasminio")
MINIO_SECRET = os.getenv("ATLAS_MINIO_SECRET_KEY", "atlasbrasilminio")
MINIO_BUCKET = os.getenv("ATLAS_MINIO_BUCKET", "atlas-raw")
MINIO_REGION = os.getenv("ATLAS_MINIO_REGION", "us-east-1")


def minio_enabled() -> bool:
    """True se MinIO ligado ou backend dual/minio explícito."""
    if os.getenv("ATLAS_MINIO_ENABLED", "").lower() in ("1", "true", "yes"):
        return True
    if os.getenv("ATLAS_STORAGE_BACKEND", "").strip().lower() in ("dual", "minio"):
        return True
    return False


# Compat: legado
MINIO_ENABLED = minio_enabled()


def _client():
    try:
        import boto3
        from botocore.client import Config
    except ImportError:
        return None
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS,
        aws_secret_access_key=MINIO_SECRET,
        region_name=MINIO_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> bool:
    """Cria bucket se não existir. Retorna True se ok."""
    client = _client()
    if not client:
        return False
    try:
        existing = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
        if MINIO_BUCKET not in existing:
            client.create_bucket(Bucket=MINIO_BUCKET)
        return True
    except Exception as e:
        print(f"minio ensure_bucket: {e}")
        return False


def object_exists(key: str) -> bool:
    client = _client()
    if not client:
        return False
    try:
        client.head_object(Bucket=MINIO_BUCKET, Key=key)
        return True
    except Exception:
        return False


def put_raw(
    *,
    source_id: str,
    run_id: str,
    filename: str,
    data: bytes,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Envia RAW para MinIO. Nunca sobrescreve objeto com o mesmo key/hash.
    Key: raw/{source_id}/{run_id}/{filename}
    """
    if not minio_enabled():
        return None
    client = _client()
    if not client:
        return None
    ensure_bucket()
    safe = filename.replace("\\", "/").lstrip("/")
    key = f"raw/{source_id}/{run_id}/{safe}"
    try:
        if object_exists(key):
            return {
                "key": key,
                "skipped": True,
                "reason": "exists",
                "bucket": MINIO_BUCKET,
            }
        extra: dict[str, Any] = {}
        if meta:
            md = {}
            for k, v in meta.items():
                if v is None:
                    continue
                try:
                    md[str(k)[:40]] = (
                        str(v).encode("ascii", "replace").decode("ascii")[:1024]
                    )
                except Exception:
                    continue
            if md:
                extra["Metadata"] = md
        client.put_object(
            Bucket=MINIO_BUCKET,
            Key=key,
            Body=data,
            ContentType=(meta or {}).get("content_type") or "application/octet-stream",
            **extra,
        )
        idx_key = f"raw/{source_id}/{run_id}/_index/{safe}.json"
        if meta and not object_exists(idx_key):
            client.put_object(
                Bucket=MINIO_BUCKET,
                Key=idx_key,
                Body=json.dumps(meta, ensure_ascii=False).encode("utf-8"),
                ContentType="application/json",
            )
        return {"key": key, "skipped": False, "bucket": MINIO_BUCKET}
    except Exception as e:
        print(f"minio put_raw fail-soft: {e}")
        return {"error": str(e)}
