"""P4 (D-249): COIN articles — read for Whale Coins, each reader paying once, VIP or not.

As with VIP articles (``test_paywall``), the point is mostly the negative one: a reader who has
not paid never receives the rest of the text. Then the paying: once, at the price of the
moment, written beside the spend that paid for it, and theirs whatever the article becomes.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from autora.accounts import credentials
from autora.accounts.coins import ArticleUnlock, CoinTxn, TxnKind, grant
from autora.company import memberships
from autora.company.organization import add_business_unit, add_product
from autora.db.models import AdminAction, BusinessUnitState, Company, ProductState
from autora.domains.newsroom.models import Article, ArticleAccess
from autora.domains.newsroom.site import lock_for, may_read
from autora.runtime.actor import Actor
from tests.api.conftest import ADMIN
from tests.api.readers import PASSWORD, sign_in_id

OPERATOR = Actor.human("operator")
SYSTEM = Actor.system("coin-articles-test")
READER = "coin-reader@example.com"


@pytest.fixture
async def site(api):
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def article(newsroom_room):
    article_id = await newsroom_room.publish()
    async with newsroom_room.committed() as session:
        return await session.get(Article, uuid.UUID(article_id))


async def _set(newsroom_room, article, access: ArticleAccess, price: int | None = None):
    async with newsroom_room.committed() as session:
        row = await session.get(Article, article.id)
        row.access = access.value
        row.coin_price = price
        await session.commit()


async def _fill(db_session, reader_id, coins: int) -> None:
    await grant(
        db_session, reader_id, requested=coins, cap=coins, kind=TxnKind.PROMOTION_GRANT,
        idempotency_key=f"promo:p4:{reader_id}", actor=SYSTEM,
    )  # fmt: skip
    await db_session.commit()


async def _read(site, article) -> dict:
    response = await site.get(f"/api/public/articles/zh-TW/{article.slug}")
    assert response.status_code == 200, response.text
    return response.json()


async def _count(db_session, model, **where) -> int:
    stmt = select(func.count()).select_from(model)
    for key, value in where.items():
        stmt = stmt.where(getattr(model, key) == value)
    return await db_session.scalar(stmt)


def _unlock(site, article):
    return site.post(f"/api/me/unlocks/{article.id}")


# --- the lock -----------------------------------------------------------------------------------


def test_coin_comes_before_signing_in_and_a_membership_does_not_open_it():
    assert lock_for("coin", "holdings") == "coin", "a 持股觀察 article set to COIN is paid for"
    assert lock_for("free", "holdings") == "sign_in", "one not set to COIN: signing in is enough"
    assert lock_for("members", None) == "members"
    assert lock_for("free", "ai") is None
    assert not may_read("coin", "member"), "VIP pays coins like anybody (D-249)"
    assert not may_read("coin", "signed_in")
    assert may_read("coin", "paid") and may_read("coin", "staff")
    assert not may_read("members", "paid"), "paying for one COIN article opens nothing else"
    assert may_read("sign_in", "signed_in") and may_read("members", "member")


async def test_a_stranger_gets_the_opening_the_price_and_no_sources(site, article, newsroom_room):
    whole = await _read(site, article)
    await _set(newsroom_room, article, ArticleAccess.COIN, 5)
    body = await _read(site, article)
    assert (body["access"], body["lock"], body["locked"], body["coin_price"]) == (
        "coin", "coin", True, 5,
    )  # fmt: skip
    assert body["unlocked"] is False
    assert len(body["blocks"]) < len(whole["blocks"])
    assert body["sources"] == []
    rest = whole["blocks"][-1]["text"]
    assert rest not in (await site.get(f"/api/public/articles/zh-TW/{article.slug}")).text


async def test_the_list_says_what_it_costs(site, article, newsroom_room):
    await _set(newsroom_room, article, ArticleAccess.COIN, 7)
    listed = (await site.get("/api/public/articles", params={"lang": "zh-TW"})).json()
    (mine,) = [row for row in listed if row["slug"] == article.slug]
    assert (mine["access"], mine["coin_price"]) == ("coin", 7)


async def test_signing_in_is_not_paying(site, article, newsroom_room):
    await _set(newsroom_room, article, ArticleAccess.COIN, 5)
    await sign_in_id(site, READER)
    assert (await _read(site, article))["locked"] is True


# --- unlocking ----------------------------------------------------------------------------------


async def test_nobody_signed_in_unlocks_nothing(site, article, newsroom_room):
    await _set(newsroom_room, article, ArticleAccess.COIN, 5)
    assert (await _unlock(site, article)).status_code == 401
    assert (await site.get("/api/me/unlocks")).status_code == 401


async def test_only_a_published_coin_article_is_unlocked(site, db_session, article):
    reader = await sign_in_id(site, READER)
    await _fill(db_session, reader, 50)
    assert (await _unlock(site, article)).status_code == 404, "a free article costs nothing"
    assert (await site.post(f"/api/me/unlocks/{uuid.uuid4()}")).status_code == 404
    assert await _count(db_session, CoinTxn, reader_id=reader, kind="SPEND") == 0


async def test_unlocking_spends_the_price_once_and_opens_the_whole_article(
    site, db_session, article, newsroom_room
):
    whole = await _read(site, article)
    await _set(newsroom_room, article, ArticleAccess.COIN, 5)
    reader = await sign_in_id(site, READER)
    await _fill(db_session, reader, 50)

    first = await _unlock(site, article)
    assert first.status_code == 201, first.text
    assert first.json() == {
        "article_id": str(article.id), "unlocked": True, "already": False, "price": 5,
        "balance": 45,
    }  # fmt: skip
    (txn,) = (
        await db_session.scalars(
            select(CoinTxn).where(CoinTxn.reader_id == reader, CoinTxn.kind == "SPEND")
        )
    ).all()
    assert (txn.amount, txn.idempotency_key, txn.ref_type, txn.ref_id) == (
        -5, f"spend:article:{reader}:{article.id}", "article", str(article.id),
    )  # fmt: skip
    assert txn.meta == {"price": 5, "slug": article.slug}
    assert txn.actor == {"kind": "human", "id": f"reader:{reader}"}
    (unlock,) = (
        await db_session.scalars(select(ArticleUnlock).where(ArticleUnlock.reader_id == reader))
    ).all()
    assert (unlock.article_id, unlock.coin_txn_id, unlock.price_paid) == (article.id, txn.id, 5)

    body = await _read(site, article)
    assert (body["locked"], body["unlocked"], body["lock"]) == (False, True, "coin")
    assert [b["text"] for b in body["blocks"]] == [b["text"] for b in whole["blocks"]]
    assert body["sources"] == whole["sources"]

    again = await _unlock(site, article)
    assert again.status_code == 200, again.text
    assert (again.json()["already"], again.json()["price"], again.json()["balance"]) == (
        True, 5, 45,
    )  # fmt: skip
    assert await _count(db_session, CoinTxn, reader_id=reader, kind="SPEND") == 1
    assert await _count(db_session, ArticleUnlock, reader_id=reader) == 1


async def test_not_enough_coins_is_402_and_writes_nothing(site, db_session, article, newsroom_room):
    await _set(newsroom_room, article, ArticleAccess.COIN, 5)
    reader = await sign_in_id(site, READER)
    await _fill(db_session, reader, 3)
    response = await _unlock(site, article)
    assert response.status_code == 402
    body = response.json()
    assert (body["detail"], body["need"], body["held"]) == ("not enough coins", 5, 3)
    assert await _count(db_session, CoinTxn, reader_id=reader, kind="SPEND") == 0
    assert await _count(db_session, ArticleUnlock, reader_id=reader) == 0
    assert (await _read(site, article))["locked"] is True


@pytest.mark.parametrize("price", [1, 100])
async def test_the_cheapest_and_the_dearest(site, db_session, article, newsroom_room, price):
    await _set(newsroom_room, article, ArticleAccess.COIN, price)
    reader = await sign_in_id(site, READER)
    await _fill(db_session, reader, 100)
    response = await _unlock(site, article)
    assert response.status_code == 201, response.text
    assert (response.json()["price"], response.json()["balance"]) == (price, 100 - price)


async def test_a_vip_pays_too(api, site, db_session, article, newsroom_room):
    company = await db_session.get(Company, article.company_id)
    unit = await add_business_unit(
        db_session, company_id=company.id, key="ai_media", name="AI Media",
        actor=OPERATOR, state=BusinessUnitState.ACTIVE,
    )  # fmt: skip
    await add_product(
        db_session, company_id=company.id, key=memberships.PRODUCT_KEY, name="Membership",
        business_unit_id=unit.id, actor=OPERATOR, state=ProductState.LIVE,
    )  # fmt: skip
    await db_session.commit()
    reader = await sign_in_id(site, READER)
    until = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    comp = await api.post(
        "/api/admin/memberships/comps",
        json={"email": READER, "until": until, "reason": "p4", "company": company.slug},
    )
    assert comp.status_code == 201, comp.text
    await _set(newsroom_room, article, ArticleAccess.COIN, 5)

    assert (await _read(site, article))["locked"] is True, "VIP does not open a COIN article"
    await _fill(db_session, reader, 10)
    assert (await _unlock(site, article)).status_code == 201
    assert (await _read(site, article))["locked"] is False


async def test_what_was_paid_for_stays_paid_for(site, db_session, article, newsroom_room):
    await _set(newsroom_room, article, ArticleAccess.COIN, 5)
    reader = await sign_in_id(site, READER)
    await _fill(db_session, reader, 50)
    assert (await _unlock(site, article)).status_code == 201

    await _set(newsroom_room, article, ArticleAccess.COIN, 9)  # dearer now
    assert (await _read(site, article))["unlocked"] is True
    again = await _unlock(site, article)
    assert (again.status_code, again.json()["price"], again.json()["balance"]) == (200, 5, 45)

    await _set(newsroom_room, article, ArticleAccess.FREE)  # free, then COIN again
    assert (await _read(site, article))["locked"] is False
    await _set(newsroom_room, article, ArticleAccess.COIN, 3)
    assert (await _read(site, article))["unlocked"] is True
    assert await _count(db_session, CoinTxn, reader_id=reader, kind="SPEND") == 1


async def test_an_admin_reads_it_without_paying(site, db_session, article, newsroom_room):
    """Blueprint §6: COIN articles are open to an admin. Nothing is spent or recorded."""
    admin = await credentials.register(db_session, ADMIN, PASSWORD)
    await credentials.verify_email(db_session, admin.verify_token)
    await db_session.commit()
    signed = await site.post("/api/auth/login", json={"email": ADMIN, "password": PASSWORD})
    assert signed.status_code == 200, signed.text
    await _set(newsroom_room, article, ArticleAccess.COIN, 5)
    body = await _read(site, article)
    assert (body["locked"], body["unlocked"]) == (False, False)
    assert await _count(db_session, ArticleUnlock, reader_id=admin.reader.id) == 0


async def test_a_reader_s_unlocks_and_their_wallet_name_the_article(
    site, db_session, article, newsroom_room
):
    await _set(newsroom_room, article, ArticleAccess.COIN, 5)
    reader = await sign_in_id(site, READER)
    await _fill(db_session, reader, 50)
    assert (await site.get("/api/me/unlocks")).json() == []
    await _unlock(site, article)

    (mine,) = (await site.get("/api/me/unlocks")).json()
    assert (mine["article_id"], mine["price_paid"]) == (str(article.id), 5)

    company = await db_session.get(Company, article.company_id)
    wallet = (await site.get("/api/me/coins", params={"company": company.slug})).json()
    spent, granted = wallet["history"]["items"]
    assert (spent["kind"], spent["amount"]) == ("SPEND", -5)
    assert spent["article"] == {
        "title": article.title,
        "path": f"/news/{article.primary_lang}/articles/{article.slug}",
    }
    assert granted["article"] is None


# --- setting it, in the back office --------------------------------------------------------------

ACCESS = "/api/articles/{}/access"


async def test_coin_is_set_at_5_unless_a_price_is_given(api, db_session, article):
    url = ACCESS.format(article.id)
    response = await api.post(url, json={"access": "coin"})
    assert response.status_code == 200, response.text
    assert response.json() == {"article_id": str(article.id), "access": "coin", "coin_price": 5}
    assert (await api.post(url, json={"access": "coin", "coin_price": 12})).json()[
        "coin_price"
    ] == 12
    back = await api.post(url, json={"access": "members"})
    assert back.json() == {"article_id": str(article.id), "access": "members", "coin_price": None}
    row = await db_session.get(Article, article.id)
    await db_session.refresh(row)
    assert (row.access, row.coin_price) == ("members", None)
    record = await db_session.scalar(
        select(func.count())
        .select_from(AdminAction)
        .where(AdminAction.route == ACCESS.format("{article_id}"))
    )
    assert record == 3, "every change is in the back office's record"


@pytest.mark.parametrize(
    "body",
    [
        {"access": "coin", "coin_price": 0},
        {"access": "coin", "coin_price": 101},
        {"access": "coin", "coin_price": 1.5},
        {"access": "free", "coin_price": 5},
        {"access": "gold"},
    ],
)
async def test_what_is_not_a_price_is_refused(api, db_session, article, body):
    assert (await api.post(ACCESS.format(article.id), json=body)).status_code == 422
    row = await db_session.get(Article, article.id)
    await db_session.refresh(row)
    assert (row.access, row.coin_price) == ("free", None)


async def test_only_the_back_office_sets_it(site, article):
    assert (await site.post(ACCESS.format(article.id), json={"access": "coin"})).status_code == 401
    await sign_in_id(site, READER)
    assert (await site.post(ACCESS.format(article.id), json={"access": "coin"})).status_code == 401
