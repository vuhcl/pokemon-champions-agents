"""Tests for ADR-014 live-fetch retry, cache-on-success-only, and soft misses."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from recommender import usage_live as ul
from recommender.usage_live import (
    LiveFetchError,
    fetch_json,
    fetch_live_cbd_battle,
    fetch_live_showdown_detail,
)


@pytest.fixture(autouse=True)
def _clear_live_caches():
    fetch_live_cbd_battle.cache_clear()
    fetch_live_showdown_detail.cache_clear()
    yield
    fetch_live_cbd_battle.cache_clear()
    fetch_live_showdown_detail.cache_clear()


def _urlopen_json(payload: object, *, status: int = 200):
    response = MagicMock()
    response.status = status
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_transient_failure_is_not_cached_then_succeeds():
    """Exception-path None must not stick in the cache (the real bug)."""
    calls = {"n": 0}

    def flaky_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] <= ul._LIVE_FETCH_ATTEMPTS:
            raise TimeoutError("blip")
        return _urlopen_json({"abilities": []})

    with (
        patch("recommender.usage_live.urllib.request.urlopen", side_effect=flaky_urlopen),
        patch("recommender.usage_live.time.sleep"),
    ):
        assert fetch_live_cbd_battle("Incineroar") is None
        # Exhausted retries — not cached. Next call can succeed.
        calls["n"] = ul._LIVE_FETCH_ATTEMPTS  # next urlopen succeeds immediately
        got = fetch_live_cbd_battle("Incineroar")
    assert got == {"abilities": []}


def test_legitimate_miss_is_cached_with_default_fetcher():
    calls = {"n": 0}

    def miss_urlopen(req, timeout=None):
        calls["n"] += 1
        err = ul.urllib.error.HTTPError(req.full_url, 404, "no", hdrs=None, fp=None)
        raise err

    with patch(
        "recommender.usage_live.urllib.request.urlopen", side_effect=miss_urlopen
    ):
        assert fetch_live_cbd_battle("MissingNo") is None
        assert fetch_live_cbd_battle("MissingNo") is None
    assert calls["n"] == 1


def test_fetch_json_retries_timeout_then_succeeds():
    calls = {"n": 0}

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("slow")
        return _urlopen_json({"ok": True})

    with (
        patch("recommender.usage_live.urllib.request.urlopen", side_effect=flaky),
        patch("recommender.usage_live.time.sleep") as sleep,
    ):
        assert fetch_json("http://example.test/x") == {"ok": True}
    assert calls["n"] == 3
    assert sleep.call_count == 2
    assert sleep.call_args_list[0].args[0] == 0.2
    assert sleep.call_args_list[1].args[0] == 0.4


def test_fetch_json_exhausted_timeouts_raise():
    with (
        patch(
            "recommender.usage_live.urllib.request.urlopen",
            side_effect=TimeoutError("gone"),
        ),
        patch("recommender.usage_live.time.sleep"),
    ):
        with pytest.raises(LiveFetchError):
            fetch_json("http://example.test/x")


def test_showdown_transport_miss_not_cached():
    calls = {"n": 0}

    def boom(req, timeout=None):
        calls["n"] += 1
        raise TimeoutError("blip")

    with (
        patch("recommender.usage_live.urllib.request.urlopen", side_effect=boom),
        patch("recommender.usage_live.time.sleep"),
    ):
        assert fetch_live_showdown_detail("Incineroar") is None
        n_after_first = calls["n"]
        assert fetch_live_showdown_detail("Incineroar") is None
    # Second call retried from scratch (not a memoized None).
    assert calls["n"] == 2 * n_after_first


def test_custom_fetcher_skips_cache():
    calls = []

    def fetch(url):
        calls.append(url)
        return None

    assert fetch_live_cbd_battle("X", fetch) is None
    assert fetch_live_cbd_battle("X", fetch) is None
    assert len(calls) == 2
