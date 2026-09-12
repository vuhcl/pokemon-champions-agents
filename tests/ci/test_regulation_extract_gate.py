"""Unit tests for regulation extract gate (no live network)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.ci.champions_news import parse_regulation_news_html
from scripts.ci.regulation_extract_gate import champions_format_names, run_gate
from scripts.ci.regulation_letters import (
    archive_mod_for_letter,
    letter_from_format_name,
    letters_adjacent,
    prior_mod_id,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_letter_helpers():
    assert letter_from_format_name("[Gen 9 Champions] VGC 2026 Reg M-C") == "C"
    assert prior_mod_id("C") == "championsregmb"
    assert archive_mod_for_letter("C") == "championsregmc"
    assert letters_adjacent("C", "D")
    assert not letters_adjacent("C", "E")
    assert not letters_adjacent("C", "C")


def test_parse_duration_mc_fixture():
    html = (FIXTURES / "champions_news_reg_mc.html").read_text(encoding="utf-8")
    page = parse_regulation_news_html(
        html, url="https://champions-news.pokemon-home.com/en/page/816.html", page_id=816
    )
    assert page.letter == "C"
    assert page.start_utc == datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc)
    assert page.end_utc == datetime(2026, 12, 2, 1, 59, tzinfo=timezone.utc)


def test_parse_duration_mb_extended_fixture():
    html = (FIXTURES / "champions_news_reg_mb.html").read_text(encoding="utf-8")
    page = parse_regulation_news_html(html, url="https://example/776", page_id=776)
    assert page.letter == "B"
    assert page.start_utc == datetime(2026, 6, 17, 2, 0, tzinfo=timezone.utc)
    assert page.end_utc == datetime(2026, 9, 9, 1, 59, tzinfo=timezone.utc)


def test_champions_format_names():
    src = """
    {
      name: "[Gen 9 Champions] VGC 2026 Reg M-C",
      mod: 'champions',
    },
    {
      name: "[Gen 9 Champions] BSS Reg M-C",
      mod: 'champions',
    },
    """
    vgc, bss = champions_format_names(src)
    assert "VGC" in vgc and "M-C" in vgc
    assert "BSS" in bss and "M-C" in bss


def _formats(letter: str) -> str:
    return f"""
    {{
      name: "[Gen 9 Champions] VGC 2026 Reg M-{letter}",
      mod: 'champions',
    }},
    {{
      name: "[Gen 9 Champions] BSS Reg M-{letter}",
      mod: 'champions',
    }},
    """


def test_gate_noop_same_letter():
    result = run_gate(
        formats_ts_text=_formats("C"),
        snapshot_vgc="[Gen 9 Champions] VGC 2026 Reg M-C",
        require_prior_mod_dir=False,
        showdown_commit="abc",
    )
    assert result["decision"] == "noop"
    assert result["reason"] == "showdown_letter_matches_snapshot"


def test_gate_fail_non_adjacent():
    result = run_gate(
        formats_ts_text=_formats("E"),
        snapshot_vgc="[Gen 9 Champions] VGC 2026 Reg M-C",
        require_prior_mod_dir=False,
        showdown_commit="abc",
    )
    assert result["decision"] == "fail"
    assert result["reason"] == "non_adjacent_letter"


def test_gate_noop_start_in_future():
    html = (FIXTURES / "champions_news_reg_md_future.html").read_text(encoding="utf-8")

    def fetch(_url: str) -> str:
        return html

    result = run_gate(
        formats_ts_text=_formats("D"),
        snapshot_vgc="[Gen 9 Champions] VGC 2026 Reg M-C",
        news_url="https://champions-news.pokemon-home.com/en/page/900.html",
        fetch_html_fn=fetch,
        require_prior_mod_dir=False,
        showdown_commit="abc",
        now=datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc),
    )
    assert result["decision"] == "noop"
    assert result["reason"] == "official_start_in_future"


def test_gate_extract_when_start_passed():
    html = (FIXTURES / "champions_news_reg_md.html").read_text(encoding="utf-8")

    def fetch(_url: str) -> str:
        return html

    result = run_gate(
        formats_ts_text=_formats("D"),
        snapshot_vgc="[Gen 9 Champions] VGC 2026 Reg M-C",
        news_url="https://champions-news.pokemon-home.com/en/page/900.html",
        fetch_html_fn=fetch,
        require_prior_mod_dir=False,
        showdown_commit="abc",
        now=datetime(2026, 12, 3, 12, 0, tzinfo=timezone.utc),
    )
    assert result["decision"] == "extract"
    assert result["prior_mod"] == "championsregmc"
    assert result["official_start_utc"].startswith("2026-12-02")


def test_gate_fail_news_letter_mismatch():
    html = (FIXTURES / "champions_news_reg_mc.html").read_text(encoding="utf-8")

    def fetch(_url: str) -> str:
        return html

    result = run_gate(
        formats_ts_text=_formats("D"),
        snapshot_vgc="[Gen 9 Champions] VGC 2026 Reg M-C",
        news_url="https://example/816",
        fetch_html_fn=fetch,
        require_prior_mod_dir=False,
        showdown_commit="abc",
        now=datetime(2026, 12, 3, tzinfo=timezone.utc),
    )
    assert result["decision"] == "fail"
    assert result["reason"] == "news_url_letter_mismatch"
