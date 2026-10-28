"""Errata MRB1 read-back: Torkoal / Drought / Charcoal at user slot 3."""

from recommender.slot_index import user_slot_to_index
from scripts.eval.part_g_arm.state.pending import build_mrb1_start


def test_mrb1_errata_readback_strings():
    state = build_mrb1_start()
    slot = state["team_draft"][user_slot_to_index(3)]
    assert slot.species.value == "Torkoal"
    assert slot.ability.value == "Drought"
    assert slot.item.value == "Charcoal"
