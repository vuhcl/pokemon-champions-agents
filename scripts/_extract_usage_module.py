"""One-shot: extract usage cluster into role_compendium_usage.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rc_path = ROOT / "recommender" / "role_compendium.py"
setup_path = ROOT / "recommender" / "role_compendium_setup.py"
lines = rc_path.read_text().splitlines()

# 1-based inclusive line numbers from plan review
usage_body = "\n".join(lines[1390:1631] + [""] + lines[1715:1726]) + "\n"
delivery_body = "\n".join(setup_path.read_text().splitlines()[2621:2687]) + "\n"

header = '''"""Mega/showdown usage attribution and delivery helpers (Role Compendium)."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.reconcile import _item_mega_forme
from recommender.usage_data import load_usage, showdown_species_map
from recommender.role_compendium import (
    LiveFetch,
    _MEGA_STONE_FALLBACK_PCT,
    _SHOWDOWN_BASE_USAGE_RATIO,
    _USAGE_SET_PCT_FLOOR,
    _UsageCtx,
    _entry_has_item,
    _entry_has_move,
)

'''

(ROOT / "recommender" / "role_compendium_usage.py").write_text(
    header + usage_body + "\n" + delivery_body
)

# Remove from role_compendium (apply bottom-up)
new_rc = lines[:1390] + lines[1631:1715] + lines[1726:]
rc_path.write_text("\n".join(new_rc) + "\n")

# Remove delivery from setup
setup_lines = setup_path.read_text().splitlines()
new_setup = setup_lines[:2621] + setup_lines[2687:]
setup_path.write_text("\n".join(new_setup) + "\n")
print("ok", len(new_rc), len(new_setup))
