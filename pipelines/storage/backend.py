#!/usr/bin/env python3
"""Adapter de storage Bronze — local / MinIO / dual.

Não quebra pipelines existentes: default = local.
Novas ingestões podem usar ATLAS_STORAGE_BACKEND=dual|minio.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[2]
LAKE = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake"))


@dataclass
class StorageObject:
    key: str
    backend: str
    byte_size: int
    content_type: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    local_path: str | None = None
    uri: str | None = None
    skipped: bool = False


class StorageBackend(Protocol):
    name: str

    def write_raw(
        self,
        *,
        source_id: str,
        run_id: str,
        filename: str,
        data: bytes,
        meta: dict[str, Any] | None = None,
        content_type: str | None = None,
    ) -> StorageObject: ...

    def exists(self, key: str) -> bool: ...

    def read_raw(self, key: str) -> bytes | None: ...


def storage_backend_name() -> str:
    # dual se MinIO habilitado e backend não forçado
    explicit = os.getenv("ATLAS_STORAGE_BACKEND", "").strip().lower()
    if explicit in ("local", "minio", "dual"):
        return explicit
    if os.getenv("ATLAS_MINIO_ENABLED", "").lower() in ("1", "true", "yes"):
        return "dual"
    return "local"


class LocalStorage:
    name = "local"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or LAKE

    def _path(self, key: str) -> Path:
        return self.root / key.replace("\\", "/")

    def write_raw(
        self,
        *,
        source_id: str,
        run_id: str,
        filename: str,
        data: bytes,
        meta: dict[str, Any] | None = None,
        content_type: str | None = None,
    ) -> StorageObject:
        safe = filename.replace("\\", "/").lstrip("/")
        key = f"bronze/{source_id}/{run_id}/{safe}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        skipped = path.exists()
        if not skipped:
            path.write_bytes(data)
        idx = path.parent / "raw_index.jsonl"
        record = {
            **(meta or {}),
            "storage_backend": self.name,
            "storage_key": key,
            "content_type": content_type,
            "byte_size": len(data),
        }
        with idx.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return StorageObject(
            key=key,
            backend=self.name,
            byte_size=len(data),
            content_type=content_type,
            meta=record,
            local_path=str(path),
            uri=f"file://{path.resolve()}",
            skipped=skipped,
        )

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def read_raw(self, key: str) -> bytes | None:
        p = self._path(key)
        if not p.exists():
            return None
        return p.read_bytes()


class MinioStorage:
    name = "minio"

    def write_raw(
        self,
        *,
        source_id: str,
        run_id: str,
        filename: str,
        data: bytes,
        meta: dict[str, Any] | None = None,
        content_type: str | None = None,
    ) -> StorageObject:
        from pipelines import raw_store

        safe = filename.replace("\\", "/").lstrip("/")
        key = f"bronze/{source_id}/{run_id}/{safe}"
        # raw_store usa prefixo raw/ — mantemos compat + novo bronze/
        result = raw_store.put_raw(
            source_id=source_id,
            run_id=run_id,
            filename=safe,
            data=data,
            meta={**(meta or {}), "content_type": content_type, "storage_key": key},
        )
        if result is None:
            return StorageObject(
                key=key,
                backend=self.name,
                byte_size=len(data),
                content_type=content_type,
                meta={"error": "minio_disabled_or_unavailable"},
                skipped=True,
            )
        if result.get("error"):
            return StorageObject(
                key=key,
                backend=self.name,
                byte_size=len(data),
                content_type=content_type,
                meta=result,
                skipped=True,
            )
        uri_key = result.get("key") or f"raw/{source_id}/{run_id}/{safe}"
        bucket = result.get("bucket") or raw_store.MINIO_BUCKET
        return StorageObject(
            key=key,
            backend=self.name,
            byte_size=len(data),
            content_type=content_type,
            meta={**(meta or {}), **result},
            uri=f"s3://{bucket}/{uri_key}",
            skipped=bool(result.get("skipped")),
        )

    def exists(self, key: str) -> bool:
        from pipelines import raw_store

        # keys históricas em raw/
        if key.startswith("bronze/"):
            # bronze/src/run/file → raw/src/run/file
            parts = key.split("/", 3)
            if len(parts) >= 4:
                alt = f"raw/{parts[1]}/{parts[2]}/{parts[3]}"
                return raw_store.object_exists(alt)
        return raw_store.object_exists(key)

    def read_raw(self, key: str) -> bytes | None:
        # leitura sob demanda — não obrigatória nesta fase
        return None


class DualStorage:
    name = "dual"

    def __init__(self) -> None:
        self.local = LocalStorage()
        self.minio = MinioStorage()

    def write_raw(
        self,
        *,
        source_id: str,
        run_id: str,
        filename: str,
        data: bytes,
        meta: dict[str, Any] | None = None,
        content_type: str | None = None,
    ) -> StorageObject:
        local_obj = self.local.write_raw(
            source_id=source_id,
            run_id=run_id,
            filename=filename,
            data=data,
            meta=meta,
            content_type=content_type,
        )
        minio_obj = self.minio.write_raw(
            source_id=source_id,
            run_id=run_id,
            filename=filename,
            data=data,
            meta=meta,
            content_type=content_type,
        )
        return StorageObject(
            key=local_obj.key,
            backend=self.name,
            byte_size=len(data),
            content_type=content_type,
            meta={
                "local": local_obj.meta,
                "minio": minio_obj.meta,
                "minio_uri": minio_obj.uri,
            },
            local_path=local_obj.local_path,
            uri=minio_obj.uri or local_obj.uri,
            skipped=local_obj.skipped and minio_obj.skipped,
        )

    def exists(self, key: str) -> bool:
        return self.local.exists(key) or self.minio.exists(key)

    def read_raw(self, key: str) -> bytes | None:
        return self.local.read_raw(key)


def get_storage() -> StorageBackend:
    name = storage_backend_name()
    if name == "minio":
        return MinioStorage()
    if name == "dual":
        return DualStorage()
    return LocalStorage()
