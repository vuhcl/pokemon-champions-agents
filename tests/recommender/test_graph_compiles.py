from recommender.graph import build_graph

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"


def test_graph_compiles_and_initializes():
    graph = build_graph().compile()
    result = graph.invoke({"format_id": VGC_MB})
    assert result["game_type"] == "doubles"
    assert result["regulation_mod"] == "champions"
    assert result["picked_team_size"] == 4
    assert len(result["team_draft"]) == 6
    assert [s["slot_index"] for s in result["team_draft"]] == list(range(6))
