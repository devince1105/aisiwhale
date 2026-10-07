"""HD-10: a 13F's information table read as it downloads — whole, or its first rows to tell
dollars from thousands — and found in its filing's folder."""

import json

import pytest

from autora.domains.newsroom import thirteenf
from autora.domains.newsroom.thirteenf_tables import (
    read_table,
    scale_of,
    scaled,
    sec_chunks,
    table_url,
    total_scale,
)
from autora.infra.http import FetchRefused

NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def row(name, cusip, value, shares, *, kind="SH", put_call="", title="COM"):
    option = f"<putCall>{put_call}</putCall>" if put_call else ""
    return (
        f"<infoTable><nameOfIssuer>{name}</nameOfIssuer><titleOfClass>{title}</titleOfClass>"
        f"<cusip>{cusip}</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}"
        f"</sshPrnamt><sshPrnamtType>{kind}</sshPrnamtType></shrsOrPrnAmt>{option}"
        "<investmentDiscretion>SOLE</investmentDiscretion><votingAuthority><Sole>1</Sole>"
        "<Shared>0</Shared><None>0</None></votingAuthority></infoTable>"
    )


def table(*rows: str) -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><informationTable xmlns="{NS}">'
        + "".join(rows)
        + "</informationTable>"
    ).encode()


def chunked(pages: dict[str, bytes], *, size: int = 7, closed: list[str] | None = None):
    """SEC's tables, a few bytes at a time (rows cut anywhere); ``closed`` hears of each
    download that ended, read to its end or not."""

    async def chunks(url: str):
        if url not in pages:
            raise FetchRefused(f"{url} answered 404")
        body = pages[url]
        try:
            for start in range(0, len(body), size):
                yield body[start : start + size]
        finally:
            if closed is not None:
                closed.append(url)

    return chunks


URL = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/infotable.xml"


async def test_a_table_is_read_a_few_bytes_at_a_time_into_its_positions():
    body = table(
        row("APPLE INC", "037833100", 2_300_000, 10_000),
        row("APPLE INC", "037833100", 460_000, 2_000),  # another manager's: added
        row("APPLE INC", "037833100", 50_000, 1_000, put_call="Put"),
        row("ACME 4% NOTES", "000000AA1", 99_000, 100_000, kind="PRN"),
    )

    t = await read_table(chunked({URL: body}), URL)

    assert (t.rows, t.complete) == (4, True)
    apple = t.holdings.positions[("037833100", "", "SH")]
    assert (apple.amount, apple.value, apple.name) == (12_000, 2_760_000, "APPLE INC")
    assert t.holdings.positions[("037833100", "PUT", "SH")].value == 50_000
    assert t.holdings.positions[("000000AA1", "", "PRN")].amount == 100_000


async def test_the_first_rows_only_and_the_download_is_closed():
    body = table(*(row(f"CO {n}", f"{n:09d}", 100 * n, 10) for n in range(1, 50)))
    closed: list[str] = []

    t = await read_table(chunked({URL: body}, closed=closed), URL, rows=5)

    assert (t.rows, t.complete, len(t.holdings.positions)) == (5, False, 5)
    assert closed == [URL]  # not read on to the end


async def test_a_dtd_is_refused_even_cut_between_chunks():
    body = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><informationTable/>'

    with pytest.raises(thirteenf.FilingError, match="DTD"):
        await read_table(chunked({URL: body}, size=5), URL)


async def test_what_is_not_an_information_table_is_refused():
    with pytest.raises(thirteenf.FilingError, match="not an information table"):
        await read_table(chunked({URL: b"<edgarSubmission><x/></edgarSubmission>"}), URL)
    with pytest.raises(thirteenf.FilingError, match="could not be read"):
        await read_table(chunked({URL: table(row("A", "1", 1, 1))[:-9]}), URL)
    with pytest.raises(FetchRefused):
        await read_table(chunked({}), URL)


async def test_thousands_are_told_by_the_price_per_share():
    dollars = table(*(row(f"CO {n}", f"{n:09d}", 150 * 1000, 1000) for n in range(1, 9)))
    thousands = table(*(row(f"CO {n}", f"{n:09d}", 150, 1000) for n in range(1, 9)))

    assert scale_of(await read_table(chunked({URL: dollars}), URL)) == 1
    t = await read_table(chunked({URL: thousands}), URL, rows=5)
    assert scale_of(t) == 1000
    holdings = scaled(t, 1000)
    assert holdings.in_thousands and holdings.total_value == 5 * 150_000


async def test_a_cover_page_total_is_in_thousands_only_when_the_table_says_a_thousand_times_more():
    # T. Rowe Price, 2026Q2: 4,722 rows in thousands, and a total of 999,124,702 — thousands too
    trowe = table(*(row(f"CO {n}", f"{n:09d}", 211_589, 1_500_000) for n in range(1, 300)))
    first = await read_table(chunked({URL: trowe}), URL, rows=200)
    assert scale_of(first) == 1000
    assert total_scale(first, 1000, entries=4722, total=999_124_702) == 1000
    # Coston, McIsaac & Partners: rows in thousands (GSK: 1,381 shares worth "72"), its total
    # in dollars — the table's US$13.5 million is its total's 13,500,000, not a thousand times it
    coston = table(*(row(f"CO {n}", f"{n:09d}", 450, 10_000) for n in range(1, 31)))
    whole = await read_table(chunked({URL: coston}), URL, rows=200)
    assert (whole.complete, scale_of(whole)) == (True, 1000)
    assert total_scale(whole, 1000, entries=30, total=13_500_000) == 1
    # rows in dollars: so is the total
    assert total_scale(whole, 1, entries=30, total=13_500) == 1


async def test_the_table_is_the_folder_s_largest_xml_but_the_cover_page():
    folder = "https://www.sec.gov/Archives/edgar/data/2012383/000201238326003238"
    listing = {
        "directory": {
            "item": [
                {"name": "0002012383-26-003238.txt", "size": "40000000"},
                {"name": "primary_doc.xml", "size": "13828"},
                {"name": "notes.xml", "size": "2000"},
                {"name": "form13fInfoTable.xml", "size": "23016794"},
            ]
        }
    }

    async def fetch(url: str) -> bytes:
        assert url == f"{folder}/index.json"
        return json.dumps(listing).encode()

    assert await table_url(fetch, "2012383", "0002012383-26-003238") == (
        f"{folder}/form13fInfoTable.xml"
    )

    async def bare(url: str) -> bytes:
        return json.dumps({"directory": {"item": [{"name": "primary_doc.xml"}]}}).encode()

    with pytest.raises(thirteenf.FilingError, match="no information table"):
        await table_url(bare, "1", "0000000001-26-000001")


async def test_only_sec_is_read():
    chunks = sec_chunks("Autora Newsroom test@example.com")

    with pytest.raises(FetchRefused, match="only www.sec.gov"):
        async for _ in chunks("https://example.com/infotable.xml"):
            pass
