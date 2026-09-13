"""Season news Duration parse (no live network)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.ci.champions_news import (
    parse_season_news_html,
    scan_for_current_season,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_season_m6_fixture():
    html = (FIXTURES / "champions_news_season_m6.html").read_text(encoding="utf-8")
    page = parse_season_news_html(
        html,
        url="https://news.pokemon-home.com/en/page/822.html",
        page_id=822,
    )
    assert page.season_number == 6
    assert page.start_utc == datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc)
    assert page.end_utc == datetime(2026, 10, 7, 1, 59, tzinfo=timezone.utc)


def test_scan_for_current_season_uses_window():
    html = (FIXTURES / "champions_news_season_m6.html").read_text(encoding="utf-8")

    def fetch(url: str) -> str:
        if url.endswith("/822.html"):
            return html
        raise FileNotFoundError(url)

    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    page = scan_for_current_season(
        start_page_id=822, window=0, now=now, fetch=fetch
    )
    assert page.season_number == 6
    assert page.page_id == 822
