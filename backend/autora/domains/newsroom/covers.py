"""Articles' cover images (D-142): a photo from a free library, cut to 1200x630 WebP and kept in
the company's own storage.

Marketing chooses it while the article is drafted (the ``cover`` task, ``agents/cover.py``) with
two tools: ``search_images`` (what the library has) and ``set_cover`` (download the one chosen,
cut it, store it). A person sees it on the approval card and can swap it for another photo from
the same search, or take it off; neither asks the model again.

- The library is Pixabay (Pexels too once it issues keys again): its licence allows commercial
  use without attribution, and asks that a photo be downloaded and served from one's own
  server, not hotlinked — so every cover is copied. The site credits the photographer anyway.
  Its key travels in the query string, so a request URL is never logged or put in an error.
- 1200x630 (1.91:1) is what Facebook and LINE show without cropping; WebP at quality 80 keeps it
  near 100-250 KB. The photo is centred and cropped to fill, never stretched.
- Storage is Cloudflare R2 (S3's API, signed here with Signature V4 — one PUT and one DELETE do
  not need an SDK), served from the bucket's public address; without R2 settings the blob store
  keeps it and the API serves it (dev).
"""

from __future__ import annotations

import hashlib
import hmac
import io
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom.models import CoverState, StoryCover
from autora.infra.blobstore import BlobStore

WIDTH, HEIGHT = 1200, 630
QUALITIES = (80, 70, 60)
MAX_BYTES = 300_000
"""Try a lower quality until the WebP is under this (a busy photo can be larger at 80)."""
MAX_DOWNLOAD = 15_000_000
KEEP_CANDIDATES = 6
CACHE_SECONDS = 24 * 3600
"""Pixabay asks that search results be cached for 24 hours."""


class CoverError(Exception):
    retryable = False


class LibraryError(CoverError):
    """The library did not answer as expected. The message never contains the request URL."""

    retryable = True


@dataclass(frozen=True)
class Photo:
    provider: str
    id: str
    page_url: str
    image_url: str
    width: int
    height: int
    tags: str
    credit: str
    kind: str = "photo"
    """photo | illustration (a 3D render or digital art: most modern technology images are)."""

    def as_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> Photo:
        return cls(**{k: value[k] for k in cls.__dataclass_fields__ if k in value})

    def for_model(self) -> dict[str, Any]:
        """What marketing reads: no URLs (it cannot see the photo; it reads what it shows)."""
        return {
            "photo_id": self.id,
            "kind": self.kind,
            "shows": self.tags,
            "size": f"{self.width}x{self.height}",
            "by": self.credit,
        }


class ImageLibrary(Protocol):
    name: str

    async def search(self, query: str, *, limit: int = 10) -> list[Photo]: ...
    async def download(self, photo: Photo) -> bytes: ...


class Pixabay:
    """https://pixabay.com/api/docs/ — landscape photos at least 1200 wide, safe search on."""

    name = "pixabay"
    URL = "https://pixabay.com/api/"

    def __init__(self, key: str, client: httpx.AsyncClient | None = None):
        self._key = key
        self._client = client
        self._cache: dict[str, tuple[float, list[Photo]]] = {}

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        try:
            if self._client is not None:
                return await self._client.get(url, params=params, timeout=20.0)
            async with httpx.AsyncClient(follow_redirects=True) as client:
                return await client.get(url, params=params, timeout=20.0)
        except httpx.HTTPError as exc:
            # str(exc) can carry the URL, and with it the key
            raise LibraryError(f"pixabay: {type(exc).__name__}") from None

    async def search(self, query: str, *, limit: int = 10) -> list[Photo]:
        query = " ".join(query.split())[:100]
        cached = self._cache.get(query.lower())
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1][:limit]
        response = await self._get(
            self.URL,
            {
                "key": self._key,
                "q": query,
                "lang": "en",
                # photos and illustrations (a modern chip is mostly a 3D render); vectors are
                # icons and clip art, filtered out below
                "image_type": "all",
                "orientation": "horizontal",
                "min_width": WIDTH,
                "safesearch": "true",
                "per_page": 20,
            },
        )
        if response.status_code != 200:
            raise LibraryError(f"pixabay answered {response.status_code}")
        photos = [
            Photo(
                provider=self.name,
                id=str(hit["id"]),
                page_url=str(hit.get("pageURL") or ""),
                image_url=str(hit["largeImageURL"]),
                width=int(hit.get("imageWidth") or 0),
                height=int(hit.get("imageHeight") or 0),
                tags=str(hit.get("tags") or ""),
                credit=str(hit.get("user") or "Pixabay"),
                kind="illustration" if hit.get("type") == "illustration" else "photo",
            )
            for hit in (response.json().get("hits") or [])
            if hit.get("largeImageURL") and not str(hit.get("type") or "").startswith("vector")
        ]
        self._cache[query.lower()] = (time.monotonic(), photos)
        return photos[:limit]

    async def download(self, photo: Photo) -> bytes:
        response = await self._get(photo.image_url)
        if response.status_code != 200:
            raise LibraryError(f"pixabay image answered {response.status_code}")
        if len(response.content) > MAX_DOWNLOAD:
            raise CoverError("the photo is too large to download")
        return response.content


class FixtureLibrary:
    """Tests and ``TOOLS_PROFILE=fixture``: three made-up photos per query, drawn on the spot."""

    name = "fixture"
    COLOURS = ((32, 64, 128), (180, 90, 40), (40, 120, 80))

    async def search(self, query: str, *, limit: int = 10) -> list[Photo]:
        words = " ".join(query.lower().split())
        return [
            Photo(
                provider=self.name,
                id=f"{hashlib.sha256(words.encode()).hexdigest()[:6]}-{i}",
                page_url=f"https://library.test/photos/{i}",
                image_url=f"https://library.test/photos/{i}.jpg",
                width=1920,
                height=1280,
                tags=f"{words}, photo {i}",
                credit=f"Photographer {i}",
            )
            for i in range(3)
        ][:limit]

    async def download(self, photo: Photo) -> bytes:
        colour = self.COLOURS[int(photo.id.rsplit("-", 1)[-1]) % len(self.COLOURS)]
        out = io.BytesIO()
        Image.new("RGB", (photo.width, photo.height), colour).save(out, "JPEG")
        return out.getvalue()


def cut_cover(data: bytes) -> tuple[bytes, int, int]:
    """1200x630 WebP: turned upright, centred, cropped to fill; lower quality until small."""
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, Image.DecompressionBombError) as exc:
        raise CoverError(f"not a photo that can be opened: {type(exc).__name__}") from None
    cover = ImageOps.fit(image, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    for quality in QUALITIES:
        out = io.BytesIO()
        cover.save(out, "WEBP", quality=quality, method=6)
        if out.tell() <= MAX_BYTES:
            break
    return out.getvalue(), WIDTH, HEIGHT


# --- storage ----------------------------------------------------------------------------------


class CoverStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str:
        """Store it; return the address readers load it from."""
        ...

    async def delete(self, key: str) -> None: ...


def sigv4_headers(
    *,
    method: str,
    host: str,
    path: str,
    headers: dict[str, str],
    payload_hash: str,
    access_key: str,
    secret_key: str,
    region: str,
    service: str = "s3",
    now: datetime | None = None,
) -> dict[str, str]:
    """AWS Signature Version 4 for a request without a query string: the headers to send."""
    now = now or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    signed = {k.lower(): " ".join(v.split()) for k, v in headers.items()}
    signed |= {"host": host, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash}
    names = sorted(signed)
    canonical = "\n".join(
        [
            method,
            quote(path, safe="/-_.~"),
            "",
            "".join(f"{n}:{signed[n]}\n" for n in names),
            ";".join(names),
            payload_hash,
        ]
    )
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = f"AWS4{secret_key}".encode()
    for part in (day, region, service, "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {k: v for k, v in signed.items() if k != "host"} | {
        "authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={';'.join(names)}, Signature={signature}"
        )
    }


class R2Store:
    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        public_base_url: str,
        prefix: str = "",
        client: httpx.AsyncClient | None = None,
    ):
        self._host = f"{account_id}.r2.cloudflarestorage.com"
        self._access = access_key_id
        self._secret = secret_access_key
        self._bucket = bucket
        self._public = public_base_url.rstrip("/")
        self._prefix = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
        self._client = client

    async def _send(self, method: str, key: str, data: bytes, headers: dict[str, str]) -> None:
        path = f"/{self._bucket}/{self._prefix}{key}"
        signed = sigv4_headers(
            method=method,
            host=self._host,
            path=path,
            headers=headers,
            payload_hash=hashlib.sha256(data).hexdigest(),
            access_key=self._access,
            secret_key=self._secret,
            region="auto",
        )
        url = f"https://{self._host}{quote(path, safe='/-_.~')}"
        try:
            if self._client is not None:
                response = await self._client.request(method, url, content=data, headers=signed)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method, url, content=data, headers=signed, timeout=30.0
                    )
        except httpx.HTTPError as exc:
            raise LibraryError(f"r2: {type(exc).__name__}") from None
        if response.status_code not in (200, 204):
            raise CoverError(f"r2 answered {response.status_code} to {method}")

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        await self._send(
            "PUT",
            key,
            data,
            {"content-type": content_type, "cache-control": "public, max-age=31536000, immutable"},
        )
        return f"{self._public}/{self._prefix}{key}"

    async def delete(self, key: str) -> None:
        await self._send("DELETE", key, b"", {})


class BlobCoverStore:
    """Dev without R2: the blob store keeps it and ``GET /api/public/covers/{key}`` serves it."""

    PREFIX = "covers/"

    def __init__(self, blobs: BlobStore):
        self._blobs = blobs

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        await self._blobs.put(key, data)
        return f"/api/public/{key}"

    async def delete(self, key: str) -> None:
        await self._blobs.delete(key)


# --- the story's cover ------------------------------------------------------------------------


async def cover_of(session: AsyncSession, story_id: uuid.UUID) -> StoryCover | None:
    return await session.scalar(select(StoryCover).where(StoryCover.story_id == story_id))


def _key(story_id: uuid.UUID, photo: Photo) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in photo.id)
    return f"covers/{story_id}/{photo.provider}-{safe}.webp"


async def _store(
    library: ImageLibrary, store: CoverStore, story_id: uuid.UUID, photo: Photo
) -> tuple[str, str, int, int, int]:
    webp, width, height = cut_cover(await library.download(photo))
    key = _key(story_id, photo)
    url = await store.put(key, webp, "image/webp")
    return key, url, width, height, len(webp)


async def _forget(store: CoverStore, key: str) -> None:
    try:
        await store.delete(key)
    except Exception:  # noqa: BLE001 - an orphaned object costs a few KB, not the cover
        pass


async def set_cover(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    story_id: uuid.UUID,
    photo: Photo,
    candidates: list[Photo],
    alt: dict[str, str],
    query: str,
    library: ImageLibrary,
    store: CoverStore,
    run_id: uuid.UUID | None,
) -> StoryCover:
    """The story's cover is ``photo``; ``candidates`` are kept for a person to swap to."""
    row = await cover_of(session, story_id)
    if row is not None and row.state == CoverState.REMOVED:
        raise CoverError("a person took this story's cover off: it gets none")
    if row is not None and row.provider == photo.provider and row.provider_id == photo.id:
        return row  # the same photo again (a retried call)
    key, url, width, height, size = await _store(library, store, story_id, photo)
    old = row.key if row is not None else None
    if row is None:
        row = StoryCover(company_id=company_id, story_id=story_id)
        session.add(row)
    _show(row, photo, key=key, url=url, width=width, height=height, size=size)
    row.alt, row.query, row.run_id = alt, query, run_id
    row.candidates = [c.as_json() for c in candidates if c.id != photo.id][:KEEP_CANDIDATES]
    if old is not None and old != key:
        await _forget(store, old)
    await session.flush()
    return row


async def swap_cover(
    session: AsyncSession, row: StoryCover, *, library: ImageLibrary, store: CoverStore
) -> StoryCover:
    """The next photo from the same search, chosen by a person: no model call. The one it
    replaces goes to the end of the list, so swapping on comes back round to it."""
    if not row.candidates:
        raise CoverError("no other photo from this search: nothing to swap to")
    photo = Photo.from_json(row.candidates[0])
    key, url, width, height, size = await _store(library, store, row.story_id, photo)
    old = row.key
    row.candidates = [*row.candidates[1:], row.photo] if row.photo else list(row.candidates[1:])
    _show(row, photo, key=key, url=url, width=width, height=height, size=size)
    # what marketing wrote described the photo it chose; for this one, the library's words
    row.alt = {"zh-TW": f"示意圖：{photo.tags}", "en": f"Illustration: {photo.tags}"}
    row.state = CoverState.ACTIVE.value
    if old != key:
        await _forget(store, old)
    await session.flush()
    return row


def _show(row: StoryCover, photo: Photo, *, key: str, url: str, width: int, height: int, size: int):
    row.provider, row.provider_id, row.page_url, row.credit = (
        photo.provider,
        photo.id,
        photo.page_url,
        photo.credit,
    )
    row.photo = photo.as_json()
    row.key, row.url, row.width, row.height, row.bytes = key, url, width, height, size


async def remove_cover(session: AsyncSession, row: StoryCover, *, store: CoverStore) -> None:
    """Off the article, and marketing will not pick another; the row stays to say so."""
    row.state = CoverState.REMOVED.value
    await _forget(store, row.key)
    await session.flush()
