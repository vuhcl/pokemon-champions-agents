"""Known-value checks for two-sided Clopper-Pearson intervals (no model)."""

from __future__ import annotations

import math
from pathlib import Path

from scripts.eval.part_g_arm.state.clopper_pearson import (
    clopper_pearson_two_sided,
    from_audit_csv,
    from_scorer,
)


def test_zero_of_n_matches_closed_form():
    for n in (1, 10, 100):
        lo, hi = clopper_pearson_two_sided(0, n)
        assert lo == 0.0
        assert abs(hi - (1.0 - (0.025) ** (1.0 / n))) < 1e-12


def test_n_of_n_matches_closed_form():
    for n in (1, 10, 100):
        lo, hi = clopper_pearson_two_sided(n, n)
        assert hi == 1.0
        assert abs(lo - ((0.025) ** (1.0 / n))) < 1e-12


def test_mid_range_5_of_20_stable():
    # Exact CP two-sided 95% for k=5, n=20 (binary-search to 100 iters).
    lo, hi = clopper_pearson_two_sided(5, 20)
    assert 0.0865 < lo < 0.0867
    assert 0.4910 < hi < 0.4911
    assert lo < 5 / 20 < hi


def test_mid_range_50_of_100_symmetric_ish():
    lo, hi = clopper_pearson_two_sided(50, 100)
    assert abs((lo + hi) / 2 - 0.5) < 0.01
    assert lo < 0.5 < hi
    assert 0.398 < lo < 0.403  # ~0.3981
    assert 0.597 < hi < 0.602  # ~0.6019


def test_empty_n_is_nan():
    lo, hi = clopper_pearson_two_sided(0, 0)
    assert math.isnan(lo) and math.isnan(hi)


def test_from_scorer_overall_turn(tmp_path: Path):
    doc = {
        "per_row": [
            {
                "row": "H1",
                "excluded": None,
                "turns": [
                    {"match": True, "key_class_expected": "SERVED"},
                    {"match": False, "key_class_expected": "SERVED"},
                ],
            }
        ]
    }
    # H1 may be mechanical in discovery; if missing, bucket defaults to mechanical.
    rows = from_scorer(doc)
    turn_overall = next(r for r in rows if r["level"] == "turn" and r["group"] == "overall")
    assert turn_overall["passes"] == 1 and turn_overall["n"] == 2
    row_overall = next(r for r in rows if r["level"] == "row" and r["group"] == "overall")
    assert row_overall["passes"] == 0 and row_overall["n"] == 1


def test_from_audit_csv_point_and_section(tmp_path: Path):
    p = tmp_path / "audit.csv"
    p.write_text(
        "row_id,turn,rubric_point_id,verdict,overall,note\n"
        "H1,1,p1,pass,pass,\n"
        "H1,1,p2,fail,pass,\n"
        "H1,2,p1,pass,fail,\n",
        encoding="utf-8",
    )
    rows = from_audit_csv(p)
    pt = next(r for r in rows if r["level"] == "rubric_point" and r["group"] == "overall")
    assert pt["passes"] == 2 and pt["n"] == 3
    sec = next(r for r in rows if r["level"] == "section" and r["group"] == "overall")
    assert sec["passes"] == 1 and sec["n"] == 2  # (H1,1) pass, (H1,2) fail
