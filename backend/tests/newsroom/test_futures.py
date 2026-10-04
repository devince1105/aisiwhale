"""D-180: 台指期 (TXF1)'s daily history, from the futures exchange's download, for its chart."""

from datetime import date

from sqlalchemy import delete, select

from autora.domains.newsroom.figures import Figures, FredHistory
from autora.domains.newsroom.forex import TiingoFx
from autora.domains.newsroom.futures import TXF1, parse_taifex_csv, refresh_txf1
from autora.domains.newsroom.models import PriceBar
from autora.domains.newsroom.price_history import HISTORY_MONTHS

HEADER = (
    "交易日期,契約,到期月份(週別),開盤價,最高價,最低價,收盤價,漲跌價,漲跌%,成交量,結算價,"
    "未沖銷契約數,最後最佳買價,最後最佳賣價,歷史最高價,歷史最低價,是否因訊息面暫停交易,交易時段,"
    "價差對單式委託成交量\n"
)


def line(day, month, session, o, h, l, c, volume="100", contract="TX"):  # noqa: E741
    return f"{day},{contract},{month},{o},{h},{l},{c},0,0%,{volume},-,-,-,-,-,-,,{session},,\n"


SEPTEMBER = HEADER + "".join(
    [
        line("2026/09/15", "202609  ", "一般", "46000", "47220", "45987", "47209", "57627"),
        line("2026/09/15", "202609  ", "盤後", "1", "1", "1", "1"),  # the night session
        line("2026/09/15", "202610  ", "一般", "46188", "47364", "46188", "47364", "328"),
        line("2026/09/15", "202609W3", "一般", "9", "9", "9", "9"),  # a weekly contract
        line("2026/09/15", "202609  ", "一般", "2", "2", "2", "2", contract="MTX"),  # 小台
        # the 16th is September's expiry: from the 17th the near month is October's
        line("2026/09/17", "202610  ", "一般", "48000", "48500", "47900", "48330", "42731"),
        line("2026/09/17", "202611  ", "一般", "48100", "48600", "48000", "48400"),
        line("2026/09/18", "202610  ", "一般", "-", "-", "-", "-"),  # no trade: no bar
    ]
)


def test_each_day_is_the_near_month_in_the_day_session():
    bars = parse_taifex_csv(SEPTEMBER)
    assert [(b.day.isoformat(), str(b.close), b.volume) for b in bars] == [
        ("2026-09-15", "47209", 57627),
        ("2026-09-17", "48330", 42731),
    ]
    assert parse_taifex_csv(HEADER) == []


async def test_filled_once_then_only_the_new_months_and_charted(db_session):
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == TXF1))
    asked: list[tuple[date, date]] = []

    async def download(first: date, last: date) -> str:
        """Every month has its days, as the exchange's five years do; September's are known."""
        asked.append((first, last))
        if first == date(2026, 9, 1):
            return SEPTEMBER
        day = f"{first:%Y/%m}/02"
        return HEADER + line(day, f"{first:%Y%m}", "一般", "47000", "47500", "46800", "47300")

    today = date(2026, 10, 4)
    written = await refresh_txf1(db_session, download, today=today, pause=0)
    assert written == 2 + HISTORY_MONTHS - 1
    assert len(asked) == HISTORY_MONTHS  # five years, a month a request
    assert asked[0] == (date(2025, 11, 1), date(2025, 11, 30))
    assert (date(2026, 10, 1), date(2026, 10, 4)) in asked  # never past today
    stored = (await db_session.scalars(select(PriceBar).where(PriceBar.symbol == TXF1))).all()
    assert {b.market for b in stored} == {"tw"} and {b.source for b in stored} == {"TAIFEX"}

    asked.clear()
    await refresh_txf1(db_session, download, today=today, pause=0)
    assert asked == [(date(2026, 10, 1), date(2026, 10, 4))]  # from the last stored day's month

    figure = await Figures(TiingoFx(None), FredHistory(None)).figure("txf1", db_session)
    assert figure is not None and figure.source == "TAIFEX" and not figure.close_only
    assert [b.c for b in figure.bars][-3:] == [47209, 48330, 47300]  # October's 2nd, in the fake
    assert len(figure.bars) == HISTORY_MONTHS + 1 and figure.as_of == date(2026, 10, 2)
