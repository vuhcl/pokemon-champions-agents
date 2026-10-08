"""Hostile redaction: CandidateDiscoveryError must not surface calc URL/host/body."""

from __future__ import annotations

import urllib.error
from dataclasses import asdict
from unittest.mock import patch

from recommender.calc_client import CalcClientError
from recommender.discovery_error import (
    CALC_INCOMPLETE_MSG,
    CALC_UNAVAILABLE_MSG,
    DISCOVERY_CALC_MESSAGE_ALLOWLIST,
    discovery_error_from_exc,
)
from recommender.matchup import MatchupEvidenceError
from recommender.present_text import format_turn
from recommender.state import CandidateDiscoveryError
from recommender.threat_counters import query_threat_counters

HOST = "calc-leak.example:8443"
URL = "https://calc-leak.example:8443/v1/batch"
PATH = "/v1/batch"
_LEAK_MARKERS = (HOST, URL, PATH)


def _assert_no_leak(text: str) -> None:
    for marker in _LEAK_MARKERS:
        assert marker not in text, f"leaked {marker!r} in {text!r}"


def _tc(species: str, *, usage_rank: int | None = None):
    from recommender.state import ThreatCandidate

    return ThreatCandidate(
        ladder_species=species,
        usage_rank=usage_rank,
        form=species,
        showdown_usage_pct=None,
        showdown_formes=(),
        spec={"species": species, "moves": ["Earthquake"], "ability": "Dummy"},
        build_source="ingame",
        threat_kinds=frozenset({"wall"}),
        ko_threshold_score=0.0,
    )


def test_e2e_urlerror_redacted_through_threat_counters():
    threats = [_tc("T1", usage_rank=1)]
    log_calls: list[tuple] = []

    def fake_qc(pokemon, n=20, **kwargs):
        sp = pokemon.get("species") or ""
        if sp == "Anchor":
            return list(threats)
        return [_tc("CandA", usage_rank=10)]

    def fake_urlopen(*_a, **_k):
        raise urllib.error.URLError(
            f"Failed to connect to {HOST} at {URL}"
        )

    def capture_log(tool, args, **kwargs):
        log_calls.append((tool, args, kwargs))

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters._most_common_verify_spec",
            side_effect=lambda sp, regulation="champions": {
                "species": sp,
                "moves": ["Earthquake"],
                "item": "Leftovers",
            },
        ),
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
        patch("recommender.calc_client.log_tool_call", side_effect=capture_log),
        patch("recommender.discovery_error.log_tool_call", side_effect=capture_log),
    ):
        result = query_threat_counters(
            {"species": "Anchor"},
            n=10,
            verify_threats_n=5,
            regulation="champions",
        )

    assert result.status == "degraded"
    assert result.error is not None
    assert result.error.kind == "calc_unavailable"
    assert result.error.message == CALC_UNAVAILABLE_MSG
    _assert_no_leak(result.error.message)
    _assert_no_leak(str(asdict(result.error)))
    rendered = format_turn(
        {
            "candidate_discovery_error": result.error,
            "pending_presentation": None,
            "team_draft": [],
        }
    )
    _assert_no_leak(rendered)
    assert CALC_UNAVAILABLE_MSG in rendered
    assert log_calls, "expected discovery/calc log_tool_call"
    for tool, args, kwargs in log_calls:
        _assert_no_leak(str(args))
        _assert_no_leak(str(kwargs.get("error") or ""))
        _assert_no_leak(tool)


def test_hostile_calc_client_error_factory_message():
    exc = CalcClientError(
        503,
        {"error": f"upstream {HOST} refused {URL} path {PATH}"},
    )
    with patch("recommender.discovery_error.log_tool_call") as logged:
        err = discovery_error_from_exc(exc, stage="coverage")
    assert err.message == CALC_UNAVAILABLE_MSG
    assert err.message in DISCOVERY_CALC_MESSAGE_ALLOWLIST
    _assert_no_leak(err.message)
    _assert_no_leak(str(asdict(err)))
    logged.assert_called_once()
    call_kwargs = logged.call_args
    _assert_no_leak(str(call_kwargs))


def test_hostile_matchup_evidence_error_factory_message():
    exc = MatchupEvidenceError(f"calc batch row failed: {URL} on {HOST}")
    with patch("recommender.discovery_error.log_tool_call"):
        err = discovery_error_from_exc(exc, stage="candidate_verification")
    assert err.kind == "calc_incomplete"
    assert err.message == CALC_INCOMPLETE_MSG
    _assert_no_leak(err.message)


def test_format_turn_shows_fixed_message_not_exc_body():
    with patch("recommender.discovery_error.log_tool_call"):
        err = discovery_error_from_exc(
            CalcClientError(500, {"error": URL}),
            stage="spof",
        )
    text = format_turn(
        {
            "candidate_discovery_error": err,
            "pending_presentation": None,
            "team_draft": [],
        }
    )
    assert CALC_UNAVAILABLE_MSG in text
    assert "calc_unavailable" in text
    assert "spof" in text
    assert "retryable=True" in text
    _assert_no_leak(text)


def test_legacy_leaky_message_redacted_by_format_turn():
    err = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="coverage",
        message=f"calc request failed (0): {{'error': 'Failed to connect to {URL}'}}",
        retryable=True,
        exception_type="CalcClientError",
        status_code=0,
    )
    text = format_turn(
        {
            "candidate_discovery_error": err,
            "pending_presentation": None,
            "team_draft": [],
        }
    )
    assert CALC_UNAVAILABLE_MSG in text
    _assert_no_leak(text)


def test_factory_fail_closed_all_calc_kind_stage_combos():
    stages = ("candidate_verification", "coverage", "spof")
    with patch("recommender.discovery_error.log_tool_call"):
        for stage in stages:
            unavailable = discovery_error_from_exc(
                CalcClientError(503, {"error": "x"}), stage=stage
            )
            incomplete = discovery_error_from_exc(
                MatchupEvidenceError("x"), stage=stage
            )
            assert unavailable.message
            assert incomplete.message
            assert unavailable.message in DISCOVERY_CALC_MESSAGE_ALLOWLIST
            assert incomplete.message in DISCOVERY_CALC_MESSAGE_ALLOWLIST
            assert unavailable.stage == stage
            assert incomplete.stage == stage


def test_factory_log_tool_call_has_no_body():
    exc = CalcClientError(503, {"error": f"body with {URL}"})
    with patch("recommender.discovery_error.log_tool_call") as logged:
        discovery_error_from_exc(exc, stage="coverage")
    args = logged.call_args.args[1] if logged.call_args.args else logged.call_args[0][1]
    error = logged.call_args.kwargs.get("error")
    _assert_no_leak(str(args))
    _assert_no_leak(str(error or ""))
    assert logged.call_args.kwargs["ok"] is False
    assert error == "calc_unavailable:CalcClientError"
