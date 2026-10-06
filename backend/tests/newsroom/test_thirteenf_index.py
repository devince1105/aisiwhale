"""HD-08: every 13F filer's quarter, from SEC's daily index — an excerpt of 2026-08-14's index and
six real cover pages (``fixtures/sec/index``): Third Point's original; Artemis's original and its
restatement; Arini's original and the amendment adding new holdings to it; Sunflower Bank's
restated combination report. The edge cases against small made-up rows."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from autora.domains.newsroom import thirteenf, thirteenf_index
from autora.domains.newsroom.models import ThirteenFFiling, ThirteenFIndexDay
from autora.domains.newsroom.thirteenf_index import (
    NEW_HOLDINGS,
    NOTICE,
    RESTATEMENT,
    index_url,
    parse_daily_index,
    parse_summary,
    quarter_totals,
    read_index,
    read_summaries,
    read_summary,
    totals,
)
from autora.infra.http import FetchRefused, FetchUnavailable

INDEX = Path(__file__).parent / "fixtures" / "sec" / "index"
NOW = datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
Q2 = date(2026, 6, 30)


def cover(name: str) -> bytes:
    return (INDEX / f"{name}.xml").read_bytes()


def folder(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"


def sec(pages: dict[str, bytes], asked: list[str] | None = None):
    """SEC as a dict of addresses; anything else answers 404."""

    async def fetch(url: str) -> bytes:
        if asked is not None:
            asked.append(url)
        if url not in pages:
            raise FetchRefused(f"{url} answered 404")
        return pages[url]

    return fetch


# the six real filings: (cik, accession, fixture)
THIRD_POINT = ("1040273", "0001040273-26-000003", "1040273-26-000003")
ARTEMIS = ("1767435", "0001941040-26-000537", "1767435-26-000537")
ARTEMIS_RESTATED = ("1767435", "0001941040-26-000613", "1767435-26-000613")
ARINI = ("2056819", "0001172661-26-003320", "2056819-26-003320")
ARINI_ADDED = ("2056819", "0001172661-26-003819", "2056819-26-003819")
SUNFLOWER = ("1818759", "0001818759-26-000007", "1818759-26-000007")


def covers(*filings) -> dict[str, bytes]:
    return {f"{folder(cik, acc)}/primary_doc.xml": cover(name) for cik, acc, name in filings}


# --- what SEC says -------------------------------------------------------------------------------


def test_the_daily_index_lists_the_13f_hrs_and_their_amendments_only():
    rows = parse_daily_index((INDEX / "form.20260814.excerpt.idx").read_text("latin-1"))

    assert [(r.form, r.company, r.cik, r.accession) for r in rows] == [
        ("13F-HR", "&PARTNERS", "107136", "0001214659-26-010148"),
        ("13F-HR", "Alight Capital Management LP", "1651473", "0001104659-26-097164"),
        ("13F-HR", "Third Point LLC", "1040273", "0001040273-26-000003"),
        ("13F-HR/A", "Arini Capital Management Ltd", "2056819", "0001172661-26-003819"),
        ("13F-HR/A", "Artemis Wealth Advisors, LLC", "1767435", "0001941040-26-000613"),
        ("13F-HR/A", "Sunflower Bank, N.A.", "1818759", "0001818759-26-000007"),
    ]  # the notice (13F-NT), the 1-A and the header are not
    assert {r.filed for r in rows} == {date(2026, 8, 14)}


def test_a_company_name_ending_in_digits_is_not_taken_for_its_cik():
    line = (
        "13F-HR           Fund 2024 1234567                                             "
        "2001234     20260814    edgar/data/2001234/0002001234-26-000001.txt\n"
    )

    (row,) = parse_daily_index(line)

    assert (row.company, row.cik) == ("Fund 2024 1234567", "2001234")


def test_the_index_address_is_by_quarter_and_day():
    assert index_url(date(2026, 8, 14)) == (
        "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260814.idx"
    )
    assert index_url(date(2026, 4, 1)).endswith("/2026/QTR2/form.20260401.idx")


def test_a_cover_page_says_the_quarter_the_manager_and_the_totals():
    original = parse_summary(cover(THIRD_POINT[2]))
    restated = parse_summary(cover(ARTEMIS_RESTATED[2]))
    added = parse_summary(cover(ARINI_ADDED[2]))
    combination = parse_summary(cover(SUNFLOWER[2]))

    assert original == thirteenf_index.Summary(
        period=Q2,
        manager="Third Point LLC",
        amendment=None,
        report_type="13F HOLDINGS REPORT",
        entries=43,
        value_usd=4_679_571_988,
    )
    # the manager, not the person who signed, nor the other managers on the summary page
    assert restated.manager == "Artemis Wealth Advisors, LLC"
    assert (restated.amendment, restated.entries, restated.value_usd) == (
        RESTATEMENT,
        55,
        834_513_809,
    )
    assert (added.amendment, added.entries, added.value_usd) == (NEW_HOLDINGS, 28, 974_731_526)
    assert (combination.report_type, combination.amendment) == (
        "13F COMBINATION REPORT",
        RESTATEMENT,
    )


def test_what_is_not_a_cover_page_is_refused():
    with pytest.raises(thirteenf.FilingError, match="not a 13F cover page"):
        parse_summary(b"<informationTable><infoTable/></informationTable>")
    with pytest.raises(thirteenf.FilingError, match="DTD"):
        parse_summary(b'<!DOCTYPE x [<!ENTITY a "b">]><edgarSubmission/>')
    with pytest.raises(thirteenf.FilingError, match="no quarter"):
        parse_summary(b"<edgarSubmission><coverPage/></edgarSubmission>")


async def test_a_cover_page_not_called_primary_doc_is_found_in_the_folder():
    cik, accession, name = THIRD_POINT
    base = folder(cik, accession)
    pages = {
        f"{base}/index.json": (
            b'{"directory": {"item": [{"name": "0001.txt"}, {"name": "table.xml"},'
            b' {"name": "cover.xml"}]}}'
        ),
        f"{base}/table.xml": b"<informationTable><infoTable/></informationTable>",
        f"{base}/cover.xml": cover(name),
    }

    summary = await read_summary(sec(pages), cik, accession)

    assert summary.manager == "Third Point LLC"


# --- the runs ------------------------------------------------------------------------------------


async def test_the_index_is_read_newest_day_first_and_each_day_once(db_session):
    excerpt = (INDEX / "form.20260814.excerpt.idx").read_bytes()
    asked: list[str] = []
    fetch = sec({index_url(date(2026, 8, 14)): excerpt}, asked)
    today = date(2026, 8, 18)  # a Tuesday: Monday the 17th is listed first, then Friday the 14th

    listed = await read_index(db_session, fetch, today=today, limit=3, now=NOW)

    assert asked == [index_url(date(2026, 8, d)) for d in (17, 14, 13)]
    assert listed == 6
    days = {d.day: d for d in (await db_session.scalars(select(ThirteenFIndexDay))).all()}
    # the 17th's missing index may only be late (asked again); the 13th's is a holiday
    assert sorted(days) == [date(2026, 8, 13), date(2026, 8, 14)]
    assert (days[date(2026, 8, 14)].listed, days[date(2026, 8, 14)].note) == (6, None)
    assert days[date(2026, 8, 13)].listed == 0 and "404" in days[date(2026, 8, 13)].note
    filings = (await db_session.scalars(select(ThirteenFFiling))).all()
    assert len(filings) == 6 and all(f.read_at is None for f in filings)

    asked.clear()
    await read_index(db_session, fetch, today=today, limit=3, now=NOW)

    assert asked[:2] == [index_url(date(2026, 8, 17)), index_url(date(2026, 8, 12))]


async def test_sec_answering_slowly_ends_the_run_and_nothing_is_taken_for_a_holiday(db_session):
    async def slow(url: str) -> bytes:
        raise FetchUnavailable(f"{url} answered 503")

    assert await read_index(db_session, slow, today=date(2026, 8, 18), now=NOW) == 0
    assert (await db_session.scalars(select(ThirteenFIndexDay))).all() == []


def listed(db_session, *filings, form="13F-HR", filed=date(2026, 8, 14)):
    for cik, accession, _ in filings:
        db_session.add(
            ThirteenFFiling(accession=accession, cik=cik, company="x", form=form, filed=filed)
        )


async def test_the_cover_pages_are_read_latest_filed_first_and_kept(db_session):
    listed(db_session, THIRD_POINT)
    listed(db_session, ARINI_ADDED, form="13F-HR/A")
    listed(db_session, ARINI, filed=date(2026, 8, 12))
    await db_session.flush()
    asked: list[str] = []

    read = await read_summaries(
        db_session,
        sec(covers(THIRD_POINT, ARINI, ARINI_ADDED), asked),
        limit=2,
        concurrency=1,
        rate=0,
        now=NOW,
    )

    assert read == 2
    assert [u.split("/")[-2] for u in asked] == ["000104027326000003", "000117266126003819"]
    third = await db_session.get(ThirteenFFiling, THIRD_POINT[1])
    assert (third.period, third.manager, third.entries, int(third.value_usd), third.read_at) == (
        Q2,
        "Third Point LLC",
        43,
        4_679_571_988,
        NOW,
    )
    assert (await db_session.get(ThirteenFFiling, ARINI[1])).read_at is None  # the next run's


async def test_a_filing_that_cannot_be_read_is_tried_three_times(db_session):
    listed(db_session, THIRD_POINT)
    await db_session.flush()
    broken = sec({f"{folder(*THIRD_POINT[:2])}/primary_doc.xml": b"<oops"})

    for _ in range(4):
        await read_summaries(db_session, broken, rate=0, now=NOW)

    filing = await db_session.get(ThirteenFFiling, THIRD_POINT[1])
    assert filing.attempts == thirteenf_index.MAX_ATTEMPTS and filing.read_at is None
    assert "could not be read" in filing.error


async def test_an_unexpected_error_is_one_filings_and_the_others_are_kept(db_session):
    listed(db_session, THIRD_POINT, ARTEMIS)
    await db_session.flush()
    pages = covers(THIRD_POINT)

    async def odd(url: str) -> bytes:
        if ARTEMIS[1].replace("-", "") in url:
            raise RuntimeError("something nobody expected")
        return pages[url]

    assert await read_summaries(db_session, odd, rate=0, now=NOW) == 1
    artemis = await db_session.get(ThirteenFFiling, ARTEMIS[1])
    assert (artemis.attempts, artemis.error) == (1, "RuntimeError: something nobody expected")
    assert (await db_session.get(ThirteenFFiling, THIRD_POINT[1])).read_at == NOW


async def test_a_deadline_day_is_listed_in_several_statements(db_session, monkeypatch):
    monkeypatch.setattr(thirteenf_index, "INSERT_ROWS", 2)
    excerpt = (INDEX / "form.20260814.excerpt.idx").read_bytes()

    await read_index(
        db_session, sec({index_url(date(2026, 8, 14)): excerpt}), today=date(2026, 8, 15), now=NOW
    )

    assert len((await db_session.scalars(select(ThirteenFFiling))).all()) == 6


async def test_no_cover_page_is_started_once_the_budget_is_spent(db_session):
    listed(db_session, THIRD_POINT, ARTEMIS, ARINI)
    await db_session.flush()
    pages = covers(THIRD_POINT, ARTEMIS, ARINI)

    async def slow(url: str) -> bytes:
        await asyncio.sleep(0.06)
        return pages[url]

    assert await read_summaries(db_session, slow, concurrency=1, rate=0, budget=0.1, now=NOW) == 2


async def test_sec_answering_slowly_stops_the_cover_pages_and_counts_no_attempt(db_session):
    listed(db_session, THIRD_POINT, ARTEMIS)
    await db_session.flush()

    async def slow(url: str) -> bytes:
        raise FetchUnavailable(f"{url} answered 429")

    started = datetime.now(UTC)
    assert await read_summaries(db_session, slow, concurrency=1, rate=2, now=NOW) == 0
    for _, accession, _ in (THIRD_POINT, ARTEMIS):
        assert (await db_session.get(ThirteenFFiling, accession)).attempts == 0
    # the second, due half a second after the first, does not wait for its turn to give up
    assert datetime.now(UTC) - started < timedelta(seconds=0.4)


async def test_the_runs_keep_to_the_rate(db_session):
    listed(db_session, THIRD_POINT, ARTEMIS, ARINI)
    await db_session.flush()
    loop_started = datetime.now(UTC)

    await read_summaries(
        db_session, sec(covers(THIRD_POINT, ARTEMIS, ARINI)), concurrency=4, rate=20, now=NOW
    )

    assert datetime.now(UTC) - loop_started >= timedelta(seconds=0.09)  # three starts, 1/20 s apart


# --- a quarter's totals --------------------------------------------------------------------------


async def test_a_quarter_restated_is_the_restatement_and_new_holdings_are_added(db_session):
    listed(db_session, THIRD_POINT)
    listed(db_session, ARTEMIS_RESTATED, ARINI_ADDED, SUNFLOWER, form="13F-HR/A")
    listed(db_session, ARTEMIS, filed=date(2026, 8, 10))
    listed(db_session, ARINI, filed=date(2026, 8, 12))
    await db_session.flush()
    everything = (THIRD_POINT, ARTEMIS, ARTEMIS_RESTATED, ARINI, ARINI_ADDED, SUNFLOWER)
    await read_summaries(db_session, sec(covers(*everything)), rate=0, now=NOW)

    ranked = await quarter_totals(db_session, Q2)

    by_cik = {t.cik: t for t in ranked}
    assert [t.cik for t in ranked] == ["1040273", "2056819", "1767435", "1818759"]
    # Arini: the original's 27 entries and US$483,556,989, and the amendment's 28 and 974,731,526
    assert (by_cik["2056819"].entries, by_cik["2056819"].value_usd) == (55, 1_458_288_515)
    assert by_cik["2056819"].accession == ARINI[1]
    assert by_cik["2056819"].filed == date(2026, 8, 14)
    # Artemis: the restatement, not the original and the restatement
    assert (by_cik["1767435"].entries, by_cik["1767435"].value_usd) == (55, 834_513_809)
    assert by_cik["1767435"].accession == ARTEMIS_RESTATED[1]
    # Sunflower: a restatement whose original came before the index was read is still a quarter
    assert by_cik["1818759"].accession == SUNFLOWER[1]


def filing(accession, *, form="13F-HR", amendment=None, filed, value, entries=1, kind=None):
    return ThirteenFFiling(
        accession=accession,
        cik="1",
        company="ACME",
        form=form,
        filed=filed,
        period=Q2,
        manager="Acme Capital",
        amendment=amendment,
        report_type=kind or "13F HOLDINGS REPORT",
        entries=entries,
        value_usd=value,
        read_at=NOW,
        attempts=0,
    )


def test_new_holdings_before_a_restatement_are_in_it_and_after_are_added():
    a = "13F-HR/A"
    (total,) = totals(
        [
            filing("1", filed=date(2026, 8, 1), value=100),
            filing("2", form=a, amendment=NEW_HOLDINGS, filed=date(2026, 8, 2), value=10),
            filing("3", form=a, amendment=RESTATEMENT, filed=date(2026, 8, 3), value=120),
            filing("4", form=a, amendment=NEW_HOLDINGS, filed=date(2026, 8, 4), value=5),
        ]
    )

    assert (total.value_usd, total.entries, total.accession) == (125, 2, "3")


def test_a_second_original_replaces_the_first_and_a_notice_or_lone_addition_is_nothing():
    a = "13F-HR/A"
    (total,) = totals(
        [
            filing("1", filed=date(2026, 8, 1), value=100),
            filing("2", filed=date(2026, 8, 2), value=90),
        ]
    )
    assert (total.value_usd, total.accession) == (90, "2")

    assert totals([filing("1", filed=date(2026, 8, 1), value=0, kind=NOTICE)]) == []
    added = filing("1", form=a, amendment=NEW_HOLDINGS, filed=date(2026, 8, 1), value=5)
    assert totals([added]) == []
    unread = filing("1", filed=date(2026, 8, 1), value=100)
    unread.read_at = None
    assert totals([unread]) == []
