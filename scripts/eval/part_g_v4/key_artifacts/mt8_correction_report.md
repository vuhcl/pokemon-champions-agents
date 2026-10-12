# MT8 / mt7_mt8_ar correction (v4.2)

Evidence JSON: `mt8_correction_analysis.json`.

## Result applied in v4.2 keys

- Jolly Sneasler + Modest Mega-Y Weather Ball: `{+SpD: 294}` only under legal SP≤32.
- Prior committed `+Def:20` / `+Spe:2` were illegal-SpD>32 artifacts (cap-less `spd_hi=rem-hp-df`; +Spe cells needed SpD=34) — not a Timid-branch labeling mixup.
- Timid + Adamant extra (`timid_zard_extra`): `{+Def:276, +Spe:0, +SpD:4}`, Bold 31/1/23/5 (total 60, spare 6).
- Request-set sha unchanged `fc6b150d…`; R9 errata for L470 and L472; fold text at Oct 19–20 pin refresh.
- Keys sha: `b39a706c18c6437933251341c5ab17fa69e94eaa265ea10054b42498d39d6e94` (supersedes v4.1 `5b244be8…7190`).

## Direct-calc anchors

- Modest WB vs neutral 32 HP / 32 SpD: 169–199 into 197 HP — does not guarantee survival.
- Timid WB vs owner hand 32/1/21/4: 169–199 into 197 — fails; Bold Spe gate is 5.
