"""HD-03: which US ticker a 13F CUSIP is — OpenFIGI's answers read, asked once, kept. The answers
are shaped as OpenFIGI gave them on 2026-10-06 (trimmed to the fields read)."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from autora.domains.newsroom import cusips
from autora.domains.newsroom.cusips import CusipError, Listing, OpenFigi, map_cusips, symbols
from autora.domains.newsroom.holdings import HoldingsKeeper
from autora.domains.newsroom.markets import edgar_13f
from autora.domains.newsroom.models import CusipSymbol, PortfolioPosition, PortfolioQuarter, Source
from autora.infra.http import FetchError
from tests.conftest import unique_company


def listing(ticker, exch, sector="Equity", kind="Common Stock", name=None):
    return {
        "ticker": ticker,
        "exchCode": exch,
        "marketSector": sector,
        "securityType": kind,
        "name": name or ticker,
    }


ANSWERS = {
    "037833100": {"data": [listing("AAPL", "UN"), listing("AAPL", "US", name="APPLE INC")]},
    "084670702": {"data": [listing("BRK/B", "US", name="BERKSHIRE HATHAWAY INC-CL B")]},
    "874039100": {"data": [listing("TSM", "US", kind="ADR")]},
    "G54950103": {"data": [listing("LIN", "US", name="LINDE PLC")]},
    "285512109": {"data": [listing("EA", "US", name="ELECTRONIC ARTS INC")]},
    "116794207": {"data": [listing("BRKR 6 3/8", "US", sector="Pfd", kind="Preference")]},
    "H1467J104": {"warning": "No identifier found."},
}


def test_the_us_composite_listing_is_the_ticker_as_the_site_writes_it():
    assert cusips.read(ANSWERS["037833100"]) == Listing("AAPL", "APPLE INC", "Common Stock")
    assert cusips.read(ANSWERS["084670702"]).symbol == "BRK.B"
    assert cusips.read(ANSWERS["874039100"]) == Listing("TSM", "TSM", "ADR")


def test_no_us_common_stock_no_ticker():
    # a preferred share is listed, but it is not the company's stock: no ticker, its name kept
    assert cusips.read(ANSWERS["116794207"]) == Listing(None, "BRKR 6 3/8", "Preference")
    bond = {"data": [listing("GPN 1.5 03/01/31", "TRACE", sector="Corp", kind="US DOMESTIC")]}
    assert cusips.read(bond).symbol is None
    assert cusips.read({"warning": "No identifier found."}) == Listing(None, None, None)
    assert cusips.read({"error": "Invalid idValue format."}).symbol is None


def test_a_code_beginning_with_a_letter_is_asked_as_a_cins_and_unlisted_ones_too():
    assert cusips.job("G54950103") == {
        "idType": "ID_CINS",
        "idValue": "G54950103",
        "includeUnlistedEquities": True,
    }
    assert cusips.job("285512109")["idType"] == "ID_CUSIP"


class Figi:
    """OpenFIGI as the tests need it: ``ANSWERS``, the requests it got, a request that fails."""

    def __init__(self, fail_at: int | None = None):
        self.requests: list[list[dict]] = []
        self.fail_at = fail_at

    async def __call__(self, url, body):
        assert url == cusips.OPENFIGI
        self.requests.append(body)
        if self.fail_at is not None and len(self.requests) == self.fail_at:
            raise CusipError("OpenFIGI: 429 Too Many Requests")
        return [ANSWERS.get(job["idValue"], {"warning": "No identifier found."}) for job in body]


@pytest.fixture
async def quarter(db_session):
    company = await unique_company(db_session)
    source = Source(
        company_id=company.id,
        name="SEC 13F：test",
        kind="rss",
        url=edgar_13f("0000000001"),
        config={"title_prefix": "test", "primary": True, "section": "holdings"},
    )
    db_session.add(source)
    await db_session.flush()
    held = PortfolioQuarter(
        company_id=company.id,
        source_id=source.id,
        period=date(2026, 6, 30),
        filed=date(2026, 8, 14),
        filings=[{"cik": "1", "accession": "0000000001-26-000001"}],
        total_value_usd=0,
    )
    db_session.add(held)
    await db_session.flush()
    for cusip, put_call, kind in (
        ("037833100", "", "SH"),
        ("037833100", "CALL", "SH"),  # the same stock's options: one CUSIP, asked once
        ("084670702", "", "SH"),
        ("G54950103", "", "SH"),
        ("116794207", "", "SH"),
        ("H1467J104", "", "SH"),
        ("37940XAU6", "", "PRN"),  # a note: principal, never a ticker, never asked
    ):
        db_session.add(
            PortfolioPosition(
                quarter_id=held.id,
                cusip=cusip,
                issuer="x",
                title_of_class="COM",
                put_call=put_call,
                kind=kind,
                amount=1,
                value_usd=1,
            )
        )
    await db_session.flush()
    return company


NOW = datetime(2026, 10, 6, tzinfo=UTC)


async def test_the_kept_quarters_cusips_are_asked_once_and_kept(db_session, quarter):
    figi = Figi()
    ask = lambda now: map_cusips(  # noqa: E731
        db_session, quarter.id, OpenFigi(figi, keyed=False, pause=0), now=now
    )
    asked = await ask(NOW)
    assert asked == 5
    assert len(figi.requests) == 1 and {j["idValue"] for j in figi.requests[0]} == {
        "037833100", "084670702", "116794207", "G54950103", "H1467J104",
    }  # fmt: skip
    found = await symbols(
        db_session, ["037833100", "084670702", "G54950103", "116794207", "H1467J104"]
    )
    assert found == {"037833100": "AAPL", "084670702": "BRK.B", "G54950103": "LIN"}
    chubb = await db_session.get(CusipSymbol, "H1467J104")
    assert chubb.symbol is None and chubb.checked_at == NOW

    # asked again: nothing — until a CUSIP without a ticker is older than RECHECK
    assert await ask(NOW) == 0
    later = NOW + cusips.RECHECK + timedelta(days=1)
    figi.requests.clear()
    assert await ask(later) == 2
    assert {j["idValue"] for j in figi.requests[0]} == {"116794207", "H1467J104"}


async def test_answers_are_kept_as_they_come(db_session, quarter):
    """Ten CUSIPs a request without a key: here two, the second failing — the first's stay."""
    figi = OpenFigi(Figi(fail_at=2), keyed=False, pause=0)
    figi.batch = 2
    with pytest.raises(CusipError):
        await map_cusips(db_session, quarter.id, figi, now=NOW)
    kept = (await db_session.scalars(select(CusipSymbol.cusip))).all()
    assert set(kept) >= {"037833100", "084670702"}


def test_a_key_asks_a_hundred_at_a_time():
    assert (OpenFigi(Figi(), keyed=True).batch, OpenFigi(Figi(), keyed=False).batch) == (100, 10)


async def test_an_answer_that_does_not_fit_is_an_error():
    async def short(url, body):
        return body[:-1]

    with pytest.raises(CusipError, match="for 2 CUSIPs"):
        await OpenFigi(short, keyed=False).ask(["037833100", "084670702"])


async def test_the_holdings_run_maps_its_new_cusips_and_a_failure_is_only_a_warning(
    db_session, quarter
):
    class SecDown:
        async def fetch(self, url):
            raise FetchError("SEC is down")  # the 13F refresh is skipped; the mapping goes on

    run = SimpleNamespace(company_id=quarter.id)
    failing = HoldingsKeeper(SecDown(), OpenFigi(Figi(fail_at=1), keyed=False, pause=0))
    await failing.schedule_handler()(db_session, run, NOW)  # logged, not raised
    assert await db_session.get(CusipSymbol, "037833100") is None

    keeper = HoldingsKeeper(SecDown(), OpenFigi(Figi(), keyed=False, pause=0))
    await keeper.schedule_handler()(db_session, run, NOW)
    assert (await db_session.get(CusipSymbol, "037833100")).symbol == "AAPL"
