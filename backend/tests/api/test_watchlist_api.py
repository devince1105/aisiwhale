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
    """D-062: a first look fills it with the market strip as it is; emptied, it stays empty."""
    from autora.domains.newsroom.market_strip import ORDER

    await _sign_in(site, mailbox, "watcher@example.com")
    first = (await site.get(URL, params={"lang": "zh-TW"})).json()
    assert [s["key"] for s in first] == list(ORDER)  # the strip's own order, all of it
    assert first[0] == {"symbol": "TAIEX", "market": "market", "key": "taiex",
                        "name": "加權指數", "exchange": None}  # fmt: skip
    assert first[1]["name"] == "台積電" and first[-1]["name"] == "以太幣"
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


async def test_the_strip_s_other_figures_come_and_go_like_stocks(site, mailbox):
    await _sign_in(site, mailbox, "coins@example.com")
    await site.get(URL)
    assert (await site.delete(f"{URL}/btc")).status_code == 204
    keys = [s["key"] for s in (await site.get(URL)).json()]
    assert "btc" not in keys and "eth" in keys
    assert (await site.post(f"{URL}/BTC")).status_code == 204
    listed = (await site.get(URL, params={"lang": "en"})).json()
    assert listed[-1] == {"symbol": "BTC", "market": "market", "key": "btc", "name": "Bitcoin",
                          "exchange": None}  # fmt: skip
    assert (await site.post(f"{URL}/DOGE")).status_code == 404  # not on the strip


async def test_a_reader_puts_the_list_in_their_own_order(site, mailbox):
    """D-063: dragged into place; the order is kept, and what is added later goes last."""
    await _sign_in(site, mailbox, "order2@example.com")
    first = [s["key"] for s in (await site.get(URL)).json()]
    wanted = ["btc", "us:NVDA", "tw:2330"]
    assert (await site.put(URL, json={"keys": [*wanted, "us:NOPE"]})).status_code == 204
    after = [s["key"] for s in (await site.get(URL)).json()]
    assert after[:3] == wanted  # the ones named first, in that order (the unknown ignored)
    assert after[3:] == [k for k in first if k not in wanted]  # the rest after, as they were
    await site.delete(f"{URL}/ETH")
    await site.post(f"{URL}/ETH")
    assert [s["key"] for s in (await site.get(URL)).json()][-1] == "eth"  # re-added: last


async def test_only_a_signed_in_reader_orders_a_list(other):
    assert (await other.put(URL, json={"keys": ["btc"]})).status_code == 401
