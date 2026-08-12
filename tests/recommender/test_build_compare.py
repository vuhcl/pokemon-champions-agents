"""build_compare Spe/damage coverage for all option ids."""

from __future__ import annotations

from recommender.build_compare import compare_build_options, parse_ko_turns
from recommender.state import (
    BuildConfirmationOption,
    BuildOptionGroup,
    ProvisionalSlot,
    TargetRoleDecision,
)


def _provisional() -> ProvisionalSlot:
    return ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(
            role_id="fast_special_attacker", source="other"
        ),
        species="Archaludon",
        ability="Stamina",
        item="Leftovers",
        moves=("Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"),
        nature="Modest",
        spread=(
            ("hp", 32),
            ("atk", 0),
            ("def", 1),
            ("spa", 5),
            ("spd", 25),
            ("spe", 3),
        ),
        fingerprint="fp",
    )


def _groups() -> tuple[BuildOptionGroup, ...]:
    opts = (
        BuildConfirmationOption(
            option_id="spread_nature:default",
            label="Default",
            axis="spread_nature",
            provenance="featured",
            overrides={},
            diff_summary="recommended default",
            tradeoff="keep",
        ),
        BuildConfirmationOption(
            option_id="spread_nature:1",
            label="Fast",
            axis="spread_nature",
            provenance="usage_spread",
            overrides={
                "nature": "Timid",
                "spread": {
                    "hp": 2,
                    "atk": 0,
                    "def": 0,
                    "spa": 32,
                    "spd": 0,
                    "spe": 32,
                },
            },
            diff_summary="spread",
            tradeoff="more Spe",
        ),
        BuildConfirmationOption(
            option_id="spread_nature:2",
            label="Wall",
            axis="spread_nature",
            provenance="usage_spread",
            overrides={
                "nature": "Calm",
                "spread": {
                    "hp": 32,
                    "atk": 0,
                    "def": 2,
                    "spa": 0,
                    "spd": 32,
                    "spe": 0,
                },
            },
            diff_summary="spread",
            tradeoff="more SpD",
        ),
    )
    return (
        BuildOptionGroup(
            axis="spread_nature", prompt="spread", options=opts
        ),
    )


def test_parse_ko_turns_ohko():
    turns, guaranteed = parse_ko_turns("guaranteed OHKO", {"koChance": "guaranteed OHKO"})
    assert turns == 1
    assert guaranteed is True


def test_compare_three_options_spe_and_damage():
    threat = {
        "species": "Incineroar",
        "moves": ["Flare Blitz", "Fake Out", "Parting Shot", "Protect"],
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "evs": {"hp": 32, "atk": 0, "def": 14, "spa": 0, "spd": 20, "spe": 0},
        "nature": "Careful",
    }

    def fake_batch(reqs):
        out = []
        for _ in reqs:
            out.append(
                {
                    "damageRange": [50, 60],
                    "koChance": "32.1% chance to 2HKO",
                    "raw": {"kochance": {"n": 2, "chance": 0.321}},
                }
            )
        return out

    text = compare_build_options(
        _provisional(),
        option_ids=(
            "spread_nature:default",
            "spread_nature:1",
            "spread_nature:2",
        ),
        groups=_groups(),
        state={"coverage": [type("R", (), {"threat": threat})()], "spofs": []},
        calculate_batch_fn=fake_batch,
    )
    assert "spread_nature:default" in text
    assert "spread_nature:1" in text
    assert "spread_nature:2" in text
    assert "Spe" in text
    assert "vs Incineroar" in text
    assert text.count("dmg=") == 3


def test_compare_unknown_option_id():
    text = compare_build_options(
        _provisional(),
        option_ids=("spread_nature:default", "missing"),
        groups=_groups(),
        state={},
    )
    assert "unknown option" in text


def test_compare_no_threat_still_lists_all_spe():
    text = compare_build_options(
        _provisional(),
        option_ids=("spread_nature:default", "spread_nature:1"),
        groups=_groups(),
        state={"coverage": [], "spofs": []},
    )
    assert "spread_nature:default" in text
    assert "spread_nature:1" in text
    assert "No threat context" in text
