"""4f change_archetype / read_archetype — MS5 rain conflict audit."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.request_set_rows import load_request_rows, resolve_start_state
from scripts.eval.part_g_arm.state.tools import (
    change_archetype,
    draft_signature,
    read_archetype,
)


def test_ms5_rain_conflict_audit():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MS5"])
    assert st, meta
    before = draft_signature(st)
    after, res = change_archetype(st, ["rain", "offense"])
    assert res.get("ok"), res
    assert draft_signature(after) == before
    kinds = {c["kind"] for c in res["conflicts"]}
    assert "non_rain_weather_ability" in kinds
    assert "rain_reduced_move" in kinds
    drought = next(c for c in res["conflicts"] if c["kind"] == "non_rain_weather_ability")
    assert drought["ability"] == "Drought"
    assert drought["species"] == "Charizard-Mega-Y"
    beam = next(c for c in res["conflicts"] if c["kind"] == "rain_reduced_move")
    assert beam["move"] == "Solar Beam"
    # Pelipper control: no conflict rows for slot 2 / Pelipper
    assert not any(c.get("species") == "Pelipper" for c in res["conflicts"])
    arch = read_archetype(after)
    assert "rain" in [c.casefold() for c in arch["components"]]
    assert arch["locked"] is True


def test_read_archetype_empty():
    from scripts.eval.part_g_arm.state.fixtures import empty_team

    r = read_archetype(empty_team())
    assert r["components"] == [] and r["locked"] is False
