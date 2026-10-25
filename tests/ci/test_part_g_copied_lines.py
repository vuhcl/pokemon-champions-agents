"""copied_unchanged line definition (scripts/eval/part_g_v4/copied_unchanged_lines.md) on hand-written transcripts."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/eval/part_g_v4"))
import copied_lines as cl  # noqa: E402

USAGE = [{"name": "get_usage_items", "result": {"items": [{"name": "Choice Scarf", "pct": 48.9}, {"name": "Life Orb", "pct": 15.4}]}},
         {"name": "get_usage_teammates", "result": {"rows": [{"name": "Sneasler", "conditional_pct": None, "rank": 1}, {"name": "Pelipper", "conditional_pct": 28.261, "rank": 2}],
                                                    "caveats": ["in-game lists carry rank only; there are no percentages"]}}]
DMG = [{"name": "calc_damage", "result": {"ko_text": "25% chance to OHKO", "calc_desc": "32+ SpA Hydrapple Draco Meteor vs. 32 HP / 0 SpD Castform-Snowy: 154-183 (87 - 103.3%) -- 25% chance to OHKO",
                                           "kochance": {"chance": 0.25, "n": 1, "text": "25% chance to OHKO"}, "damage_range": [154, 183], "defender_hp": 177, "rolls_that_ko": 4}}]


def test_carrier_lines_follow_the_per_tool_table():
    lines = cl.carrier_lines(USAGE + DMG + [{"name": "get_typing", "result": {"types": ["Fire", "Flying"], "source": "x", "species": "Charizard"}},
                                            {"name": "get_speed", "result": {"speed": 177, "note": "Final Speed stat from calc"}},
                                            {"name": "get_move_static", "result": {"type": "Water", "category": "Status", "base_power": 0}}])
    assert "choice scarf 48.9" in lines and "pelipper 28.261" in lines and "sneasler" in lines  # one entry per line; null pct drops the number
    assert "in-game lists carry rank only; there are no percentages" in lines and "25% chance to ohko" in lines
    assert "fire" in lines and "flying" in lines and "water" in lines and "status" in lines and "final speed stat from calc" in lines
    assert not any(ln in ("177", "0", "154", "183", "177", "4") for ln in lines)  # integers (speed, base power, range, HP, counts) are not lines
    assert "charizard" not in lines and "x" not in lines  # other string fields are not lines


def test_a_usage_entry_is_copied_only_when_the_whole_rendered_line_is_in_the_text():
    f = lambda kind, prop, text, line="gate": cl.is_copied_unchanged(kind, prop, line, USAGE, text)  # noqa: E731
    assert f("common_items", "Choice Scarf=48.9", "Choice Scarf   48.9 is the top item.", "usage_pct")  # whitespace and case are normalised
    assert not f("common_items", "Choice Scarf=48.9", "Choice Scarf (48.9%)", "usage_pct")  # punctuation is not
    assert not f("common_items", "Life Orb=15.4", "Life Orb is used 15.4% of the time.", "usage_pct")
    assert f("teammates", "Sneasler", "Teammates: Sneasler, Pelipper") is True  # in-game row renders as the name alone
    assert not f("teammates", "Pelipper", "Pelipper - 28.26%")  # the line is "pelipper 28.261"
    assert f("teammates", "Pelipper", "pelipper 28.261 per cent")
    assert not f("teammates_rank", "Sneasler=1", "Sneasler (rank 1)")  # the rank is in no line, so nothing carries a rank claim


def test_damage_lines_and_the_claims_they_carry():
    full = "The calc says: 32+ SpA Hydrapple Draco Meteor vs. 32 HP / 0 SpD Castform-Snowy: 154-183 (87 - 103.3%) -- 25% chance to OHKO."
    assert cl.is_copied_unchanged("damage_range", "damage range 154-183", "gate", DMG, full)
    assert cl.is_copied_unchanged("percent_of_hp", "percent of HP 87-103.3", "gate", DMG, full)
    assert cl.is_copied_unchanged("ko_chance", "25%", "ko_chance", DMG, "A 25% chance to OHKO.")
    assert not cl.is_copied_unchanged("damage_range", "damage range 154-183", "gate", DMG, "It deals 154-183 damage.")  # the whole calc_desc line is absent
    assert not cl.is_copied_unchanged("ko_count", "4 of 16 rolls KO", "ko_chance", DMG, full)  # counts have no value string
    assert not cl.is_copied_unchanged("guaranteed_ko", "no", "gate", DMG, full)


def test_kinds_without_a_carrier_line_are_never_copied():
    calls = [{"name": "get_speed", "result": {"speed": 177, "note": "Final Speed stat from calc"}}]
    txt = "Ninetales-Alola has a final Speed stat of 177. Final Speed stat from calc"
    assert not cl.is_copied_unchanged("speed_stat", "Ninetales-Alola speed=177", "gate", calls, txt)  # the stat is an integer, not a line
    for kind in ("has_type", "has_ability", "item_legal", "species_legal", "outspeed", "faster", "guaranteed_ko", "ko_needed", "ko_threshold", "hp_arithmetic",
                 "speed_margin", "type_list_member_exact", "ability_list_member_exact"):
        assert cl.value_strings(kind, "x") == []
    t = [{"name": "get_typing", "result": {"types": ["Fire", "Flying"]}}]
    assert cl.is_copied_unchanged("type_list_member", "Fire", "gate", t, "It is a Fire/Flying type.")  # a one-word line counts as a line
    assert not cl.is_copied_unchanged("type_list_member", "Water", "gate", t, "It is a Water type.")
    assert not cl.is_copied_unchanged("type_list_member", "Fire", "gate", [], "Fire")  # no tool result, no line
