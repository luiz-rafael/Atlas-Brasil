"""Storage unificado do lake Atlas — local e/ou MinIO.

Backends:
  local  — data/lake (padrão atual; compatibilidade)
  minio  — object store (padrão-alvo para Bronze novo)
  dual   — grava local + espelho MinIO (transição)

Env:
  ATLAS_STORAGE_BACKEND=local|minio|dual
  ATLAS_MINIO_* (ver pipelines/raw_store.py)
"""

from __future__ import annotations

from pipelines.storage.backend import (  # noqa: F401
    StorageBackend,
    StorageObject,
    get_storage,
    storage_backend_name,
)

__all__ = [
    "StorageBackend",
    "StorageObject",
    "get_storage",
    "storage_backend_name",
]
