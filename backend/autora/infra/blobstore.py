"""Blob storage for large payloads kept out of Postgres (T-210).

Contents: full model prompts/responses per agent step, evidence HTML snapshots (Phase 5).
Rows store only the key.

Implementations:
- ``LocalFSBlobStore``: dev and tests. Writes are atomic (temp file + rename).
- ``R2BlobStore``: production (D-153), a private Cloudflare R2 bucket. Both pass the same
  contract suite (``tests/infra/test_blobstore.py``); nothing above this module depends on which
  one is used — ``build_blob_store`` chooses.

Keys are relative, slash-separated paths of ``[A-Za-z0-9._-]`` segments. No ``..``, no leading
slash, no backslashes, so a key can never escape the store root.
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from autora.infra.s3 import R2Bucket

if TYPE_CHECKING:
    from autora.infra.settings import Settings

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class BlobError(Exception):
    pass


class InvalidBlobKey(BlobError):
    pass


class BlobNotFound(BlobError):
    pass


def validate_key(key: str) -> str:
    if not key or key.startswith("/") or "\\" in key:
        raise InvalidBlobKey(f"invalid blob key: {key!r}")
    segments = key.split("/")
    if any(s in ("", ".", "..") or not _SEGMENT.match(s) for s in segments):
        raise InvalidBlobKey(f"invalid blob key: {key!r}")
    return key


class BlobStore(Protocol):
    async def put(self, key: str, data: bytes) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def exists(self, key: str) -> bool: ...
    async def delete(self, key: str) -> None: ...


class LocalFSBlobStore:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if not path.is_relative_to(self.root):  # defence in depth; validate_key already blocks
            raise InvalidBlobKey(f"invalid blob key: {key!r}")
        return path

    async def put(self, key: str, data: bytes) -> str:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise

        await asyncio.to_thread(write)
        return key

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            raise BlobNotFound(key) from None

    async def exists(self, key: str) -> bool:
        path = self._path(key)
        return await asyncio.to_thread(path.is_file)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)


class R2BlobStore:
    """Production (D-153): a private Cloudflare R2 bucket, so the API and the worker — separate
    machines whose disks are wiped on every deploy — read the same blobs. Never a public bucket:
    agent traces hold whole model conversations."""

    def __init__(self, bucket: R2Bucket):
        self._bucket = bucket

    async def put(self, key: str, data: bytes) -> str:
        await self._bucket.put(
            validate_key(key), data, {"content-type": "application/octet-stream"}
        )
        return key

    async def get(self, key: str) -> bytes:
        data = await self._bucket.get(validate_key(key))
        if data is None:
            raise BlobNotFound(key)
        return data

    async def exists(self, key: str) -> bool:
        return await self._bucket.exists(validate_key(key))

    async def delete(self, key: str) -> None:
        await self._bucket.delete(validate_key(key))


def build_blob_store(settings: Settings) -> BlobStore:
    """The private R2 bucket when ``BLOB_R2_BUCKET`` is set (with the R2 account and keys), else
    the local directory (dev, tests)."""
    if settings.blob_r2_bucket:
        if not (
            settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key
        ):
            raise BlobError(
                "BLOB_R2_BUCKET needs R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY"
            )
        return R2BlobStore(
            R2Bucket(
                account_id=settings.r2_account_id,
                access_key_id=settings.r2_access_key_id.get_secret_value(),
                secret_access_key=settings.r2_secret_access_key.get_secret_value(),
                bucket=settings.blob_r2_bucket,
            )
        )
    return LocalFSBlobStore(settings.blob_store_dir)
