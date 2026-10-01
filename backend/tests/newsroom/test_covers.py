"""D-142: an article's cover — cut to 1200x630 WebP, stored in R2 (Signature V4), swapped or
taken off by a person; Pixabay's key never shows in an error."""

import base64
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
    # not an image: nothing is sent, nothing fails
    assert await viewer.look_at("broken", b"not an image") == (None, 0)
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


async def test_gemini_draws_a_wide_image_with_the_site_rules_and_its_key_in_a_header():
    # D-145: a cover the library cannot give
    out = io.BytesIO()
    Image.new("RGB", (1344, 768), (10, 20, 80)).save(out, "PNG")
    seen = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "here"},
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(out.getvalue()).decode(),
                                    }
                                },
                            ]
                        }
                    }
                ]
            },
        )

    painter = covers.GeminiPainter(
        "SECRET-KEY",
        "gemini-3.1-flash-image",
        0.04,
        client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    data, cost = await painter.paint("a dark-blue 3D dashboard of portfolio holdings")
    assert data == out.getvalue() and cost == Decimal("0.04")
    request = seen["request"]
    assert request.headers["x-goog-api-key"] == "SECRET-KEY" and "SECRET" not in str(request.url)
    assert "gemini-3.1-flash-image:generateContent" in str(request.url)
    body = json.loads(request.content)
    assert body["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9"
    assert "no text" in body["contents"][0]["parts"][0]["text"]
    assert covers.cut_cover(data)[1:] == (1200, 630)

    refused = covers.GeminiPainter(
        "SECRET-KEY",
        "m",
        0.04,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"candidates": []}))
        ),
    )
    with pytest.raises(covers.CoverError, match="no image"):
        await refused.paint("anything at all, twenty chars")


async def test_a_generated_cover_is_the_cover_keeps_the_library_photos_and_has_a_daily_cap(
    db_session, tmp_path
):
    from autora.domains.newsroom.tools.covers import GenerateCoverArgs, generate_cover_tool
    from autora.runtime.actor import Actor
    from autora.runtime.tools import ToolContext

    company = await unique_company(db_session, "covers")
    story = Story(company_id=company.id, title="13F", state="SELECTED")
    db_session.add(story)
    await db_session.flush()
    library, store = covers.FixtureLibrary(), covers.BlobCoverStore(LocalFSBlobStore(tmp_path))
    found = await library.search("financial report")
    await covers.set_cover(
        db_session,
        company_id=company.id,
        story_id=story.id,
        photo=found[0],
        candidates=found,
        alt={},
        query="financial report",
        library=library,
        store=store,
        run_id=None,
    )
    ctx = ToolContext(
        session=db_session,
        company_id=company.id,
        actor=Actor.system("test"),
        tool_call_id="t",
        idempotency_key="k",
    )
    args = GenerateCoverArgs(
        story_id=story.id,
        prompt="a sleek dark-blue 3D dashboard of portfolio holdings",
        alt_zh="深藍色的持股儀表板",
        alt_en="A dark-blue holdings dashboard",
    )
    tool = generate_cover_tool(covers.FixturePainter(), store, None, per_day=1)
    result = await tool(args, ctx)
    row = await covers.cover_of(db_session, story.id)
    assert row.provider == "gemini" and row.credit == "AI 生成示意圖" and row.page_url == ""
    assert (row.width, row.height) == (1200, 630) and result.output["photo_id"] == row.provider_id
    # the library photo it replaced is first to swap back to
    assert [c["id"] for c in row.candidates][:2] == [found[0].id, found[1].id]
    with pytest.raises(covers.CoverError, match="today"):
        await tool(args, ctx)


async def test_a_generated_image_is_looked_at_closely():
    # D-147: a small symbol (a crypto logo on a wallet) is missed at low detail
    sent = {}

    def answer(request: httpx.Request) -> httpx.Response:
        sent["body"] = json.loads(request.content)
        said = {
            "images": [{"photo_id": "g", "looks": "a wallet", "text_or_logo": "Ethereum symbol"}]
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(said)}}], "usage": {}},
        )

    viewer = covers.ImageViewer(
        base_url="https://model.test/v1",
        api_key="k",
        model="m",
        price_in=0.2,
        price_out=1.2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    data, cost = await covers.FixturePainter().paint("a wallet")
    looked, _ = await viewer.look_at("g", data)
    assert looked["text_or_logo"] == "Ethereum symbol"
    [image] = [c for c in sent["body"]["messages"][1]["content"] if c["type"] == "image_url"]
    assert image["image_url"]["detail"] == "high"


def test_the_brands_a_story_names():
    # D-150: in Chinese, by ticker, as a whole word in its own case
    from autora.domains.newsroom.brands import named

    def slugs(text):
        return [b.slug for b in named(text)]

    assert slugs("減持輝達逾五成、出清台積電，新建倉阿里巴巴") == ["nvidia", "tsmc", "alibaba"]
    assert slugs("Circle與Tether凍結穩定幣") == ["circle", "tether"]
    assert slugs("Bitcoin ETF 與 ETH") == ["bitcoin", "ethereum"]
    assert slugs("an arm of the firm, a meta-analysis, an x-ray") == []


async def test_a_generated_cover_draws_the_story_s_own_logos_and_no_other(db_session, tmp_path):
    from autora.domains.newsroom.tools.covers import GenerateCoverArgs, generate_cover_tool
    from autora.runtime.actor import Actor
    from autora.runtime.tools import ToolContext

    company = await unique_company(db_session, "covers")
    story = Story(company_id=company.id, title="Circle與Tether凍結被盜的穩定幣", state="SELECTED")
    db_session.add(story)
    await db_session.flush()
    blobs = LocalFSBlobStore(tmp_path)
    store = covers.BlobCoverStore(blobs)
    await blobs.put("brand/tether.png", b"tether-png")
    asked = {}

    class Recording(covers.FixturePainter):
        async def paint(self, prompt, references=None):
            asked["references"] = references
            return await super().paint(prompt, references)

    ctx = ToolContext(
        session=db_session,
        company_id=company.id,
        actor=Actor.system("test"),
        tool_call_id="t",
        idempotency_key="k",
    )
    tool = generate_cover_tool(Recording(), store, None, per_day=5)

    def args(*slugs):
        return GenerateCoverArgs(
            story_id=story.id,
            prompt="two coins on a dark glass table, one bearing the Tether logo",
            alt_zh="兩枚硬幣",
            alt_en="Two coins",
            brands=list(slugs),
        )

    await tool(args("tether"), ctx)
    assert asked["references"] == [("Tether", b"tether-png")]
    with pytest.raises(covers.CoverError, match="not a brand this story is about"):
        await tool(args("bitcoin"), ctx)
    with pytest.raises(covers.CoverError, match="no logo is kept"):
        await tool(args("circle"), ctx)  # named, but no logo kept here


async def test_gemini_is_shown_the_logos_as_images():
    seen = {}
    out = io.BytesIO()
    Image.new("RGB", (64, 36)).save(out, "PNG")

    def answer(request):
        seen["body"] = json.loads(request.content)
        part = {"inlineData": {"data": base64.b64encode(out.getvalue()).decode()}}
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [part]}}]})

    painter = covers.GeminiPainter(
        "k", "m", 0.04, client=httpx.AsyncClient(transport=httpx.MockTransport(answer))
    )
    await painter.paint("two coins on a table", [("Tether", b"PNG-BYTES")])
    parts = seen["body"]["contents"][0]["parts"]
    assert "official logos" in parts[0]["text"]
    assert parts[1] == {"text": "Official logo of Tether:"}
    assert base64.b64decode(parts[2]["inlineData"]["data"]) == b"PNG-BYTES"
