from __future__ import annotations

import importlib.util
import os
from dataclasses import replace
from typing import get_args
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from recommender.anchor_roles import (
    MechanismEvidence,
    classify_anchor_role,
    resolve_anchor_build,
)
from recommender.bootstrap import (
    BootstrapExtraction,
    BootstrapIntakeParseError,
    _DIRECTION_PHRASES,
    _direction_phrase_examples,
    build_anthropic_bootstrap_intake_parser,
    build_ollama_bootstrap_intake_parser,
    discover_bootstrap_directions,
    parse_bootstrap_intake,
    resolve_bootstrap_direction,
    _target_role,
)
from recommender.graph import compile_graph
from recommender.nodes import (
    bootstrap_direction,
    classify_input,
    classify_pending,
    commit_full_slot,
    initialize,
    record_bootstrap_response,
    refine_provisional_slot,
    reset_team,
)
from recommender.recommend import RoleArchetype
from recommender.role_compendium import ReverseCompendiumEvidence
from recommender.state import (
    BootstrapResponsePayload,
    TargetRoleDecision,
    UnresolvedTargetRoleDecision,
)
from recommender.team_candidates import _BASIS_RANK

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"
OLLAMA_INSTALLED = importlib.util.find_spec("langchain_ollama") is not None


def _state(**overrides):
    raw = {"format_id": VGC_MB, **overrides}
    return {**raw, **initialize(raw)}


def _payload(
    *,
    direction=None,
    anchor=None,
    pool=None,
    delegated=True,
    ownership_mode=None,
) -> BootstrapResponsePayload:
    return {
        "direction_text": direction,
        "anchor_text": anchor,
        "pool_entries": pool,
        "delegated": delegated,
        "ownership_mode": ownership_mode,
    }


def _record(state, payload):
    return {**state, **record_bootstrap_response({**state, "turn_payload": payload})}


def test_combined_intake_reuses_presupplied_pool_in_prompt():
    state = _state(available_pool=[{"species": "Pelipper", "item": "Focus Sash"}])

    result = bootstrap_direction(state)

    pending = result["pending_presentation"]
    assert pending["kind"] == "bootstrap_intake"
    assert pending["existing_pool_labels"] == ("Pelipper",)
    assert "direction or anchor" in pending["prompt_text"]
    assert "Pelipper" in pending["prompt_text"]


def test_structured_parser_preserves_raw_text_and_none_versus_empty_pool():
    parser = RunnableLambda(
        lambda _: {
            "direction_text": "Rain offense",
            "anchor_text": "Pelipper",
            "pool_entries": [],
            "delegated": False,
            "ownership_mode": "off",
        }
    )

    payload = parse_bootstrap_intake(parser, "raw user text")

    assert payload == _payload(
        direction="Rain offense",
        anchor="Pelipper",
        pool=(),
        delegated=False,
        ownership_mode="off",
    )


def test_presupplied_pool_is_validated_and_non_species_fields_survive_omission():
    state = _state(
        available_pool=[
            {"species": "Pelipper", "item": "Focus Sash"},
            {"species": "Eternal Floette", "item": "Leftovers"},
        ]
    )

    result = record_bootstrap_response(
        {**state, "turn_payload": _payload(pool=None)}
    )

    assert result["available_pool"] == [
        {"species": "Pelipper", "item": "Focus Sash"},
        {"species": "Floette-Eternal", "item": "Leftovers"},
    ]
    assert result["unresolved_pool_entries"] == ()


def test_explicit_empty_pool_clears_pool_and_unresolved_entries():
    state = _state(
        available_pool=[{"species": "Pelipper"}],
        unresolved_pool_entries=("Old typo",),
    )

    result = record_bootstrap_response(
        {**state, "turn_payload": _payload(pool=())}
    )

    assert result["available_pool"] == []
    assert result["unresolved_pool_entries"] == ()
    assert result["ownership_mode"] == "off"


def test_omitted_pool_preserves_existing_unresolved_diagnostics():
    state = _state(
        available_pool=[{"species": "Pelipper"}],
        unresolved_pool_entries=("Previous typo",),
    )

    result = record_bootstrap_response(
        {**state, "turn_payload": _payload(direction="Rain", pool=None)}
    )

    assert result["available_pool"] == [{"species": "Pelipper"}]
    assert result["unresolved_pool_entries"] == ("Previous typo",)


def test_pool_only_response_delegates_and_derives_owned_first():
    state = _state()
    payload = _payload(pool=("Pelipper",), delegated=True)

    result = record_bootstrap_response({**state, "turn_payload": payload})

    assert result["bootstrap_response"]["delegated"] is True
    assert result["ownership_mode"] == "owned_first"
    assert result["ownership_mode_source"] == "default"


def test_full_delegation_returns_diverse_terminal_ready_options():
    state = _record(_state(), _payload(pool=(), delegated=True))

    discovery = discover_bootstrap_directions(state)

    assert 1 <= len(discovery.candidates) <= 3
    signatures = {
        (
            row.strategic_role_id,
            row.primary_function,
            row.mechanism_ids,
        )
        for row in discovery.candidates
    }
    assert len(signatures) == len(discovery.candidates)
    assert all(
        isinstance(row.target_role_decision, TargetRoleDecision)
        for row in discovery.candidates
    )


def test_exact_explicit_anchor_is_inserted_ahead_of_usage_cut():
    state = _record(
        _state(),
        _payload(
            direction="Redirection",
            anchor="Ariados",
            pool=(),
            delegated=False,
        ),
    )

    discovery = discover_bootstrap_directions(state)

    assert discovery.candidates[0].species == "Ariados"
    assert discovery.candidates[0].strategic_role_id == "redirection"


def test_explicit_anchor_maps_kit_role_alias_to_target_role():
    """RoleArchetype kit labels promote by identity (Fork A), not collapse."""
    state = _record(
        _state(),
        _payload(anchor="Archaludon", pool=(), delegated=False),
    )

    discovery = discover_bootstrap_directions(state)

    assert discovery.clarification is None
    assert discovery.candidates[0].species == "Archaludon"
    assert discovery.candidates[0].strategic_role_id == "bulky_special_attacker"
    decision = discovery.candidates[0].target_role_decision
    assert isinstance(decision, TargetRoleDecision)
    assert decision.producer_name == "bootstrap_kit_role_policy"
    assert decision.confidence == "medium"


def test_explicit_anchor_survives_mismatched_direction_filter():
    """Named anchor is admitted even when its kit role ≠ mapped direction."""
    state = _record(
        _state(),
        _payload(direction="Rain", anchor="Archaludon", pool=(), delegated=False),
    )

    discovery = discover_bootstrap_directions(state)

    assert discovery.clarification is None
    assert discovery.candidates[0].species == "Archaludon"
    assert discovery.candidates[0].strategic_role_id == "bulky_special_attacker"
    assert any(c.strategic_role_id == "rain_setter" for c in discovery.candidates)


def _speed_mech(role_id: str, mechanic: str) -> MechanismEvidence:
    return MechanismEvidence(
        mechanic=mechanic,
        kind="speed_control",
        relation="provides",
        importance="wanted",
        role_id=role_id,
        present=True,
        prerequisite=False,
        activation="move",
        interruptible=True,
        source="synthesized",
        supply="self_supplied",
    )


def test_standard_special_attacker_promotes_by_identity():
    base = classify_anchor_role(resolve_anchor_build("Archaludon"))
    anchor = replace(
        base,
        kit_role="standard_special_attacker",
        role_id="standard_special_attacker",
        mechanisms=(),
        compendium=ReverseCompendiumEvidence(),
    )
    decision = _target_role(anchor)
    assert isinstance(decision, TargetRoleDecision)
    assert decision.role_id == "standard_special_attacker"
    assert decision.producer_name == "bootstrap_kit_role_policy"


def test_support_speed_control_without_tw_tr_stays_identity():
    base = classify_anchor_role(resolve_anchor_build("Whimsicott"))
    anchor = replace(
        base,
        kit_role="support_speed_control",
        role_id="support_speed_control",
        mechanisms=(),
        compendium=ReverseCompendiumEvidence(),
    )
    decision = _target_role(anchor)
    assert isinstance(decision, TargetRoleDecision)
    assert decision.role_id == "support_speed_control"
    assert decision.producer_name == "bootstrap_kit_role_policy"


def test_whimsicott_resolves_tailwind_via_strategic_evidence():
    decision = _target_role(classify_anchor_role(resolve_anchor_build("Whimsicott")))
    assert isinstance(decision, TargetRoleDecision)
    assert decision.role_id == "tailwind_setter"
    assert decision.producer_name == "target_role_from_strategic_evidence"
    assert decision.confidence == "high"


def test_pelipper_prefers_rain_over_incidental_tailwind():
    """Drizzle identity must win before a single TW mechanism short-circuits."""
    decision = _target_role(classify_anchor_role(resolve_anchor_build("Pelipper")))
    assert isinstance(decision, TargetRoleDecision)
    assert decision.role_id == "rain_setter"


def test_tw_and_tr_mechanisms_yield_unresolved_speed_control():
    base = classify_anchor_role(resolve_anchor_build("Whimsicott"))
    anchor = replace(
        base,
        mechanisms=(
            _speed_mech("tailwind_setter", "Tailwind"),
            _speed_mech("trick_room_setter", "Trick Room"),
        ),
    )
    decision = _target_role(anchor)
    assert isinstance(decision, UnresolvedTargetRoleDecision)
    assert decision.reason == "ambiguous_speed_control"
    assert set(decision.ambiguity) == {"tailwind_setter", "trick_room_setter"}
    assert decision.producer_name == "bootstrap_speed_control_pre_pass"


def test_explicit_anchor_ambiguous_speed_control_asks_clarification():
    unresolved = UnresolvedTargetRoleDecision(
        reason="ambiguous_speed_control",
        ambiguity=("tailwind_setter", "trick_room_setter"),
        source="other",
        producer_name="bootstrap_speed_control_pre_pass",
    )
    with patch("recommender.bootstrap._target_role", return_value=unresolved):
        state = _record(
            _state(),
            _payload(anchor="Whimsicott", pool=(), delegated=False),
        )
        discovery = discover_bootstrap_directions(state)
    assert discovery.candidates == ()
    assert discovery.clarification is not None
    assert "ambiguous speed control" in discovery.clarification


def test_handler_round_trip_does_not_repeat_intake():
    state = _record(
        _state(),
        _payload(direction="Rain", anchor="Pelipper", pool=None, delegated=False),
    )

    result = bootstrap_direction(state)

    assert result["pending_presentation"]["kind"] == "candidate_selection"


def test_graph_injects_parser_and_routes_bootstrap_response_back_to_empty_phase():
    parser = RunnableLambda(
        lambda _: {
            "direction_text": "Rain",
            "anchor_text": "Pelipper",
            "pool_entries": None,
            "delegated": False,
            "ownership_mode": None,
        }
    )
    graph = compile_graph(
        MemorySaver(), bootstrap_intake_parser=parser
    )
    config = {"configurable": {"thread_id": "bootstrap-routing"}}

    first = graph.invoke({"format_id": VGC_MB}, config=config)
    second = graph.invoke({"pending_input": "Rain with Pelipper"}, config=config)

    assert first["pending_presentation"]["kind"] == "bootstrap_intake"
    assert second["bootstrap_intake_complete"] is True
    assert second["pending_presentation"]["kind"] == "candidate_selection"


def test_owned_first_prefers_owned_default_without_excluding_global_alternatives():
    state = _record(_state(), _payload(pool=("Pelipper",), delegated=True))

    discovery = discover_bootstrap_directions(state)

    assert discovery.candidates[0].species == "Pelipper"
    assert any(row.species != "Pelipper" for row in discovery.candidates)


def test_bootstrap_passes_expanded_owned_ids_to_query_by_usage():
    state = _record(
        _state(ownership_mode="owned_only"),
        _payload(pool=("Swampert",), delegated=True),
    )
    captured: dict = {}

    def capture_usage(*, available_species=(), ownership_mode="off", **kwargs):
        captured["available_species"] = list(available_species)
        captured["ownership_mode"] = ownership_mode
        return []

    with patch(
        "recommender.bootstrap.query_by_usage", side_effect=capture_usage
    ):
        discover_bootstrap_directions(state)

    species = set(captured.get("available_species") or ())
    assert "swampert" in species
    assert "swampertmega" in species
    assert captured.get("ownership_mode") == "owned_only"


def test_owned_only_without_recognized_pool_is_visible_and_does_not_fallback():
    state = _record(
        _state(ownership_mode="owned_only"),
        _payload(pool=(), delegated=True),
    )

    result = bootstrap_direction(state)

    assert result["candidate_discovery_error"].kind == "no_candidates"
    assert result["pending_presentation"]["kind"] == "bootstrap_intake"
    assert not result["pending_presentation"].get("options")


@pytest.mark.parametrize("mode", ["owned_only", "owned_last", "off"])
def test_user_ownership_mode_is_preserved(mode):
    state = _state(ownership_mode=mode)

    result = record_bootstrap_response(
        {**state, "turn_payload": _payload(pool=("Pelipper",))}
    )

    assert result["ownership_mode"] == mode
    assert result["ownership_mode_source"] == "user"


def test_unresolved_labels_are_ordered_and_rendered():
    state = _record(
        _state(),
        _payload(pool=("Missing One", "Pelipper", "Missing Two")),
    )

    result = bootstrap_direction(state)

    assert state["unresolved_pool_entries"] == ("Missing One", "Missing Two")
    assert result["pending_presentation"]["notices"] == (
        "Couldn't identify: Missing One",
        "Couldn't identify: Missing Two",
    )


def test_unresolved_only_pool_uses_global_off_and_explains_bias():
    state = _record(_state(), _payload(pool=("Missing One",)))

    result = bootstrap_direction(state)

    assert state["ownership_mode"] == "off"
    assert result["pending_presentation"]["kind"] == "candidate_selection"
    assert any(
        "No owned bias" in notice
        for notice in result["pending_presentation"]["notices"]
    )


def test_eternal_floette_alias_accepts_and_dedupes_with_canonical():
    state = _record(
        _state(),
        _payload(pool=("Eternal Floette", "Floette-Eternal")),
    )

    assert state["available_pool"] == [{"species": "Floette-Eternal"}]
    assert state["unresolved_pool_entries"] == ()


def test_basculegion_pool_notice_is_on_bootstrap_presentation():
    state = _record(_state(), _payload(pool=("Basculegion",), delegated=True))
    result = bootstrap_direction(state)
    assert (
        "Basculegion is the male forme; Basculegion-F is also legal."
        in result["pending_presentation"]["notices"]
    )


def test_classify_pending_resolves_abbrev_to_option_species():
    selected = classify_pending(
        "M-Swampert",
        {
            "schema_version": 1,
            "kind": "candidate_selection",
            "slot_index": 0,
            "options": [{"species": "Swampert-Mega", "source": "bootstrap"}],
        },
    )
    assert selected["turn_intent"] == "slot_candidate_selected"
    assert selected["selected_option"]["species"] == "Swampert-Mega"


def test_provenance_claim_types_remain_separate():
    state = _record(_state(), _payload(pool=("Pelipper",), delegated=True))
    pelipper = discover_bootstrap_directions(state).candidates[0]

    bases = {row.basis for row in pelipper.evidence}

    assert {"usage_backed", "ownership_backed", "synthesized"} <= bases
    assert "compendium_backed" in bases
    assert len({row.producer_name for row in pelipper.evidence}) >= 4


def test_unmappable_direction_reprompts_without_coarse_default():
    state = _record(
        _state(),
        _payload(direction="surprise me with something weird", delegated=False),
    )

    with patch("recommender.propose._pick_role") as generic_fallback:
        result = bootstrap_direction(state)

    assert result["pending_presentation"]["kind"] == "bootstrap_intake"
    message = result["candidate_discovery_error"].message
    assert "Couldn't map direction" in message
    examples = _direction_phrase_examples()
    assert examples in message
    registry_phrases = {phrase for phrase, _ in _DIRECTION_PHRASES}
    for phrase in examples.split(", "):
        assert phrase in registry_phrases
    generic_fallback.assert_not_called()
    assert not result["pending_presentation"].get("options")


def test_track1_strategic_evidence_precedes_real_anchor_coarse_kit_role():
    anchor_role = classify_anchor_role(resolve_anchor_build("Tyranitar"))
    assert anchor_role.kit_role in get_args(RoleArchetype)
    assert anchor_role.kit_role != "sand_setter"
    state = _record(
        _state(),
        _payload(direction="Sand", anchor="Tyranitar", delegated=False),
    )

    decision = discover_bootstrap_directions(
        state
    ).candidates[0].target_role_decision

    assert isinstance(decision, TargetRoleDecision)
    assert decision.role_id == "sand_setter"
    assert decision.confidence == "high"
    assert decision.producer_name == "target_role_from_strategic_evidence"


@pytest.mark.parametrize(
    ("direction", "anchor", "role"),
    [
        ("Rain", "Pelipper", "rain_setter"),
        ("Redirection", "Ariados", "redirection"),
    ],
)
def test_track1_roles_reach_existing_refinement_confirmation_and_commit(
    direction, anchor, role
):
    state = _record(
        _state(),
        _payload(direction=direction, anchor=anchor, delegated=False),
    )
    presented = bootstrap_direction(state)
    pending = presented["pending_presentation"]
    selected = classify_input(
        {
            **state,
            **presented,
            "pending_input": anchor,
        }
    )
    selected_state = {**state, **presented, **selected}
    refined = refine_provisional_slot(selected_state)

    assert refined["pending_presentation"]["kind"] == "full_build_confirmation"
    assert refined["provisional_slot"].target_role_decision.role_id == role

    committed = commit_full_slot({**selected_state, **refined})
    slot = committed["team_draft"][0]
    assert slot.role.value == role
    assert slot.species.value == anchor
    assert len(slot.moveset.value) == 4
    assert sum(slot.spread.value.values()) == 66
    assert pending["options"][0]["target_role_decision"].producer_name == (
        "target_role_from_strategic_evidence"
    )


def test_reset_clears_bootstrap_state_but_preserves_available_pool():
    state = _record(_state(), _payload(pool=("Pelipper",)))

    result = reset_team(state)

    assert result["bootstrap_intake_complete"] is False
    assert result["bootstrap_response"] is None
    assert result["bootstrap_intake_error"] is None
    assert result["unresolved_pool_entries"] == ()
    assert "available_pool" not in result


def _provider_failure(_):
    raise RuntimeError("provider unavailable")


@pytest.mark.parametrize(
    "parser",
    [
        None,
        RunnableLambda(_provider_failure),
        RunnableLambda(
            lambda _: {
                "direction_text": None,
                "anchor_text": None,
                "pool_entries": "not-a-list",
                "delegated": True,
                "ownership_mode": None,
            }
        ),
    ],
    ids=["missing-parser", "provider-exception", "malformed-output"],
)
def test_bootstrap_parser_failure_retains_intake_and_mutates_no_facts(parser):
    state = _state(
        available_pool=[{"species": "Pelipper", "item": "Focus Sash"}],
        unresolved_pool_entries=("Existing typo",),
    )
    pending = bootstrap_direction(state)["pending_presentation"]

    updates = classify_input(
        {**state, "pending_presentation": pending, "pending_input": "anything"},
        bootstrap_intake_parser=parser,
    )
    after = {**state, "pending_presentation": pending, **updates}

    assert after["pending_presentation"] == pending
    assert after["available_pool"] == state["available_pool"]
    assert after["bootstrap_intake_complete"] is False
    assert after["bootstrap_response"] is None
    assert after["unresolved_pool_entries"] == ("Existing typo",)
    assert after["turn_payload"] is None
    assert after["bootstrap_intake_error"]


def test_bootstrap_parser_timeout_becomes_actionable_error():
    """A hung structured-output call must fail closed, not hang the graph.

    Live evidence: certain multi-species bootstrap utterances caused 7-8
    minute hangs requiring a manual kill. Simulates the timeout directly
    (rather than waiting out a real 30s timeout in the test suite) by having
    the parser itself raise LLMInvokeTimeout — invoke_with_timeout's own
    real-timed behavior is separately proven in test_llm_invoke.py.
    """
    from recommender.llm_invoke import LLMInvokeTimeout

    def _hangs(_payload):
        raise LLMInvokeTimeout("LLM call did not return within 300s")

    with pytest.raises(BootstrapIntakeParseError, match="took too long"):
        parse_bootstrap_intake(RunnableLambda(_hangs), "trick room with Indeedee-F")


def test_include_raw_parsing_error_is_observable():
    parser = RunnableLambda(
        lambda _: {"raw": object(), "parsed": None, "parsing_error": ValueError("bad")}
    )

    with pytest.raises(BootstrapIntakeParseError, match="structured extraction failed"):
        parse_bootstrap_intake(parser, "anything")


def test_strict_schema_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        BootstrapExtraction.model_validate(
            {
                "direction_text": None,
                "anchor_text": None,
                "pool_entries": None,
                "delegated": True,
                "ownership_mode": None,
                "canonical_species": "Pelipper",
            }
        )


@pytest.mark.skipif(
    not OLLAMA_INSTALLED,
    reason="install the ollama optional dependency",
)
def test_ollama_factory_uses_json_schema_and_include_raw_without_live_model():
    chat = MagicMock()
    chat.with_structured_output.return_value = RunnableLambda(lambda value: value)
    with patch("langchain_ollama.ChatOllama", return_value=chat) as constructor:
        parser = build_ollama_bootstrap_intake_parser("test-model", num_ctx=2048)

    assert parser is not None
    constructor.assert_called_once_with(
        model="test-model", temperature=0, num_ctx=2048
    )
    chat.with_structured_output.assert_called_once_with(
        BootstrapExtraction,
        method="json_schema",
        include_raw=True,
    )


def test_anthropic_factory_uses_json_schema_and_include_raw_without_live_model():
    chat = MagicMock()
    chat.with_structured_output.return_value = RunnableLambda(lambda value: value)
    fake_mod = MagicMock()
    fake_mod.ChatAnthropic = MagicMock(return_value=chat)
    with patch.dict("sys.modules", {"langchain_anthropic": fake_mod}):
        parser = build_anthropic_bootstrap_intake_parser("claude-test")

    assert parser is not None
    fake_mod.ChatAnthropic.assert_called_once_with(
        model="claude-test", temperature=0
    )
    chat.with_structured_output.assert_called_once_with(
        BootstrapExtraction,
        method="json_schema",
        include_raw=True,
    )


@pytest.mark.skipif(
    not OLLAMA_INSTALLED or not os.getenv("BOOTSTRAP_OLLAMA_MODEL"),
    reason="Ollama dependency or BOOTSTRAP_OLLAMA_MODEL is not configured",
)
def test_ollama_bootstrap_adapter_live_smoke():
    parser = build_ollama_bootstrap_intake_parser(
        os.environ["BOOTSTRAP_OLLAMA_MODEL"]
    )

    payload = parse_bootstrap_intake(parser, "You pick. I have no available Pokémon.")

    assert payload["delegated"] is True
    assert payload["pool_entries"] == ()


def test_existing_classification_boundaries_and_evidence_ranks_are_unchanged():
    with pytest.raises(NotImplementedError):
        classify_pending("anything", None)
    selected = classify_pending(
        "yes",
        {
            "schema_version": 1,
            "kind": "candidate_selection",
            "slot_index": 0,
            "options": [{"species": "Pelipper", "source": "bootstrap"}],
        },
    )

    assert selected["turn_intent"] == "slot_candidate_selected"
    assert _BASIS_RANK == {
        "synthesized": 0,
        "ownership_backed": 0,
        "teammate_backed": 1,
        "mechanical_only": 2,
        "usage_backed": 3,
        "compendium_backed": 4,
    }


@pytest.mark.parametrize(
    ("text", "role"),
    [
        ("Rain offense", "rain_setter"),
        ("Rain", "rain_setter"),
        ("Sun", "sun_setter"),
        ("Sand", "sand_setter"),
        ("Snow", "snow_setter"),
        ("Sand offense", "sand_setter"),
        ("Trick Room", "trick_room_setter"),
        ("Trick Room sweeper", "trick_room_sweeper"),
        ("Tailwind", "tailwind_setter"),
        ("Follow Me", "redirection"),
        ("redirection", "redirection"),
        ("Swords Dance", "swords_dance_attacker"),
        ("Nasty Plot", "nasty_plot_attacker"),
        ("fast offense", "fast_attacker"),
        ("fast attacker", "fast_attacker"),
        ("bulky attacker", "bulky_attacker"),
        ("fast pivot", "fast_pivot"),
        ("bulky pivot", "bulky_pivot"),
        ("fast physical attacker", "fast_physical_attacker"),
        ("fast special attacker", "fast_special_attacker"),
        ("fast mixed attacker", "fast_mixed_attacker"),
        ("bulky physical attacker", "bulky_physical_attacker"),
        ("bulky special attacker", "bulky_special_attacker"),
        ("bulky mixed attacker", "bulky_mixed_attacker"),
        ("screens", "screens_support"),
        ("screens support", "screens_support"),
        ("speed control", "support_speed_control"),
        ("support speed control", "support_speed_control"),
    ],
)
def test_reviewed_direction_phrase_mapping_exact_normalized(text, role):
    assert resolve_bootstrap_direction(text) == role


@pytest.mark.parametrize(
    "text",
    [
        "Sand Force",
        "Snow Warning",
        "Sand Stream",
    ],
)
def test_ability_shaped_weather_mentions_do_not_map_as_setters(text):
    assert resolve_bootstrap_direction(text) is None


def test_direction_phrase_examples_come_from_registry():
    examples = _direction_phrase_examples()
    registry_phrases = {phrase for phrase, _ in _DIRECTION_PHRASES}
    asserted = examples.split(", ")
    assert asserted
    assert all(phrase in registry_phrases for phrase in asserted)
    # One example per distinct role_id.
    roles = {role for _, role in _DIRECTION_PHRASES}
    assert len(asserted) == len(roles)
