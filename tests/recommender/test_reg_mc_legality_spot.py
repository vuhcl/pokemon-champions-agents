"""Spot-check Reg M-C unbans against the committed legality snapshot."""

from recommender.legality import is_item_legal, is_species_legal, load_snapshot

# Representative sample of the 35 M-B→M-C species unbans (not the full list).
_SPECIES = (
    "Rillaboom",
    "Indeedee",
    "Indeedee-F",
    "Baxcalibur",
    "Absol-Mega-Z",
    "Salamence",
    "Pawmot",
    "Cinderace",
    "Wigglytuff",
    "Toxtricity",
)

_ITEMS = (
    "Terrain Extender",
    "Rocky Helmet",
    "Absolite Z",
    "Leek",
    "Air Balloon",
    "Electric Seed",
)


def test_mc_species_unbans_legal():
    snap = load_snapshot()
    for name in _SPECIES:
        assert is_species_legal(snap, name), name


def test_mc_item_unbans_legal():
    snap = load_snapshot()
    for name in _ITEMS:
        assert is_item_legal(snap, name), name


def test_snapshot_formats_are_reg_mc():
    snap = load_snapshot()
    formats = snap["meta"]["formats"]
    assert "Reg M-C" in formats["vgc"]
    assert "Reg M-C" in formats["bss"]
