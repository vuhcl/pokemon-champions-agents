"""M-C-era legality sample scenarios (empty direction + named anchor)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from scripts.eval.harness import (
    VGC_MC,
    ScenarioResult,
    accept_recommended_until_terminal,
    bootstrap_once_and_stop,
    locked_pairs,
)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    path: str
    doc: str
    run: Callable[[Any, dict, dict], ScenarioResult]
    format_id: str = VGC_MC


def _result(
    scenario_id: str,
    path: str,
    state: dict[str, Any],
    terminal: str,
    *,
    notes: str = "",
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        path=path,
        terminal=terminal,
        pairs=locked_pairs(state),
        state=state,
        notes=notes,
    )


def _payload(anchor: str) -> dict[str, Any]:
    return {
        "direction_text": None,
        "anchor_text": anchor,
        "pool_entries": None,
        "delegated": False,
        "ownership_mode": None,
    }


def _run_accept(scenario_id: str, path: str, anchor: str):
    def run(graph, config, state) -> ScenarioResult:
        state, terminal = accept_recommended_until_terminal(
            graph,
            config,
            state,
            bootstrap_payload=_payload(anchor),
        )
        return _result(scenario_id, path, state, terminal)

    return run


def _run_once(scenario_id: str, path: str, anchor: str):
    def run(graph, config, state) -> ScenarioResult:
        state, terminal = bootstrap_once_and_stop(
            graph, config, state, _payload(anchor)
        )
        return _result(scenario_id, path, state, terminal)

    return run


SCENARIOS_MC: list[Scenario] = [
    Scenario(
        "mc_baseline_rillaboom",
        "mc_baseline",
        "M-C empty-direction Rillaboom accept-until-terminal",
        _run_accept("mc_baseline_rillaboom", "mc_baseline", "Rillaboom"),
    ),
    Scenario(
        "mc_baseline_indeedee",
        "mc_baseline",
        "M-C empty-direction Indeedee accept-until-terminal",
        _run_accept("mc_baseline_indeedee", "mc_baseline", "Indeedee"),
    ),
    Scenario(
        "mc_baseline_baxcalibur",
        "mc_baseline",
        "M-C empty-direction Baxcalibur accept-until-terminal",
        _run_accept("mc_baseline_baxcalibur", "mc_baseline", "Baxcalibur"),
    ),
    Scenario(
        "mc_baseline_sirfetchd",
        "mc_baseline",
        "M-C empty-direction Sirfetch’d accept-until-terminal",
        _run_accept("mc_baseline_sirfetchd", "mc_baseline", "Sirfetch’d"),
    ),
    Scenario(
        "mc_baseline_cinderace",
        "mc_baseline",
        "M-C Cinderace one-shot bootstrap; fail_closed OK",
        _run_once("mc_baseline_cinderace", "mc_baseline", "Cinderace"),
    ),
    Scenario(
        "mc_baseline_pawmot",
        "mc_baseline",
        "M-C empty-direction Pawmot accept-until-terminal",
        _run_accept("mc_baseline_pawmot", "mc_baseline", "Pawmot"),
    ),
]
