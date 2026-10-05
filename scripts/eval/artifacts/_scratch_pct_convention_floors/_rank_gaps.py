import json
from pathlib import Path

d = json.loads(Path(__file__).with_name("distributions.json").read_text())
tr = d["distributions"]["trick_room_22.5"]
gaps = tr["gaps"]
ranked = sorted(gaps, key=lambda g: -g["gap"])
for i, g in enumerate(ranked, 1):
    mark = " <<<" if abs(g["gap"] - 2.664) < 0.001 else ""
    print(f"{i:2d}. gap={g['gap']:.3f}  {g['above']}->{g['below']}{mark}")
print("n_gaps", len(gaps))
# percentile among gaps
idx = next(i for i, g in enumerate(ranked, 1) if abs(g["gap"] - 2.664) < 0.001)
print(f"rank {idx} of {len(gaps)} (1=largest)")

dd = d["distributions"]["dd_presence_1.0"]
print("\nDD top40 above dragapult cliff (2.812):")
for row in dd.get("top40") or []:
    if row["pct"] + 1e-9 >= 2.812:
        print(row)
