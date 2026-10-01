"""T-210: BlobStore contract. Every implementation must pass this suite unchanged."""

import httpx
import pytest

from autora.infra.blobstore import (
    BlobNotFound,
    InvalidBlobKey,
    LocalFSBlobStore,
    R2BlobStore,
    build_blob_store,
    validate_key,
)
from autora.infra.s3 import R2Bucket
from autora.infra.settings import load_settings


def fake_r2() -> httpx.AsyncClient:
    """An S3 server in memory: PUT, GET, HEAD, DELETE by path; every request must be signed."""
    objects: dict[str, bytes] = {}

    def answer(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=id/")
        path = request.url.path
        if request.method == "PUT":
            objects[path] = request.content
            return httpx.Response(200)
        if request.method == "DELETE":
            objects.pop(path, None)
            return httpx.Response(204)
        if path not in objects:
            return httpx.Response(404)
        return httpx.Response(200, content=b"" if request.method == "HEAD" else objects[path])

    return httpx.AsyncClient(transport=httpx.MockTransport(answer))


@pytest.fixture(params=["localfs", "r2"])
def store(request, tmp_path):
    if request.param == "localfs":
        return LocalFSBlobStore(tmp_path / "blobs")
    if request.param == "r2":  # D-153
        return R2BlobStore(
            R2Bucket(
                account_id="acct",
                access_key_id="id",
                secret_access_key="secret",
                bucket="private",
                client=fake_r2(),
            )
        )
    raise AssertionError(request.param)


def test_the_private_bucket_when_one_is_named(tmp_path):
    local = load_settings(
        _env_file=None, database_url="postgresql+asyncpg://u:p@h/db", blob_store_dir=tmp_path
    )
    assert isinstance(build_blob_store(local), LocalFSBlobStore)
    r2 = load_settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@h/db",
        blob_r2_bucket="aisiwhale-private",
        r2_account_id="acct",
        r2_access_key_id="id",
        r2_secret_access_key="secret",
    )
    assert isinstance(build_blob_store(r2), R2BlobStore)


async def test_put_get_roundtrip_and_overwrite(store):
    key = "companies/c1/runs/r1/steps/00000.json"
    assert await store.put(key, b'{"prompt": "hi"}') == key
    assert await store.get(key) == b'{"prompt": "hi"}'
    await store.put(key, b"v2")
    assert await store.get(key) == b"v2"


async def test_exists_and_delete(store):
    key = "a/b.txt"
    assert not await store.exists(key)
    await store.put(key, b"x")
    assert await store.exists(key)
    await store.delete(key)
    assert not await store.exists(key)
    await store.delete(key)  # deleting a missing blob is a no-op


async def test_missing_blob_raises(store):
    with pytest.raises(BlobNotFound):
        await store.get("nope/missing.json")


async def test_binary_data_preserved(store):
    data = bytes(range(256)) * 100
    await store.put("bin/data.bin", data)
    assert await store.get("bin/data.bin") == data


@pytest.mark.parametrize(
    "key",
    ["", "/abs/path", "../escape", "a/../../escape", "a//b", "a/./b", "a\\b", "a/b c", ".hidden"],
)
async def test_unsafe_keys_rejected(store, key):
    with pytest.raises(InvalidBlobKey):
        await store.put(key, b"x")
    with pytest.raises(InvalidBlobKey):
        validate_key(key)


async def test_localfs_writes_atomically(tmp_path):
    store = LocalFSBlobStore(tmp_path)
    await store.put("dir/file.json", b"data")
    leftovers = [p.name for p in (tmp_path / "dir").iterdir() if p.name.startswith(".tmp-")]
    assert leftovers == []
