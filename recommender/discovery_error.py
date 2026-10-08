"""Fixed-message construction for calc CandidateDiscoveryError (no exc body in state)."""

from __future__ import annotations

from typing import Literal

from recommender.calc_client import CalcClientError
from recommender.matchup import MatchupEvidenceError
from recommender.state import CandidateDiscoveryError
from recommender.tool_log import log_tool_call

CALC_UNAVAILABLE_MSG = "The calc service is unavailable."
CALC_INCOMPLETE_MSG = "Calc evidence was incomplete."
DISCOVERY_CALC_MESSAGE_ALLOWLIST: frozenset[str] = frozenset(
    {CALC_UNAVAILABLE_MSG, CALC_INCOMPLETE_MSG}
)

_CalcStage = Literal["coverage", "spof", "candidate_verification"]


def discovery_error_from_exc(
    exc: CalcClientError | MatchupEvidenceError,
    stage: _CalcStage,
) -> CandidateDiscoveryError:
    """Map a calc/evidence failure to a CandidateDiscoveryError with a fixed message."""
    kind: Literal["calc_unavailable", "calc_incomplete"] = (
        "calc_unavailable" if isinstance(exc, CalcClientError) else "calc_incomplete"
    )
    message = CALC_UNAVAILABLE_MSG if kind == "calc_unavailable" else CALC_INCOMPLETE_MSG
    exception_type = type(exc).__name__
    status_code = exc.status if isinstance(exc, CalcClientError) else None
    args: dict[str, object] = {
        "event": "discovery_calc_failed",
        "kind": kind,
        "stage": stage,
        "exception_type": exception_type,
        "status_code": status_code,
    }
    log_tool_call(
        "discovery.calc_error",
        args,
        latency_ms=0.0,
        ok=False,
        error=f"{kind}:{exception_type}",
    )
    return CandidateDiscoveryError(
        kind=kind,
        stage=stage,
        message=message,
        retryable=True,
        exception_type=exception_type,
        status_code=status_code,
    )
