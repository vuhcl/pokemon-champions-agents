from recommender.graph import build_graph
from recommender.state import Attr, Slot

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"


def test_graph_compiles_and_initializes():
    graph = build_graph().compile()
    result = graph.invoke({"format_id": VGC_MB})
    assert result["game_type"] == "doubles"
    assert result["regulation_mod"] == "champions"
    assert result["picked_team_size"] == 4
    assert len(result["team_draft"]) == 6
    assert all(isinstance(s, Slot) for s in result["team_draft"])
    assert all(not s.role.locked and s.species.value is None for s in result["team_draft"])
    assert isinstance(result["archetype"], Attr)
    assert result["archetype"].value is None
