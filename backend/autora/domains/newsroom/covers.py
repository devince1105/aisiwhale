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

import base64
import hashlib
import hmac
import io
import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from PIL import Image, ImageOps
from sqlalchemy import func, select
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
    preview_url: str = ""
    """A 640-pixel copy, for the viewer to look at (D-144)."""

    def as_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> Photo:
        return cls(**{k: value[k] for k in cls.__dataclass_fields__ if k in value})

    def for_model(self, looks: dict[str, Any] | None = None) -> dict[str, Any]:
        """What marketing reads: no URLs. ``looks`` is what the viewer saw in it (D-144)."""
        out = {
            "photo_id": self.id,
            "kind": self.kind,
            "shows": self.tags,
            "size": f"{self.width}x{self.height}",
            "by": self.credit,
        }
        if looks:
            out["looks"] = looks
        return out


class ImageLibrary(Protocol):
    name: str

    async def search(self, query: str, *, limit: int = 10) -> list[Photo]: ...
    async def download(self, photo: Photo, *, preview: bool = False) -> bytes: ...


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
                preview_url=str(hit.get("webformatURL") or ""),
            )
            for hit in (response.json().get("hits") or [])
            if hit.get("largeImageURL") and not str(hit.get("type") or "").startswith("vector")
        ]
        self._cache[query.lower()] = (time.monotonic(), photos)
        return photos[:limit]

    async def download(self, photo: Photo, *, preview: bool = False) -> bytes:
        response = await self._get(
            photo.preview_url if preview and photo.preview_url else photo.image_url
        )
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

    async def download(self, photo: Photo, *, preview: bool = False) -> bytes:
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


# --- looking at them (D-144) ----------------------------------------------------------------

VIEW_PROMPT = """You look at candidate cover images for a finance newsroom's articles and say, for
each, what it actually looks like — the library's own words say what it is about, not how it
looks. Be plain and specific. Reply with only a JSON object:
{"images": [{"photo_id": "<id>", "looks": "<one sentence: what is in the picture and how it is
drawn or shot>", "style": "photo | 3d render | flat illustration | cartoon | clip art or icons |
chart graphic | other", "dated": <true if it looks old-fashioned: old electronics, retro, 2000s
stock art, binary-digit backdrops>, "text_or_logo": "<none, or which words, logo or brand is
visible>", "quality": "high | ok | poor"}]}"""


class ImageViewer:
    """A vision model's look at the candidates (D-144): marketing chooses by what an image looks
    like, not only by the library's tags (which never say "flat cartoon" or "dated"). One call per
    search, small previews at the provider's low detail; what it saw is cached per image."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        price_in: float,
        price_out: float,
        extra_body: dict[str, Any] | None = None,
        max_tokens_field: str = "max_tokens",
        client: httpx.AsyncClient | None = None,
    ):
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model
        self._prices = (Decimal(str(price_in)), Decimal(str(price_out)))
        self._extra = extra_body or {}
        self._max_tokens_field = max_tokens_field
        self._client = client
        self._seen: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _thumbnail(data: bytes) -> str:
        with Image.open(io.BytesIO(data)) as image:
            small = ImageOps.exif_transpose(image).convert("RGB")
            small.thumbnail((512, 512))
            out = io.BytesIO()
            small.save(out, "JPEG", quality=80)
        return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()

    async def look(
        self, library: ImageLibrary, photos: list[Photo]
    ) -> tuple[dict[str, dict[str, Any]], Decimal]:
        """What each photo looks like, by id, and what asking cost. A photo that cannot be
        downloaded, or a model that does not answer, is left out: marketing then has the tags."""
        images: list[tuple[str, bytes]] = []
        for photo in photos:
            if photo.id in self._seen:
                continue
            try:
                images.append((photo.id, await library.download(photo, preview=True)))
            except CoverError:
                continue
        cost = await self._ask(images) if images else Decimal(0)
        return {p.id: self._seen[p.id] for p in photos if p.id in self._seen}, cost

    async def look_at(self, image_id: str, data: bytes) -> tuple[dict[str, Any] | None, Decimal]:
        """What one image in hand looks like (a generated cover, D-145)."""
        cost = await self._ask([(image_id, data)])
        return self._seen.get(image_id), cost

    async def _ask(self, images: list[tuple[str, bytes]]) -> Decimal:
        content: list[dict[str, Any]] = [{"type": "text", "text": "The candidates:"}]
        for image_id, data in images:
            try:
                url = self._thumbnail(data)
            except (OSError, Image.DecompressionBombError):
                continue
            content += [
                {"type": "text", "text": f"photo_id {image_id}:"},
                {"type": "image_url", "image_url": {"url": url, "detail": "low"}},
            ]
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": VIEW_PROMPT},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            self._max_tokens_field: 2000,
            **self._extra,
        }
        try:
            if self._client is not None:
                response = await self._client.post(
                    self._url, json=body, headers=self._headers, timeout=90.0
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self._url, json=body, headers=self._headers, timeout=90.0
                    )
            answer = response.json() if response.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            answer = {}
        usage = answer.get("usage") or {}
        cost = (
            self._prices[0] * (usage.get("prompt_tokens") or 0)
            + self._prices[1] * (usage.get("completion_tokens") or 0)
        ) / Decimal(1_000_000)
        try:
            said = json.loads(answer["choices"][0]["message"]["content"])
            for item in said.get("images") or []:
                seen = {
                    k: item.get(k) for k in ("looks", "style", "dated", "text_or_logo", "quality")
                }
                self._seen[str(item.get("photo_id"))] = seen
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        return cost


class FixtureViewer:
    """Tests: every image looks like a clean modern render."""

    async def look(
        self, library: ImageLibrary, photos: list[Photo]
    ) -> tuple[dict[str, dict[str, Any]], Decimal]:
        return {
            p.id: {
                "looks": f"a clean render of {p.tags}",
                "style": "3d render",
                "dated": False,
                "text_or_logo": "none",
                "quality": "high",
            }
            for p in photos
        }, Decimal(0)


# --- generating one (D-145) ------------------------------------------------------------------

GENERATED = "gemini"
PAINT_RULES = (
    " Style: a modern, clean editorial illustration for a finance news site, wide 16:9, rich but "
    "not garish colour, one clear subject. Absolutely no text, letters, numbers, labels, logos, "
    "watermarks or signatures, and no recognisable real person."
)


class Painter(Protocol):
    name: str

    async def paint(self, prompt: str) -> tuple[bytes, Decimal]: ...


class GeminiPainter:
    """Gemini's image model: one wide image per prompt, with the site's rules appended. Its key
    goes in a header, never the URL. The cost is a set price per image (MODEL settings)."""

    name = GENERATED
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(
        self, key: str, model: str, usd_per_image: float, client: httpx.AsyncClient | None = None
    ):
        self._key = key
        self.model = model
        self._cost = Decimal(str(usd_per_image))
        self._client = client

    async def paint(self, prompt: str) -> tuple[bytes, Decimal]:
        body = {
            "contents": [{"parts": [{"text": prompt.strip() + PAINT_RULES}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": "16:9"},
            },
        }
        url = self.URL.format(model=self.model)
        headers = {"x-goog-api-key": self._key}
        try:
            if self._client is not None:
                response = await self._client.post(url, json=body, headers=headers, timeout=120.0)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=body, headers=headers, timeout=120.0)
        except httpx.HTTPError as exc:
            raise LibraryError(f"gemini image: {type(exc).__name__}") from None
        if response.status_code != 200:
            raise CoverError(f"gemini image answered {response.status_code}")
        for candidate in response.json().get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"]), self._cost
        raise CoverError("gemini image returned no image (it may have refused the prompt)")


class FixturePainter:
    name = GENERATED

    async def paint(self, prompt: str) -> tuple[bytes, Decimal]:
        out = io.BytesIO()
        Image.new("RGB", (1344, 768), (20, 40, 90)).save(out, "PNG")
        return out.getvalue(), Decimal(0)


async def generated_today(session: AsyncSession, company_id: uuid.UUID) -> int:
    """How many covers the company has generated since midnight UTC (the daily cap)."""
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        await session.scalar(
            select(func.count()).where(
                StoryCover.company_id == company_id,
                StoryCover.provider == GENERATED,
                StoryCover.updated_at >= start,
            )
        )
        or 0
    )


def generated_photo(prompt: str) -> Photo:
    return Photo(
        provider=GENERATED,
        id=uuid.uuid4().hex[:12],
        page_url="",
        image_url="",
        width=WIDTH,
        height=HEIGHT,
        tags=prompt[:300],
        credit="AI 生成示意圖",
        kind="generated",
    )


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


async def used_elsewhere(
    session: AsyncSession, company_id: uuid.UUID, story_id: uuid.UUID | None, photos: list[Photo]
) -> set[str]:
    """The photos another of the company's stories already has as its cover (D-144): two
    articles side by side on the front page must not share one."""
    if not photos:
        return set()
    rows = await session.scalars(
        select(StoryCover.provider_id).where(
            StoryCover.company_id == company_id,
            StoryCover.provider_id.in_([p.id for p in photos]),
            StoryCover.state == CoverState.ACTIVE.value,
            *([StoryCover.story_id != story_id] if story_id else []),
        )
    )
    return set(rows)


async def cover_of(session: AsyncSession, story_id: uuid.UUID) -> StoryCover | None:
    return await session.scalar(select(StoryCover).where(StoryCover.story_id == story_id))


def _key(story_id: uuid.UUID, photo: Photo) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in photo.id)
    return f"covers/{story_id}/{photo.provider}-{safe}.webp"


async def _store(
    library: ImageLibrary | None,
    store: CoverStore,
    story_id: uuid.UUID,
    photo: Photo,
    data: bytes | None = None,
) -> tuple[str, str, int, int, int]:
    if data is None:
        assert library is not None
        data = await library.download(photo)
    webp, width, height = cut_cover(data)
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
    library: ImageLibrary | None,
    store: CoverStore,
    run_id: uuid.UUID | None,
    data: bytes | None = None,
) -> StoryCover:
    """The story's cover is ``photo``; ``candidates`` are kept for a person to swap to.
    ``data``: the image itself (a generated one, D-145), else it is downloaded."""
    row = await cover_of(session, story_id)
    if row is not None and row.state == CoverState.REMOVED:
        raise CoverError("a person took this story's cover off: it gets none")
    if row is not None and row.provider == photo.provider and row.provider_id == photo.id:
        return row  # the same photo again (a retried call)
    if await used_elsewhere(session, company_id, story_id, [photo]):
        raise CoverError(f"photo {photo.id} is another article's cover already: choose another")
    key, url, width, height, size = await _store(library, store, story_id, photo, data)
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
    others = [Photo.from_json(c) for c in row.candidates]
    taken = await used_elsewhere(session, row.company_id, row.story_id, others)
    free = [i for i, p in enumerate(others) if p.id not in taken]
    if not free:
        raise CoverError("no other photo from this search: nothing to swap to")
    photo = others[free[0]]
    key, url, width, height, size = await _store(library, store, row.story_id, photo)
    old = row.key
    rest = [c for i, c in enumerate(row.candidates) if i != free[0]]
    row.candidates = [*rest, row.photo] if row.photo else rest
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
