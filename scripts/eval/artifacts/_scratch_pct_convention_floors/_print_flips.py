import json
from pathlib import Path

d = json.loads(Path(__file__).with_name("rescale_deltas.json").read_text())
print("showdown-only clears:", len(d["showdown_only_clears_among_admits"]))
for f in d["all_flips"]:
    o, n = f["old"], f["new"]
    print(
        f"{f['category']} | {f['species_id']} | "
        f"old {o['max_source']} {o['max_pct']} ({o['move']}) -> "
        f"new {n['max_source']} {n['max_pct']} ({n['move']}) | "
        f"sd_only={n.get('showdown_only_clear')}"
    )
    if o.get("per_move"):
        print("    old per_move:", o["per_move"])
    if n.get("per_move"):
        print("    new per_move:", n["per_move"])
print("\n--- showdown-only list ---")
for row in d["showdown_only_clears_among_admits"]:
    print(row["category"], row["species_id"], row.get("move"), row.get("max_pct"))
