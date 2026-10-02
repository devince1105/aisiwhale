"""Two sources that answer in JSON rather than a feed (D-169): the Taiwan Stock Exchange's
material announcements (重大訊息) and the GDELT DOC API. Both are read into ``FeedEntry`` like
any feed, so the poller treats them as it treats RSS.

**TWSE** (``openapi.twse.com.tw``, dataset ``t187ap04_L``): the listed companies' announcements
of the latest trading day, about 80 a day, with Chinese keys and dates in the Republic of China
calendar (``1151002`` is 2026-10-02; ``發言時間`` is HHMMSS without its leading zeros). An
announcement has no page of its own that a GET can read (MOPS answers only to a form post), so
its item keeps the whole text as its summary and gets a URL of its own on the dataset — the
official place it was published — that ``fetch_url`` recognises and answers from the item.

**GDELT** (``api.gdeltproject.org``): a search over news sites worldwide, free, without a key,
and at most one request every five seconds; anything faster is answered with a plain-text
request to slow down — and it says so to an address for minutes on end, even one that waited
longer (seen 2026-10-03), and from Render with a 429 instead. Either answer is ``GdeltBusy``:
the poll is recorded as not done, but it does not count towards pausing the source, as an
outage of the site would.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from autora.domains.newsroom.feeds import FeedEntry, FeedError

TWSE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_GAP_SECONDS = 10.0
"""GDELT asks for one request every five seconds; twice that, as from a cloud host's shared
address the second of two requests 5.5 seconds apart was refused (2026-10-03)."""

_TAIPEI = timezone(timedelta(hours=8))
_LINE_BREAK = re.compile(r"\s*[\r\n]+\s*")
_LOOSE_PUNCTUATION = re.compile(r"\s+([.,:;!?])")


class GdeltBusy(FeedError):
    """GDELT asked for fewer requests: try again at the next poll."""


def _roc_moment(day: str, time: str = "") -> datetime | None:
    """``1151002`` and ``5311`` → 2026-10-02 00:53:11 Taipei time (in UTC)."""
    day = day.strip()
    if not day.isdigit() or len(day) < 6:
        return None
    clock = time.strip().zfill(6) if time.strip().isdigit() else "000000"
    try:
        moment = datetime(
            int(day[:-4]) + 1911,
            int(day[-4:-2]),
            int(day[-2:]),
            int(clock[:2]),
            int(clock[2:4]),
            int(clock[4:6]),
            tzinfo=_TAIPEI,
        )
    except ValueError:
        return None
    return moment.astimezone(UTC)


def _roc_date(day: str) -> str:
    moment = _roc_moment(day)
    return moment.astimezone(_TAIPEI).strftime("%Y-%m-%d") if moment else day.strip()


def _load(body: bytes, who: str) -> Any:
    try:
        return json.loads(body)
    except ValueError:
        start = body[:200].decode("utf-8", "replace").strip()
        raise FeedError(f"{who} did not answer JSON: {start!r}") from None


def parse_twse_announcements(
    body: bytes, *, codes: Iterable[str] = (), keywords: Iterable[str] = ()
) -> list[FeedEntry]:
    """The announcements, only those of ``codes`` and those whose subject has one of
    ``keywords`` when either is given (a company in ``codes`` is kept whatever its subject)."""
    rows = _load(body, "TWSE")
    if not isinstance(rows, list):
        raise FeedError("TWSE answered something other than a list of announcements")
    wanted = {c.strip() for c in codes if c.strip()}
    words = [k.strip() for k in keywords if k.strip()]
    entries: list[FeedEntry] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        # the dataset's own keys carry stray spaces ("主旨 ")
        row = {str(k).strip(): str(v or "").strip() for k, v in raw.items()}
        code, name = row.get("公司代號", ""), row.get("公司名稱", "")
        # some subjects run over several lines, broken where a Chinese sentence has no space
        subject = " ".join(_LINE_BREAK.sub("", row.get("主旨", "")).split())
        if not code or not subject:
            continue
        if (wanted or words) and code not in wanted and not any(w in subject for w in words):
            continue
        said_on, said_at = row.get("發言日期", ""), row.get("發言時間", "")
        moment = _roc_moment(said_on, said_at)
        stamp = moment.strftime("%Y%m%dT%H%M%SZ") if moment else said_on
        digest = hashlib.sha256(f"{subject}\n{row.get('說明', '')}".encode()).hexdigest()[:10]
        url = f"{TWSE_URL}?{urlencode({'co_id': code, 'at': stamp, 'id': digest})}"
        text = "\n".join(
            line
            for line in (
                f"{name}（{code}）重大訊息：{subject}",
                f"發言時間：{moment.astimezone(_TAIPEI):%Y-%m-%d %H:%M}（台北）" if moment else "",
                f"符合條款：{row['符合條款']}" if row.get("符合條款") else "",
                f"事實發生日：{_roc_date(row['事實發生日'])}" if row.get("事實發生日") else "",
                "說明：",
                row.get("說明", ""),
                "資料來源：臺灣證券交易所 公開資訊觀測站 上市公司每日重大訊息",
            )
            if line
        )
        entries.append(
            FeedEntry(
                external_id=f"twse:{code}:{stamp}:{digest}",
                url=url,
                title=f"{name}（{code}）{subject}",
                summary=text,
                published_at=moment,
            )
        )
    return entries


def gdelt_url(config: dict[str, Any]) -> str:
    return f"{GDELT_URL}?" + urlencode(
        {
            "query": config["query"],
            "mode": "artlist",
            "format": "json",
            "maxrecords": int(config.get("maxrecords", 25)),
            "timespan": str(config.get("timespan", "1d")),
            "sort": "datedesc",
        }
    )


def parse_gdelt(body: bytes) -> list[FeedEntry]:
    if not body.strip():
        return []  # GDELT answers nothing at all when nothing matched
    if body.lstrip().startswith(b"Please limit requests"):
        raise GdeltBusy("GDELT asked for fewer requests")
    answer = _load(body, "GDELT")
    articles = answer.get("articles", []) if isinstance(answer, dict) else None
    if not isinstance(articles, list):
        raise FeedError("GDELT answered without a list of articles")
    entries: list[FeedEntry] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        url = str(article.get("url") or "")
        # GDELT's titles come with stray spaces: "Prize Is Where the Rest Is Going . "
        title = _LOOSE_PUNCTUATION.sub(r"\1", " ".join(str(article.get("title") or "").split()))
        if not url.startswith(("http://", "https://")) or not title:
            continue
        try:
            seen = datetime.strptime(str(article.get("seendate", "")), "%Y%m%dT%H%M%SZ")
        except ValueError:
            published = None
        else:
            published = seen.replace(tzinfo=UTC)
        domain = str(article.get("domain") or "").strip()
        entries.append(
            FeedEntry(
                external_id=url,
                url=url,
                title=title,
                summary=domain or None,
                published_at=published,
            )
        )
    return entries
