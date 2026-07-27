import pytest

from recommender.format import resolve_format

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"
BSS_MB = "[Gen 9 Champions] BSS Reg M-B"
VGC_MA = "[Gen 9 Champions] VGC 2026 Reg M-A"


def test_vgc_mb():
    assert resolve_format(VGC_MB) == {
        "game_type": "doubles",
        "regulation_mod": "champions",
        "picked_team_size": 4,
    }


def test_bss_mb():
    assert resolve_format(BSS_MB) == {
        "game_type": "singles",
        "regulation_mod": "champions",
        "picked_team_size": 3,
    }


def test_vgc_ma_prior_mod():
    assert resolve_format(VGC_MA)["regulation_mod"] == "championsregma"


def test_short_champions_prefix():
    assert resolve_format("[Champions] VGC 2026 Reg M-B")["picked_team_size"] == 4


def test_non_champions_raises():
    with pytest.raises(ValueError, match="not a Champions format"):
        resolve_format("[Gen 9] OU")


def test_champions_without_vgc_or_bss_raises():
    with pytest.raises(ValueError, match="VGC or BSS"):
        resolve_format("[Gen 9 Champions] Something Else")
