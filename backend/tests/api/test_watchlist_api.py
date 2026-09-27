"""D-060: a signed-in reader's own watchlist."""

import re

import httpx
import pytest

URL = "/api/me/watchlist"


@pytest.fixture
async def site(api):
    """A reader's browser: no operator token, only its own cookie."""
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def other(api):
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


async def _sign_in(client, mailbox, address):
    mailbox.sent.clear()
    assert (await client.post("/api/auth/link", json={"email": address})).status_code == 202
    token = re.search(r"token=([A-Za-z0-9_\-]+)", mailbox.sent[0].text).group(1)
    assert (await client.post("/api/auth/verify", json={"token": token})).status_code == 200


async def test_a_new_list_starts_with_the_strip_s_stocks_once(site, mailbox):
    """D-062: a first look fills it with the market strip's twenty; emptied, it stays empty."""
    await _sign_in(site, mailbox, "watcher@example.com")
    first = (await site.get(URL, params={"lang": "zh-TW"})).json()
    assert len(first) == 20
    assert first[0] == {"symbol": "2330", "market": "tw", "key": "tw:2330", "name": "台積電",
                        "exchange": None}  # fmt: skip
    assert [s["key"] for s in first][7:9] == ["us:NVDA", "us:AAPL"]  # Taiwan's, then the US's
    for stock in first:
        assert (await site.delete(f"{URL}/{stock['symbol']}")).status_code == 204
    assert (await site.get(URL)).json() == []  # not filled again
    for symbol in ("nvda", "2330", "NVDA"):  # any case; the same stock twice is still once
        assert (await site.post(f"{URL}/{symbol}")).status_code == 204
    assert [s["symbol"] for s in (await site.get(URL)).json()] == ["NVDA", "2330"]
    assert (await site.get(URL, params={"lang": "en"})).json()[1]["name"] == "TSMC"


async def test_one_reader_s_list_is_not_another_s(site, other, mailbox):
    await _sign_in(site, mailbox, "one@example.com")
    await _sign_in(other, mailbox, "two@example.com")
    await site.get(URL)
    await site.delete(f"{URL}/2330")
    assert "tw:2330" in [s["key"] for s in (await other.get(URL)).json()]


async def test_only_stocks_with_a_page_and_only_when_signed_in(site, mailbox):
    assert (await site.get(URL)).status_code == 401
    assert (await site.post(f"{URL}/NVDA")).status_code == 401
    await _sign_in(site, mailbox, "watcher2@example.com")
    assert (await site.post(f"{URL}/NOPE")).status_code == 404


async def test_stocks_added_together_keep_the_order_they_were_added_in(db_session):
    """Three in one transaction share created_at: the id (uuid7) keeps them in order."""
    from autora.accounts import request_link, watchlist

    reader = (await request_link(db_session, "order@example.com")).reader
    for market, symbol in (("us", "NVDA"), ("tw", "2330"), ("us", "TSM"), ("us", "AAPL")):
        await watchlist.add(db_session, reader.id, market, symbol)
    assert [s for _, s in await watchlist.items(db_session, reader.id)] == [
        "NVDA",
        "2330",
        "TSM",
        "AAPL",
    ]


async def test_any_listed_stock_can_be_kept_and_is_then_tracked(site, mailbox, db_session):
    """D-061: beyond the strip's twenty — and keeping one tracks it, without saying who."""
    from sqlalchemy import select

    from autora.domains.newsroom import securities
    from autora.domains.newsroom.models import TrackedSecurity

    await securities.store(
        db_session, [securities.Listed("tw", "6488", "環球晶", None, "TPEx", "stock")]
    )
    await _sign_in(site, mailbox, "wide@example.com")
    assert (await site.post(f"{URL}/6488")).status_code == 204
    assert (await site.get(URL)).json()[-1] == {
        "symbol": "6488", "market": "tw", "key": "tw:6488", "name": "環球晶", "exchange": "TPEx"
    }  # fmt: skip
    tracked = await db_session.scalar(
        select(TrackedSecurity).where(TrackedSecurity.symbol == "6488")
    )
    assert tracked is not None and not hasattr(tracked, "reader_id")
