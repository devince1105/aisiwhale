"""D-142: an article's cover — cut to 1200x630 WebP, stored in R2 (Signature V4), swapped or
taken off by a person; Pixabay's key never shows in an error."""

import io
import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from PIL import Image

from autora.domains.newsroom import covers
from autora.domains.newsroom.models import CoverState, Story
from autora.domains.newsroom.site import public_cover
from autora.infra.blobstore import LocalFSBlobStore
from tests.conftest import unique_company


def _jpeg(width: int, height: int) -> bytes:
    out = io.BytesIO()
    # detailed like a photo (not noise, which no format compresses)
    detail = Image.effect_mandelbrot((width, height), (-2.0, -1.2, 0.8, 1.2), 200)
    Image.merge("RGB", (detail, detail.rotate(90, expand=False), detail)).save(
        out, "JPEG", quality=95
    )
    return out.getvalue()


def test_a_photo_is_cut_to_1200_by_630_webp_and_kept_small():
    for size in ((1920, 1280), (1280, 1920), (1300, 600)):
        data, width, height = covers.cut_cover(_jpeg(*size))
        with Image.open(io.BytesIO(data)) as image:
            assert (image.format, image.size) == ("WEBP", (1200, 630))
        assert (width, height) == (1200, 630)
        assert len(data) <= covers.MAX_BYTES


def test_what_is_not_a_photo_is_refused():
    with pytest.raises(covers.CoverError):
        covers.cut_cover(b"<html>not an image</html>")


def test_the_r2_signature_is_aws_signature_v4():
    # AWS's worked example (S3 docs, "Signature Calculations for the Authorization Header":
    # GET Object), recomputed by the same function that signs the PUT to R2
    headers = covers.sigv4_headers(
        method="GET",
        host="examplebucket.s3.amazonaws.com",
        path="/test.txt",
        headers={"Range": "bytes=0-9"},
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        now=datetime(2013, 5, 24, tzinfo=UTC),
    )
    assert headers["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


async def test_r2_puts_the_webp_with_a_long_cache_and_returns_the_public_address():
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    store = covers.R2Store(
        account_id="acct",
        access_key_id="id",
        secret_access_key="secret",
        bucket="covers-bucket",
        public_base_url="https://img.example.test/",
        prefix="/news/images/",
        client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    url = await store.put("covers/s1/pixabay-1.webp", b"webp", "image/webp")
    # under the bucket's folder (R2_KEY_PREFIX), in the object's key and in its address
    assert url == "https://img.example.test/news/images/covers/s1/pixabay-1.webp"
    request = seen[0]
    assert request.method == "PUT"
    assert (
        str(request.url)
        == "https://acct.r2.cloudflarestorage.com/covers-bucket/news/images/covers/s1/pixabay-1.webp"
    )
    assert request.headers["content-type"] == "image/webp"
    assert "immutable" in request.headers["cache-control"]
    assert request.headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=id/")


async def test_pixabay_is_read_and_its_key_never_reaches_an_error():
    def answer(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "SECRET-KEY"
        assert request.url.params["min_width"] == "1200"
        assert request.url.params["image_type"] == "all"
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "id": 42,
                        "pageURL": "https://pixabay.com/photos/wafer-42/",
                        "largeImageURL": "https://pixabay.com/get/42_1280.jpg",
                        "imageWidth": 5000,
                        "imageHeight": 3000,
                        "tags": "wafer, chip, semiconductor",
                        "user": "someone",
                    },
                    {
                        "id": 43,
                        "type": "illustration",
                        "pageURL": "https://pixabay.com/illustrations/cpu-43/",
                        "largeImageURL": "https://pixabay.com/get/43_1280.jpg",
                        "imageWidth": 3840,
                        "imageHeight": 2160,
                        "tags": "processor, cpu, chip, 3d",
                        "user": "renderer",
                    },
                    {
                        "id": 44,
                        "type": "vector/svg",
                        "largeImageURL": "https://pixabay.com/get/44_1280.png",
                        "tags": "cpu, icon",
                        "user": "iconist",
                    },
                ]
            },
        )

    library = covers.Pixabay(
        "SECRET-KEY", client=httpx.AsyncClient(transport=httpx.MockTransport(answer))
    )
    # photos and illustrations; vector icons and clip art left out
    photo, render = await library.search("semiconductor wafer")
    assert (render.id, render.kind, render.for_model()["kind"]) == (
        "43",
        "illustration",
        "illustration",
    )
    assert (photo.id, photo.credit, photo.tags) == ("42", "someone", "wafer, chip, semiconductor")
    assert "url" not in str(photo.for_model()).lower()  # the model reads what it shows

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    broken = covers.Pixabay(
        "SECRET-KEY", client=httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    )
    with pytest.raises(covers.LibraryError) as caught:
        await broken.search("gold bars")
    assert "SECRET-KEY" not in str(caught.value) and caught.value.__cause__ is None


async def test_a_cover_is_set_swapped_and_taken_off(db_session, tmp_path):
    company = await unique_company(db_session, "covers")
    story = Story(company_id=company.id, title="Chips", state="SELECTED")
    db_session.add(story)
    await db_session.flush()
    library, blobs = covers.FixtureLibrary(), LocalFSBlobStore(tmp_path)
    store = covers.BlobCoverStore(blobs)
    found = await library.search("semiconductor wafer")

    row = await covers.set_cover(
        db_session,
        company_id=company.id,
        story_id=story.id,
        photo=found[0],
        candidates=found,
        alt={"zh-TW": "晶圓", "en": "A wafer"},
        query="semiconductor wafer",
        library=library,
        store=store,
        run_id=None,
    )
    first_key = row.key
    assert (row.width, row.height, row.provider_id) == (1200, 630, found[0].id)
    assert row.url == f"/api/public/{first_key}" and await blobs.exists(first_key)
    assert [c["id"] for c in row.candidates] == [found[1].id, found[2].id]
    shown = public_cover(row, "zh-TW")
    assert shown is not None and shown.alt == "晶圓" and shown.credit == found[0].credit

    await covers.swap_cover(db_session, row, library=library, store=store)
    assert row.provider_id == found[1].id
    assert not await blobs.exists(first_key) and await blobs.exists(row.key)
    # the one it replaced goes last, so swapping on comes back round to it
    assert [c["id"] for c in row.candidates] == [found[2].id, found[0].id]
    assert row.alt["en"].startswith("Illustration:")

    await covers.remove_cover(db_session, row, store=store)
    assert row.state == CoverState.REMOVED and public_cover(row, "en") is None
    with pytest.raises(covers.CoverError):
        await covers.set_cover(
            db_session,
            company_id=company.id,
            story_id=story.id,
            photo=found[2],
            candidates=found,
            alt={},
            query="semiconductor wafer",
            library=library,
            store=store,
            run_id=None,
        )
    # another story may not take the photo this one shows (D-144)
    other = Story(company_id=company.id, title="More chips", state="SELECTED")
    db_session.add(other)
    await db_session.flush()
    assert await covers.used_elsewhere(db_session, company.id, other.id, found) == set()
    # a person's 換一張 puts one back
    await covers.swap_cover(db_session, row, library=library, store=store)
    assert row.state == CoverState.ACTIVE


async def test_the_viewer_says_what_each_image_looks_like_and_what_it_cost():
    # D-144: marketing reads what an image looks like, not only the library's tags
    seen = {}

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["body"] = body
        images = [c for c in body["messages"][1]["content"] if c["type"] == "image_url"]
        assert len(images) == 2 and all(i["image_url"]["detail"] == "low" for i in images)
        assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "images": [
                                        {
                                            "photo_id": photos[0].id,
                                            "looks": "flat cartoon people at desks",
                                            "style": "cartoon",
                                            "dated": False,
                                            "text_or_logo": "none",
                                            "quality": "ok",
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            },
        )

    library = covers.FixtureLibrary()
    photos = await library.search("ai workflow")
    viewer = covers.ImageViewer(
        base_url="https://model.test/v1",
        api_key="k",
        model="m",
        price_in=0.2,
        price_out=1.2,
        max_tokens_field="max_completion_tokens",
        client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    looks, cost = await viewer.look(library, photos[:2])
    assert looks == {
        photos[0].id: {
            "looks": "flat cartoon people at desks",
            "style": "cartoon",
            "dated": False,
            "text_or_logo": "none",
            "quality": "ok",
        }
    }
    assert cost == Decimal("0.0008")  # 1000 x 0.2 + 500 x 1.2, per million
    assert seen["body"]["max_completion_tokens"] == 2000
    assert photos[0].for_model(looks[photos[0].id])["looks"]["style"] == "cartoon"
    # what it saw is kept: asking again about the same image costs nothing
    again, cost = await viewer.look(library, photos[:1])
    assert again and cost == 0


async def test_two_articles_do_not_share_a_cover(db_session, tmp_path):
    company = await unique_company(db_session, "covers")
    first, second = (Story(company_id=company.id, title=t, state="SELECTED") for t in ("A", "B"))
    db_session.add_all([first, second])
    await db_session.flush()
    library, store = covers.FixtureLibrary(), covers.BlobCoverStore(LocalFSBlobStore(tmp_path))
    found = await library.search("financial report")
    common = dict(
        company_id=company.id,
        candidates=found,
        alt={},
        query="financial report",
        library=library,
        store=store,
        run_id=None,
    )
    await covers.set_cover(db_session, story_id=first.id, photo=found[0], **common)
    assert await covers.used_elsewhere(db_session, company.id, second.id, found) == {found[0].id}
    with pytest.raises(covers.CoverError, match="another article"):
        await covers.set_cover(db_session, story_id=second.id, photo=found[0], **common)
    await covers.set_cover(db_session, story_id=second.id, photo=found[1], **common)
