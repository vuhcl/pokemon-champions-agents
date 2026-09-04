"""Pass-through CalcClient + classify_matchup spies for mechanical-claim eval."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import recommender.matchup as matchup_mod
from recommender.calc_client import CalcClient, CalcRequest
from recommender.matchup import MatchupResult, _matchup_cache_key
from scripts.eval.harness import eval_scenario_id, eval_turn_index

_original_classify = matchup_mod.classify_matchup
_original_batch = CalcClient.calculate_batch


@dataclass
class CalcLogEntry:
    scenario_id: str
    turn_index: int
    requests: list[CalcRequest]
    responses: list[Any]


@dataclass
class MatchupCapture:
    scenario_id: str
    turn_index: int
    build_a: dict[str, Any]
    build_b: dict[str, Any]
    field: dict[str, Any] | None
    result: MatchupResult
    cache_key: tuple[Any, ...]


@dataclass
class EvalSpies:
    calc_log: list[CalcLogEntry] = field(default_factory=list)
    matchups: list[MatchupCapture] = field(default_factory=list)
    _seen_keys: set[Any] = field(default_factory=set, repr=False)
    _patches: list[Any] = field(default_factory=list, repr=False)

    def install(self) -> None:
        spies = self

        def logging_calculate_batch(self_client, requests: list[CalcRequest]):
            responses = _original_batch(self_client, requests)
            spies.calc_log.append(
                CalcLogEntry(
                    scenario_id=eval_scenario_id.get(),
                    turn_index=eval_turn_index.get(),
                    requests=deepcopy(list(requests)),
                    responses=deepcopy(list(responses)),
                )
            )
            return responses

        def spying_classify_matchup(build_a, build_b, field=None, *, client=None):
            result = _original_classify(build_a, build_b, field, client=client)
            key = _matchup_cache_key(build_a, build_b, field)
            if key not in spies._seen_keys:
                spies._seen_keys.add(key)
                spies.matchups.append(
                    MatchupCapture(
                        scenario_id=eval_scenario_id.get(),
                        turn_index=eval_turn_index.get(),
                        build_a=deepcopy(dict(build_a)),
                        build_b=deepcopy(dict(build_b)),
                        field=deepcopy(dict(field)) if field else None,
                        result=result,
                        cache_key=key,
                    )
                )
            return result

        patches = [
            patch.object(CalcClient, "calculate_batch", logging_calculate_batch),
            patch.object(matchup_mod, "classify_matchup", spying_classify_matchup),
            patch("recommender.coverage.classify_matchup", spying_classify_matchup),
            patch(
                "recommender.threat_counters.classify_matchup", spying_classify_matchup
            ),
        ]
        for p in patches:
            p.start()
            self._patches.append(p)

    def uninstall(self) -> None:
        while self._patches:
            self._patches.pop().stop()
