"""Parse champions-news.pokemon-home.com Regulation Set Duration pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UA = "pokemon-champions-agents/0.1 (legality-extract-gate)"
NEWS_HOST = "https://champions-news.pokemon-home.com"
PAGE_TMPL = NEWS_HOST + "/en/page/{id}.html"

_DURATION_START = re.compile(
    r"([A-Za-z]+day),\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4}),\s+at\s+(\d{1,2}):(\d{2})\s+UTC"
    r".*?to\s+([A-Za-z]+day),\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4}),\s+at\s+(\d{1,2}):(\d{2})\s+UTC",
    re.I | re.S,
)
_TITLE_SET = re.compile(r"Regulation Set M-([A-Z])\b", re.I)
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass(frozen=True)
class RegulationNewsPage:
    letter: str
    url: str
    page_id: int | None
    start_utc: datetime
    end_utc: datetime
    title: str


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "title":
            self._in_title = True
        if t in {"script", "style"}:
            self._in_script = True
        if t in {"br", "p", "div", "h1", "h2", "h3", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "title":
            self._in_title = False
        if t in {"script", "style"}:
            self._in_script = False
        if t in {"p", "div", "h1", "h2", "h3", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_script:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.parts.append(data)


def _parse_dt(month: str, day: str, year: str, hour: str, minute: str) -> datetime:
    mi = _MONTHS.get(month.lower())
    if mi is None:
        raise ValueError(f"unknown month {month!r}")
    return datetime(
        int(year), mi, int(day), int(hour), int(minute), tzinfo=timezone.utc
    )


def fetch_html(url: str, *, timeout: float = 30.0) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_regulation_news_html(
    html: str, *, url: str = "", page_id: int | None = None
) -> RegulationNewsPage:
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join("".join(parser.parts).split())
    title = " ".join("".join(parser.title_parts).split()) or text[:120]
    tm = _TITLE_SET.search(title) or _TITLE_SET.search(text)
    if not tm:
        raise ValueError(f"no Regulation Set M-* title in {url or 'html'}")
    letter = tm.group(1).upper()
    dm = _DURATION_START.search(text)
    if not dm:
        raise ValueError(f"no Duration UTC window in {url or 'html'}")
    start = _parse_dt(dm.group(2), dm.group(3), dm.group(4), dm.group(5), dm.group(6))
    end = _parse_dt(dm.group(8), dm.group(9), dm.group(10), dm.group(11), dm.group(12))
    return RegulationNewsPage(
        letter=letter,
        url=url,
        page_id=page_id,
        start_utc=start,
        end_utc=end,
        title=title,
    )


def page_url(page_id: int) -> str:
    return PAGE_TMPL.format(id=page_id)


def scan_for_letter(
    letter: str,
    *,
    start_page_id: int,
    window: int = 80,
    fetch=fetch_html,
) -> RegulationNewsPage:
    """Scan page ids [start, start+window] for Regulation Set M-{letter}."""
    want = letter.upper()
    last_err: Exception | None = None
    for page_id in range(start_page_id, start_page_id + window + 1):
        url = page_url(page_id)
        try:
            html = fetch(url)
        except HTTPError as e:
            if e.code == 404:
                continue
            last_err = e
            continue
        except (URLError, TimeoutError, OSError) as e:
            last_err = e
            continue
        try:
            page = parse_regulation_news_html(html, url=url, page_id=page_id)
        except ValueError as e:
            last_err = e
            continue
        if page.letter == want:
            return page
    msg = f"no champions-news page for Regulation Set M-{want} in ids {start_page_id}..{start_page_id + window}"
    if last_err:
        raise LookupError(f"{msg} (last error: {last_err})") from last_err
    raise LookupError(msg)
