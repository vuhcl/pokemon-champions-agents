from recommender.state import Attr, Slot, all_locked, core, empty_slot


def test_empty_slot_and_core():
    draft = [empty_slot() for _ in range(6)]
    assert not all_locked(draft[0])
    assert core({"team_draft": draft}) == draft  # type: ignore[arg-type]

    locked = Slot(
        role=Attr(locked=True),
        species=Attr(locked=True),
        ability=Attr(locked=True),
        item=Attr(locked=True),
        moveset=Attr(locked=True),
        spread=Attr(locked=True),
        nature=Attr(locked=True),
    )
    draft[0] = locked
    assert all_locked(locked)
    assert core({"team_draft": draft}) == draft[1:]  # type: ignore[arg-type]

    assert not all_locked(Slot(**{**locked.__dict__, "ability": Attr()}))
    assert not all_locked(Slot(**{**locked.__dict__, "nature": Attr()}))
