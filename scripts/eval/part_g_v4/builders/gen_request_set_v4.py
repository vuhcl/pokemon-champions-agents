#!/usr/bin/env python3
"""Emit part_g_v4/part3_request_set_v4.md from v3 structure + Part G v4 corrections."""
from __future__ import annotations

import json
from pathlib import Path

from _lib import PKG, ROOT

OUT = PKG / "part3_request_set_v4.md"
keys = json.loads((PKG / "key_artifacts" / "derived_keys.json").read_text())
snap = json.loads((ROOT / "data/legality/champions.v1.json").read_text())

h11 = "{" + ",".join(keys["h11"]["key_set"]) + "}"
hu1 = "{" + ",".join(n for n, _ in keys["hu1"]) + "}"
ann = keys["hn2"]["ann_jolly32"]
ghol = keys["hn2"]["ghol_timid32"]
out = ann > ghol
hn2d = keys["hn2d_mega_blaziken"]
bbase, bj, bj1 = hn2d["base_spe"], hn2d["jolly_32"], hn2d["jolly_32_plus1"]
isn = keys["is3_is4"]
sstack = isn["Slowbro"]["max_stack"]
dplus = isn["Dragapult"]["plus_32"]
pstack = isn["Pincurchin"]["max_stack"]
aplus = isn["Alakazam-Mega"]["plus_32"]
modest = keys["h15_primarina"]["modest_top"]
top10 = ", ".join(f"{r}:{n}" for r, n, _ in keys["ingame_top10_usage"])
hn2d_opp = keys.get("hn2d_opp") or {
    "species": "Garchomp",
    "nature": "Jolly",
    "spe_sp": 32,
    "spe": 169,
}
dm3 = keys.get("dm3") or {
    "attacker": "Tyranitar",
    "move": "Rock Slide",
    "targets": ["Incineroar", "Rillaboom"],
}
dm4 = keys.get("dm4") or {
    "attacker": "Garchomp",
    "move": "Earthquake",
    "target": "Incineroar",
}
dm_out = keys.get("dm_outputs") or {}
dm3k = dm_out.get("dm3") or {}
dm4k = dm_out.get("dm4") or {}
dm6k = dm_out.get("dm6") or {}
dm7k = dm_out.get("dm7") or {}
inc_shared = dm_out.get("shared_incineroar_top_joint") or {}
ar3 = keys.get("ar3") or {}
ar3_aj = ar3.get("t4_aqua_jet_survival") or {}
ar3_fb = ar3.get("t4_flare_blitz_recoil") or {}
ar3_p1 = ar3.get("part1_followup") or {}
mt7_sa = keys.get("mt7_special") or {
    "species": "Gholdengo",
    "move": "Make It Rain",
}
ix2 = keys.get("ix2_pain_split_magic_guard") or {}


def _dmg_ko(case: dict) -> str:
    dr = case.get("damage_range") or []
    ko = case.get("ko_chance") or ""
    if len(dr) == 2:
        return f"{dr[0]}–{dr[1]} ({ko})"
    return ko or "?"


_inc_j = (inc_shared.get("joint") or {}).get("evs") or {}
_inc_nat = (inc_shared.get("joint") or {}).get("nature") or "Adamant"
_inc_item = inc_shared.get("item") or "Sitrus Berry"
_ril_j = ((dm3k.get("rillaboom_defender") or {}).get("top_joint") or {})
_ril_evs = _ril_j.get("evs") or {}
_dm3_inc_on = ((dm3k.get("incineroar_defender") or {}).get("cases") or {}).get("intimidate_on") or {}
_dm3_inc_off = ((dm3k.get("incineroar_defender") or {}).get("cases") or {}).get("intimidate_off") or {}
_dm3_ril_on = ((dm3k.get("rillaboom_defender") or {}).get("cases") or {}).get("intimidate_on") or {}
_dm3_ril_off = ((dm3k.get("rillaboom_defender") or {}).get("cases") or {}).get("intimidate_off") or {}
_dm4_on = ((dm4k.get("incineroar_defender") or {}).get("cases") or {}).get("intimidate_on") or {}
_dm4_off = ((dm4k.get("incineroar_defender") or {}).get("cases") or {}).get("intimidate_off") or {}
_ar3_worst = (ar3_aj.get("worst_joint") or {}).get("nature") or "Quiet"
_ar3_aj = ar3_aj.get("aj1_max") or 27
_ar3_chain = (
    f"{ar3_aj.get('after_aj1')}/{ar3_aj.get('belly_drum_cost')}/"
    f"{ar3_aj.get('after_bd')}/{ar3_aj.get('after_aj2')}"
)
_ar3_hp0 = (ar3_aj.get("hp0_confirm") or {}).get("after_aj2")
_ar3_key = (
    f"Per-turn: t1 SERVED (Mega-X+Charizardite X+Belly Drum; Tough Claws explicit). "
    f"t2 SERVED|ASK — Flame Charge/Scale Shot only. t3 MUTATION-OK lock Flame Charge. "
    f"t4 SERVED — AJ worst joint {_ar3_worst} Life Orb {_ar3_aj}/hit; chain at HP-32 (cx HP 185): "
    f"{_ar3_chain}; HP-0 leaves {_ar3_hp0}; BD remaining from full 93. "
    f"Flare Blitz recoil ≈61.71 (0.33× Primarina HP 187); calc % 33.3% of atk HP 185 / 40.3% of 153; "
    f"exact claims allow 61–62 in-game rounding. OHKO mins across 3 COMMON_JOINT (def_hp 187): "
    f"Jolly FP/TF Atk-14; Adamant FP/TF 0; Fire Fang Adamant 22. ASSUME-STATE t4: Jolly HP0/Atk14/Spe28. "
    f"t5 PARTIAL — Jolly for Scarf cells 231–241; leftover 24. "
    f"Keys: derived_keys.ar3 (+ part1_followup) + calc/ar3_*."
)
_dm3_key = (
    f"Doubles; Rock Slide allAdjacentFoes → 0.75 (≥2 targets assumed). "
    f"Shared Incineroar top joint {_inc_nat} SP {_inc_j} item {_inc_item} ability Intimidate. "
    f"Rillaboom top joint {_ril_j.get('nature')} SP {_ril_evs} item {(_ril_j and (dm3k.get('rillaboom_defender') or {}).get('top_item'))}. "
    f"BOTH Intimidate cases per defender: on=attacker Atk −1; off=0. "
    f"Incineroar on {_dmg_ko(_dm3_inc_on)}; off {_dmg_ko(_dm3_inc_off)}. "
    f"Rillaboom on {_dmg_ko(_dm3_ril_on)}; off {_dmg_ko(_dm3_ril_off)}. "
    f"Scoring: both labeled=SERVED; on-only with assumption+offer=SERVED(ASSUME-STATE); off-only/unstated=false. "
    f"dm_outputs.dm3"
)
def _min_atk(case: dict) -> str:
    v = case.get("min_atk_sp")
    return "null (unreachable at 32)" if v is None else str(v)


_dm4_on_sp = _dm4_on.get("spread_0_75") or {}
_dm4_on_st = _dm4_on.get("single_target_doubles") or {}
_dm4_off_sp = _dm4_off.get("spread_0_75") or {}
_dm4_off_st = _dm4_off.get("single_target_doubles") or {}
_dm4_key = (
    f"Earthquake allAdjacent → 0.75 when ≥2 targets (Doubles); single-target-in-doubles = no 0.75 "
    f"(not a Singles-format row). Same Incineroar top joint/item/Intimidate as DM3. "
    f"BOTH cases: on −1 / off 0. At Atk SP 32 figures: "
    f"on spread {_dmg_ko(_dm4_on_sp)}; on single-target {_dmg_ko(_dm4_on_st)}; "
    f"off spread {_dmg_ko(_dm4_off_sp)}; off single-target {_dmg_ko(_dm4_off_st)}. "
    f"min_atk_sp for guaranteed OHKO (min_roll≥HP, search 0–32): "
    f"on/spread={_min_atk(_dm4_on_sp)}; on/single={_min_atk(_dm4_on_st)}; "
    f"off/spread={_min_atk(_dm4_off_sp)}; off/single={_min_atk(_dm4_off_st)}. "
    f"Arm answer must match stored min_atk_sp for the case it states. "
    f"Same Intimidate scoring as DM3. dm_outputs.dm4"
)
_dm6_att = dm6k.get("attacker") or {}
_dm6_key = (
    f"ASSUME-STATE. Gallade-Mega Inner Focus + Galladite; nature/SP/item from top Showdown joint+item "
    f"({_dm6_att.get('nature')} SP {_dm6_att.get('evs')} item {_dm6_att.get('item')}; "
    f"source={(_dm6_att.get('source') or {}).get('nature_sp')}). "
    f"Close Combat (Fighting {dm6k.get('type_effectiveness_vs_incineroar')}× vs Fire/Dark). "
    f"Single case attacker Atk stage 0 (no Intimidate drop). "
    f"Key: {_dmg_ko(dm6k.get('case') or {})}. "
    f"Arm must state attacker nature/SP/item matching key; mismatch → not SERVED; "
    f"numbers with no stated attacker conditions → false claim; −1 or second case → false. "
    f"Not a spread move. dm_outputs.dm6"
)
_dm7_att = dm7k.get("attacker") or {}
_dm7_key = (
    f"ASSUME-STATE. Annihilape; nature/SP/item from top Showdown joint+item "
    f"({_dm7_att.get('nature')} SP {_dm7_att.get('evs')} item {_dm7_att.get('item')}); "
    f"assume top ability Defiant ({_dm7_att.get('ability_usage_pct')}% Showdown). "
    f"Close Combat (Fighting {dm7k.get('type_effectiveness_vs_incineroar')}×). "
    f"on=Intimidate then Defiant → net +1 Atk {_dmg_ko(((dm7k.get('cases') or {}).get('intimidate_on') or {}))}; "
    f"off=0 {_dmg_ko(((dm7k.get('cases') or {}).get('intimidate_off') or {}))}. "
    f"Arm must state attacker nature/SP/item + Defiant matching key; mismatch/unstated → not SERVED / false. "
    f"Kingambit rejected (top-4 resisted). Not a spread move. dm_outputs.dm7"
)

modest_evs = modest["evs"] if modest else {}
_modest_cw = modest.get("chaos_weight", modest.get("pct")) if modest else None
modest_note = (
    f"Modest top joint SP={modest_evs} chaos_weight pct≈{_modest_cw:.1f}"
    if modest and _modest_cw is not None
    else "Modest absent"
)

# Illegal / legal item lists from pinned legality blob
past_items = sorted(
    v["name"] for v in snap["items"].values() if v.get("is_nonstandard") == "Past"
)
past_csv = ", ".join(past_items)


def _item_legal(name: str) -> bool:
    sid = "".join(c for c in name.lower() if c.isalnum())
    it = snap["items"].get(sid)
    return it is not None and it.get("is_nonstandard") is None


TYPE_BOOST = [
    "Charcoal",
    "Mystic Water",
    "Miracle Seed",
    "Magnet",
    "Soft Sand",
    "Never-Melt Ice",
    "Black Glasses",
    "Spell Tag",
    "Dragon Fang",
    "Sharp Beak",
    "Silver Powder",
    "Poison Barb",
    "Twisted Spoon",
    "Black Belt",
    "Silk Scarf",
    "Metal Coat",
    "Fairy Feather",
]
RESIST_BERRIES = [
    "Occa Berry",
    "Passho Berry",
    "Wacan Berry",
    "Rindo Berry",
    "Yache Berry",
    "Chople Berry",
    "Kebia Berry",
    "Shuca Berry",
    "Coba Berry",
    "Payapa Berry",
    "Tanga Berry",
    "Charti Berry",
    "Kasib Berry",
    "Haban Berry",
    "Colbur Berry",
    "Babiri Berry",
    "Chilan Berry",
    "Roseli Berry",
]
legal_type_boost = [n for n in TYPE_BOOST if _item_legal(n)]
legal_resist = [n for n in RESIST_BERRIES if _item_legal(n)]
assert _item_legal("Expert Belt")
assert all(_item_legal(n) for n in ["Life Orb", "Sitrus Berry", "Leftovers", "Focus Sash"])

# Water∧Fire intersection for HC1
water_fire = sorted(
    sp["name"]
    for sp in snap["species"].values()
    if sp.get("is_nonstandard") is None
    and "Water" in (sp.get("types") or [])
    and "Fire" in (sp.get("types") or [])
)
assert water_fire == [], water_fire

HEADER = f"""# Part G v4 — request-level held-out set (DRAFT — do not run)

**HEAD:** `e935de9b2051da6fe968b87087b27c7b5901168b`  
**Source:** `scripts/eval/part_g_v4/part3_request_set_v3.md` + Part G v4 edits  
**Companion battery design:** `scripts/eval/part_g_v4/part3_claim_battery_design_v4.md`

**Scoring:** **per slice** (no pooled score across slices). Outcome **class** per row = desired system behavior. Comparison conditions: bare LLM vs model-driven arm; CLI is capability reference only. The **bare-LLM condition applies only to stateless rows** (idle / empty start with no pending, no locked team, no multi-turn prior). Claim-rate gates live in the claim battery, not here. Ungated IX*/MV*/HP* report (a) correctness vs key and (b) tool-verified share; never enter ≤2% gates.

**STALL is not an acceptable expected class** for desired behavior.

---

## Part 0 — global rules

### Class glossary

SERVED | PARTIAL | FAIL-CLOSED | **ASSUME-STATE** | **ASK** | **ASK\\|ASSUME-STATE** (MC1 only) | MUTATION-OK | MUTATION-REFUSED | NO-MUTATION

- **PARTIAL** = safe subset only; drops named in Acceptance / frozen checklist.
- **ASSUME-STATE:** state a concrete assumption → confirm before tools **or** run tools, report results, and ask whether the assumption matches. Bare “what do you mean?” / refuse-without-assumption = fail.
- **ASK:** ask a clarifying question; no state change; no guess. Used when separate requests (across turns or clauses) conflict with each other and either could be performed, or when the referent is under-specified (ambiguous “it” / ordinal / multi-select).
- **FAIL-CLOSED** hard set (undefined/no-data refuse, or a single request that contradicts itself and cannot be performed under any reading): **H13** (no per-team win-rate data), **H14** (OOF format), **H16** (no history / false premise of a prior pick), **HC1** (self-contradictory constraint that no legal team can satisfy).  
  **Contradiction test:** one request that contradicts itself and cannot be performed under any reading = FAIL-CLOSED. Separate requests (across turns or clauses) that conflict with each other, where either could be performed, = ASK.

### Property-check spreads

A proposed nature+SP vector passes only if every stated property holds (survive OHKO, outspeed target cells, legal SP 0–32/stat, sum ≤66, integers). Extra properties claimed without evidence count as separate claims.

### Set-answer scoring rule (H6, MT2, HU2, HN1, H11, HU2b, IX5/IX7 sets, and any set-valued key)

- A named member **not in the key** = **false claim**.
- A **missing** key member (incomplete list) = **incomplete**, not false.

### Usage sources + D9 + constants

- **Default usage source for keys:** in-game doubles blob. **Showdown** for Mega/base form handling and for **joint** nature+spread.
- Showdown `top_spreads`: chaos weight; `evs` fields are Champions **SP**; blob retains up to **8**; coverage may omit natures/spreads (document gaps).
- **COMMON_JOINT:** top 3 retained Showdown joint spreads by chaos weight. Take the top 3 first, then for outspeed comparisons drop the max-speed cell and mention its share.
- **COMMON_SPEED:** top 3 distinct grouped final-Speed values (speed-only rows).
- **COMMON_ITEM:** items by descending usage until cumulative ≥ 90%, max 5. The `"nothing"` entry (no item) counts toward both the five slots and the cumulative cutoff when present.
- **Tie-break:** higher final Speed first. Ability share denominator: the species' TOTAL ability weight (not the sum of retained entries).
- **D9:** in-game extractor rank-pairs `top_spreads` with `stat_alignment` nature (`fetch_usage_mc_munchstats.py` `spreads_with_natures`) — **not** a joint observation. Arm must not present in-game spread+nature as jointly observed.

### Forward speed

Champions Spe: `floor(n * (base + SP + 20))` with Spe+ natures `n=1.1`, Spe− `n=0.9`, else `1.0`; SP 0–32. Scarf ×1.5 after nature. Tailwind ×2 on the final Spe.

- Base grid has no field effects. Tailwind ×2 as extra lines. No Scarf+Tailwind stacking in forward grids. Trick Room named as excluded.
- Core cells: up to 4 (max speed and most-common speed on each side), grouped by outcome (outspeeds / ties / outsped). Quantified summary claims are scored against the FULL grid.
- Scarf adds only 2 entries per side (Spe-32 at neutral and at beneficial nature, with Scarf); other speed values are always without Scarf.
- Move-sourced boosts never combine with Scarf. Ability-sourced boosts (Speed Boost) can.
- Boost list: generated from `data/moves/stat_boosts.v1.json` plus a short hand-listed set of abilities (Speed Boost, Unburden, Chlorophyll, Surge Surfer, Swift Swim, Sand Rush, Slush Rush). Moves that raise Speed by two or more stages (Agility, Shift Gear and similar) are excluded from the boost list, except when the user's own mon has its moveset locked and that moveset contains one; then that move is counted, as a move-sourced boost, in that mon's forward grid. (Move-sourced boosts never combine with Scarf; Tailwind lines still apply. The exception covers the user's locked mon only. Opponent mons and unlocked own mons keep the exclusion, including when such a move is in the opponent's top 4 moves.)
- Opponent boosts count only if their top ability is Speed-boosting or a boosting move is in their top 4. Core cells only. Conditional abilities run with and without their condition.
- Quantified claims must match script Spe. Mirror max-speed: state both Spe values.

### Mega naming

"Mega \<Species\>" means \<Species\>-Mega when that form exists and is legal in the pinned blob. "Mega \<Species\> X", "Y" or "Z" means \<Species\>-Mega-X / -Y / -Z. If a legal species has no plain \<Species\>-Mega (pinned: Charizard, Raichu, Meowstic), a bare "Mega \<Species\>" is ambiguous — the arm must ASK, or state an assumption (ASSUME-STATE). A prompt that relies on a bare name for such a species is only allowed in **MC1**; everywhere else the prompt must carry the form. If a species has both a plain and a lettered mega (pinned: Absol, Garchomp, Lucario), the bare name resolves to the plain form. Species with `is_nonstandard` set (Past or Future) are illegal and excluded. Source for any mega-specific build, moves, items or spreads is the Showdown per-form entry (the in-game list is species-level).

### Choice lock (hand rule — no field in pinned items blob)

Choice Scarf locks the holder into one move each turn. Status moves remaining in the draft become unusable while Scarf is held; the arm must name each such status move and offer swaps without silently changing moves.

### Inverse speed

- The min-SP claim has 4 parts: neutral and beneficial nature, each as “N suffices and N−1 does not”. (This replaces the older “reachable / needs Scarf / needs TW / unreachable” framing.)
- Neutral is always reported. Beneficial is added if neutral needs more than 32 but beneficial is reachable, or if beneficial is a common nature. A locked nature gives only that nature.
- Budget R = 66 − SP in the other stats (unlocked: R = 66). Outcomes: fits / shortfall (the arm does not recommend which stat to cut) / unreachable.
- Reachability considers the Scarf+Tailwind stack. The arm states the minimum required stat and recorded usage, and never says “not recommended”.

### Damage

Calc HTTP; parse description string. Crit condition lives in the string (“on a critical hit”); score crit-conditioned claims from that string (no invented `isCrit` API). Avoids-OHKO = max roll < defender HP (all 16). Pass KO phrasing starts at 2HKO+; fail = OHKO chance text. Items: locked else COMMON_ITEM grouped into **legal** effect classes only.

- **Explicit ability (cross-cutting):** every calc request (key builder; design intent for the arm) sends `ability` for attacker and defender. Value from pinned legality (mega forms: their single ability; base forms: user-stated, else arm states an assumption → ASSUME-STATE). Never rely on the hosted calc default (Mega-Y Drought is accidentally right; Mega-X Blaze vs Tough Claws is silently wrong). Key builder asserts legality + desc echo for abilities named in the roll (e.g. Tough Claws on contact). Damage claims carry the ability they were computed under; verifier compares like with like.
- **Illegal items (must not be assumed):** every item in pinned `data/legality/champions.v1.json` with `is_nonstandard` = `"Past"` (n={len(past_items)}): {past_csv}.
- **Legal effect-class items used in keys/grids (verified against that blob):** Expert Belt; Life Orb; Muscle Band; Wise Glasses; type-boost items: {", ".join(legal_type_boost)}; resist berries: {", ".join(legal_resist)}; defender Sitrus Berry / Leftovers / Focus Sash; Rocky Helmet; Air Balloon (ignored for Ground moves after damage).
- Focus Sash/Sturdy mention when relevant.
- Chip damage (Rocky Helmet 1/6, Rough Skin/Iron Barbs 1/8, Life Orb recoil 1/10, floored, minimum 1) is a separate standalone-formula line.
- Reverse damage + speed order only if own Pokémon is locked.

### Mutation vs WORKING STATE

- Mutations are tool-executed, user-initiated, with a tool-rendered read-back: lock, unlock, reset, commit, rejection, archetype change, and team-level constraints (anything spanning more than one slot or the whole team, e.g. “all Water types”).
- Slot conditions and proposed spreads are per-slot DRAFTS, not mutations; kept on topic change, cleared by reset. A topic switch makes the arm ask whether to lock first; “no” keeps the draft.
- Team-level mutations re-validate drafts and invalidate pending option lists (D8).
- A named species not on the team with a slot condition: the arm asks “Add X?” and places it as a draft in the lowest slot that is empty, unlocked and has no draft; with no open slot it asks which to replace; “no” means not recorded.
- Option lists bind strictly: exact id, exact number, or exact label only. “The second one” does not bind.

### Re-pin invalidation

Any re-pin of legality or usage blobs **invalidates** all answer keys below. Keys valid only against the frozen directory that copies both usage blobs + legality blob and records the repo commit.

### Oracle independence (ADR-060)

Pinned JSON / standalone Champions Spe–HP formulas / calc HTTP. Do **not** use `claim_is_true_against_snapshot`, `try_parse_verifiable_claim_from_message`, `scripts/eval/oracle.py`, or `scripts/eval/species_fact_oracle.py` as the eval answer-key oracle. (One-time Showdown cross-check for battery fidelity reporting is separate; see battery design.)

---

## Defect list (D1–D9)

| Id | Status | Summary |
|---|---|---|
| **D1** | Lean | Do not change `query_teammates` here; Showdown-first vs in-game default. |
| **D2** | Lean | Scorer checks usage claim vs **labeled** source; unlabeled → unverifiable; wrong source → separate outcome. |
| **D3** | Lean | Threat Spe assumption in question text (HU2). |
| **D4** | Lean | Calc HTTP batch; independence = invocation path. |
| **D5** | Lean | Per-template parsers + human audit; LLM judge cross-check only. |
| **D6** | Lean | Defer derived-stat; HU1 request-level only. |
| **D7** | Defect | `query_teammates` Showdown-first (`recommender/teammates.py` L296–341) vs Vu in-game default. Arm usage tool must take explicit source + label. |
| **D8** | Defect | **Missing `candidate_selection` stale gate** (follow-up 2). FBC has fingerprint refuse (`nodes.py` L787–804); CS ordinal bind has none (`nodes_classify.py` L1489–1569). Arm mutation tools **must invalidate** pending when team/provisional state changes. |
| **D9** | Defect | In-game `spreads_with_natures` rank-pairs spread with `stat_alignment` nature — not a joint. |

---

## Mismatch banner (defect D7)

Vu policy: **default usage = in-game doubles**; Showdown only for base/Mega form handling and joint nature+spread.  
**Code mismatch:** `query_teammates` is **Showdown-first**. Do **not** change it here (D1). Arm usage tool: explicit source argument + claim labels.

---

## Pinned data record

SHAs below are **git blob SHAs** (`git hash-object <file>`), not raw content hashes.

| Role | Path @ recorded HEAD | Blob SHA (`git hash-object`) |
|---|---|---|
| Legality | `data/legality/champions.v1.json` | `ca5bb8181448765875396ce3b02561923c3e4694` |
| In-game usage (default keys) | `data/usage/champions-reg-mc.ingame_doubles.v1.json` | `65f8c51e3ce4068736a2c8aa65609f836064cbcc` |
| Showdown usage (form/Mega / joints) | `data/usage/champions-reg-mc.showdown_doubles.v1.json` | `63bcefe4512a202d75b62e79f2ccc5436527b46e` |
| Move static (priority / target / displayed PP) | `data/moves/static.v1.json` | `c4f2aabe8ffb420a70e77afaa50b5a4d616a1f54` |
| Move flags | `data/moves/flags.v1.json` | `89a00b2c46df4c139027f81f77627a4a85fdd631` |
| Move accuracy | `data/moves/gen9_accuracy.v1.json` | `4eeb96eacfdee56ccaf7e9a7b8d6a65c6fb1da20` |
| Move stat boosts | `data/moves/stat_boosts.v1.json` | `040059884684b27f0894e484c7c987fb5aef158e` |

- In-game blob commit: `73c1635071fea8f15455ab18f0fe56b2fbad5ca5`
- In-game label: `ingame_doubles_extracted_at` = `2026-10-07T20:42:25Z`; `munchstats_captured_on` = `2026-10-06`
- Showdown label: `showdown_month` = `2026-09`; `showdown_extracted_at` = `2026-10-05T23:13:53Z`
- Legality Showdown source commit (meta): `9fb3a5b99f1a0bea17f495c5cc1bfe04fdd19c3e`; `meta.source.mod` = `champions`; formats = Reg M-C
- Frozen run dir: copy **both** usage blobs + legality; record repo commit `e935de9…` (pin record — not “consumer clone HEAD must equal pin”)
- Move-inventory pins: `static.v1.json` at commit `8cfe63a` (PR #259); flags / accuracy / boosts refresh merge commit `6674b74c41810f63d1a25453d26ea8498d0b9341` (PR #260); four move blob SHAs in the table above

---

## Usage row pct-margin report

| Id | Source | Rank structure | Has pct margin? | Margin / note |
|---|---|---|---|---|
| **H6** | ingame `rillaboom.teammates` | strings (no pct) | **No** | **Unordered set** of first 5 |
| **MT2** | ingame teammates ∩ | string lists (no pct) | **No** | **Unordered set** |
| **HN3** | ingame `glimmora.common_items` | `{{name,pct}}` | **Yes** | Ordered; rank3–4 Δ **1.2 pp** |
| **HU2** | ingame `usage_rank` | integer ranks | **Yes** | Rank 10 Golisopod vs 11 Archaludon |

---

## Speed keys — script + output (ADR-060; no recommender imports)

Champions: `floor(n * (base + SP + 20))`; Spe-boosting `n=1.1`; **SP 0–32**. Helpers: `scripts/eval/part_g_v4/builders/_lib.py`, `scripts/eval/part_g_v4/builders/derive_keys.py` → `scripts/eval/part_g_v4/key_artifacts/derived_keys.json`.

```
H4: Jolly Spe-32 Garchomp -> 169; Timid Spe-32 Gholdengo -> 149
HN2: Jolly Spe-32 Annihilape -> {ann}; Timid Spe-32 Gholdengo -> {ghol}; outspeeds={out}
HN2d: Blaziken-Mega base Spe {bbase}; Jolly Spe-32 -> {bj}; +1 stage -> {bj1}; opp {hn2d_opp['species']} {hn2d_opp['nature']} Spe-{hn2d_opp['spe_sp']} -> {hn2d_opp['spe']}
IS3 Slowbro max stack vs Dragapult Timid-32: stack={sstack} vs {dplus}
IS4 Pincurchin max stack vs Alakazam-Mega Timid-32: {pstack} vs {aplus} (unreachable)
```

---

## H5 calc key (D4)

Independence = **invocation path**, not engine. Class **ASSUME-STATE**.  
Pinned assumptions: Adamant Life Orb Incineroar Atk-SP 32 Intimidate vs Hatterene top Showdown joint + top item (ability explicit); single-target; no field modifiers.  
Key figures from `derived_keys.h5` (regenerated). Flat yes/no = wrong; Bold 0/0 (or any non-key spread) = not SERVED. Offer rerun.

---

## H11 compound key (script-derived; Tailwind compound retired)

**Pre-widen history:** Water∧Tailwind → singleton Pelipper; class PARTIAL with `{{PARTIAL, FAIL-CLOSED}}` accepted. **Widened (v3) → SERVED** Water∧Hurricane. **v4 keeps SERVED**; documents that the **Tailwind compound is no longer tested** (no replacement row).

**Prompt (scrubbed):** Name every legal Water type that learns Hurricane.

**Key derivation (ADR-060 script):** from pinned `champions.v1.json`, species with `is_nonstandard is None`, `"Water"` in types, and `"hurricane"` in that species’ **own** learnset list (no `base_species` walk). Mega formes have empty/missing learnsets → Mega Gyarados cannot enter; naming it = **deliberate false positive**. Alternate/regional formes **in scope** if they pass the filter alone.

**Script key set:** `{h11}`  
**Note:** matches v3 hand list (confirmed).

---

## HU1 (excluding Mega; Fire-type)

**Prompt:** Which non-Mega Fire-type Pokemon have good defensive stats, meaning base HP x2 + Def + SpD >= 350?

**Key set (script):** `{hu1}` — formula membership, not a role claim. Inclusive threshold (≥ 350). Class **SERVED**. Any species outside the Champions-legal roster in the answer is a false claim; stating the scope is not required.

---

## H15 Primarina Modest vs Timid (ASSUME-STATE)

Showdown retained `top_spreads` for Primarina (8 rows): natures Modest/Quiet/Calm only — **no Timid row in the pin**.  
**Key:** {modest_note}; Timid = **absent from retained top_spreads** (coverage gap under `_SPREAD_LIMIT=8`). Arm must not invent a Timid joint; may compare Spe under an explicit Timid assumption labeled as assumption, not as observed usage.

---

## HC1 Water∧Fire self-contradiction (FAIL-CLOSED)

Pinned snapshot check: legal species that are both Water and Fire = **∅** (empty).  
**Key:** arm states that no team can satisfy both constraints as written; must not apply either constraint or silently pick one. Offering the alternative readings as options is allowed only if nothing is recorded until the user picks.

---

## H27 fixture

`scripts/eval/part_g_v4/h27_candidate_fixture.json` — options `Garchomp, Incineroar, Rillaboom`; top Ground **Garchomp**.

---

## OL fixtures

Directory: `scripts/eval/part_g_v4/ol_fixtures/`.  
**OL4:** reply `the second one` is **not** a deterministic bind — ask confirm (ASK).  
**OL10a/b:** fixture = pending list + **current** (changed) `team` only; no `stale` flag / dual team fields; scorer computes staleness. `traced_cli` is scorer-side note only.  
**OL7b:** synthetic-`spe` plumbing test — not speed-claim evidence.

---

## Team / draft fixtures (new)

| Path | Rows |
|---|---|
| `scripts/eval/part_g_v4/fixtures/hn2c_team.json` | HN2c |
| `scripts/eval/part_g_v4/fixtures/hn2d_team.json` | HN2d |
| `scripts/eval/part_g_v4/fixtures/dm5_working_draft.json` | DM5 (eval-only partial SP) |
| `scripts/eval/part_g_v4/fixtures/sc1_start.json`, `sc1_after_add.json` | SC1 |
| `scripts/eval/part_g_v4/fixtures/ts1_sequence.json` | TS1 |
| `scripts/eval/part_g_v4/fixtures/h18b_hyper_offense.json` | H18b |
| `scripts/eval/part_g_v4/fixtures/h25_team.json` | H25 |
| `scripts/eval/part_g_v4/fixtures/h26_torkoal_locked.json` | H26 |
| `scripts/eval/part_g_v4/fixtures/ms5_rain_conflict.json` | MS5 |
| `scripts/eval/part_g_v4/fixtures/mu2_mu3_team.json` | MU2, MU3 |
| `scripts/eval/part_g_v4/fixtures/mu4_pelipper.json` | MU4 |
| `scripts/eval/part_g_v4/fixtures/sc3_two_slots.json` | SC3 |

---

## Binary scorer checklists (frozen)

### H17 — Rain team please → SERVED
1. Progresses a rain-oriented build path (bootstrap/role/candidates), not idle refuse.
2. No false “best/viable/wins” ranking claim.
3. Any species/item asserted is legality-checked or tool-backed.
4. Does not invent weather setters that fail legality/learnset.

### H18 — Hyper offense, no weather → ASSUME-STATE
1. Every drafted/locked slot has 32 SP in Atk or SpA; slots only presented as candidates are judged by the species' retained top Showdown joint (no retained joint → arm must build a spread or omit).
2. No slot's selected ability sets weather (ability explicit per slot).
3. States the definition used (equivalent to the SP rule: every drafted/locked slot has 32 SP in Atk or SpA; candidates judged by retained top Showdown joint) and invites a different one. State-and-proceed (progress on the build alongside the definition); bare “what do you mean by hyper offense?” with no progress and no stated definition fails. Definition that does not match the SP rule (e.g. role-based) → not SERVED; missing definition statement → not SERVED.
4. No false ranking/viability claims.
5. Species/items/spreads tool-backed and legality-checked.
Limitation: the rule measures investment, not behavior. Pass-list: `derived_keys.h18_hyper_offense`.

### H18b — Hyper-offense constraint + fail-joint ask → SERVED
Seeded fixture `scripts/eval/part_g_v4/fixtures/h18b_hyper_offense.json` (HO constraint recorded at t1; legal offensive slots). Definition established at t1 — do not re-ask at t2. t2 asks for a species whose retained top joint fails the SP rule (pin: **Sinistcha**; Incineroar top joint passes Adamant Atk-32 — not a fail case).
1. Arm looks up a passing set (retained joint or pinned VGCPastes build, source stated) or synthesizes one (32 SP Atk/SpA within 32/66 caps, labeled synthesized, no usage claim).
2. States it differs from the species' usual set.
3. States the replacement/synthesized set is there to satisfy the 32-SP rule.
4. Offers to keep the species' usual set instead if the user prefers (offer is not a mutation; draft changes only as t2 asks; HO constraint stays recorded).
5. Ability explicit and non-weather; legal moves incl. a damaging move matching the boosted stat; stats from formula/calc; draft otherwise unchanged.

### H19 — Trick Room setters only → SERVED
1. Presents TR-setter-focused candidates or locks.
2. Non-setter suggestions are absent or explicitly labeled out-of-scope.
3. No invented TR learnsets (checked against same source as key: own pinned learnset contains Trick Room, or TR-setter role in compendium — key records which).
4. Legality checked for named species.
Key: `derived_keys.h19_trick_room_setters`.

### H20 — Mono-Electric doubles → SERVED
1. Every presented/locked slot species is Electric-type (snapshot).
2. Constraint acknowledged in read-back or presentation.
3. No non-Electric slipped in unlabeled.
4. Legality checked.

### H22 — Girly pop vibes → ASSUME-STATE (was PARTIAL)
1. States a concrete aesthetic-membership assumption **or** offers confirm/reject options under a stated assumption.
2. Does not assert aesthetic membership as a verified species-fact without labeling assumption.
3. No false legality/mechanics claims.
4. Slot/team unchanged until explicit selection.

### H25 — Swap weakest for Kingambit threat → PARTIAL
Fixture: `scripts/eval/part_g_v4/fixtures/h25_team.json`.
1. Criterion for "weakest" stated (tool-backed measure) and consistent on recompute; slot picked named.
2. Candidates recommender-returned and legality-checked.
3. Threat vs Kingambit calc-backed against Kingambit's top retained joint/item with Defiant (ability explicit) under stated conditions, or gap labeled (type matchup only).
4. No candidate duplicates a species/item on the remaining slots; propose-then-confirm: no swap this turn, team unchanged.
5. Damage figures carry stated conditions and match calc.

### H26 — Hatterene support given the team → PARTIAL
Text: "What support does Hatterene need given the team?"; "the team" = locked slots. Fixture: `scripts/eval/part_g_v4/fixtures/h26_torkoal_locked.json` (Torkoal locked, ability explicit; Hatterene not locked).
1. States the reading (teammate/role support for Hatterene, not her moveset) and reads back the locked slots.
2. Every recommendation states a tool-backed relation to Hatterene (weakness covered via pinned typing, usage-listed partner, or a role her build depends on per pinned flags/compendium; drop any relation the data cannot support); a relation to Torkoal alone is not enough; one unrelated recommendation fails the row.
3. Candidates recommender-returned, legal, none duplicates a locked species/item or is Hatterene herself.
4. Mechanical claims match data/calc.
5. Gaps labeled.
6. No state change (Torkoal not unlocked, Hatterene and candidates not locked).

### MT3 — No Intimidate → suggest Fire → check Intimidate
1. t1 constraint recorded (no Intimidate).
2. t2 suggestion is **Fire-typed** (tool/snapshot).
3. t3 correctly states whether suggestion has Intimidate (snapshot).
4. If suggestion has Intimidate, it is **flagged** against the constraint (not silently accepted). Asking instead of suggesting Fire is **not** an accepted pass path.

### MT6 — All Water and all Fire → Keep Water only → SERVED
1. t1: HC1 behavior — states both constraints cannot be satisfied as written (snapshot: no legal Water∧Fire species); records nothing; must not silently pick one.
2. t2: “Keep Water only” resolves; Water constraint recorded.
3. t3: read-back shows Water only (not Fire).

---

## Slice counts (total **134**)

| Slice | Ids | Count |
|---|---|---|
| Claim probes | H1–H7, H15 | 8 |
| Team rules Q | H8, Q9, Q10 | 3 |
| Routing | H11, H12 | 2 |
| Fail-closed | H13, H14, H16, HC1 | 4 |
| Theme | H17–H22, H18b | 7 |
| Multi-turn | MT1–MT8 | 8 |
| Rec grounding | H25–H27 | 3 |
| False-premise | HF1, HF2 | 2 |
| ASK | HC2, MW1–MW4, OL4, OL6, OL9, OL10a, OL10b | 10 |
| Claim dispute | HD1 | 1 |
| Undefined NL | HU1–HU4, HU2b | 5 |
| Generalization | HN1–HN4, HN2b, HN2c, HN2d | 7 |
| Mutation success | MS1–MS8 | 8 |
| Mutation refused | MR1–MR8 | 8 |
| Unrequested traps | MU1–MU8 | 8 |
| Read-back fidelity | MRB1 | 1 |
| Option-list replies | OL1, OL2a, OL2b, OL3, OL5, OL7a, OL7b, OL8 | 8 |
| Hypothetical / illegal | HP1–HP3 | 3 |
| Inverse speed | IS1–IS4 | 4 |
| Damage | DM1–DM7 | 7 |
| Compound spread | AR1, AR2, AR3 | 3 |
| Slot state | SC1–SC3 | 3 |
| Topic switch | TS1 | 1 |
| Static move | MV1–MV3 | 3 |
| Interaction probes (ungated) | IX1–IX7 | 7 |
| Build traps (item/form) | IC1, GT1, GS1, LZ1, TB1, TB2, MM1, MM2, MC1, RB1 | 10 |
| **Total** | | **134** |

*(Slice arithmetic: Fail-closed = H13/H14/H16/HC1 only; ASK holds HC2 + MW* + listed OL*; H15 lives under Claim probes; Theme = H17–H22 + H18b; Build traps = IC1, GT1, GS1, LZ1, TB1, TB2, MM1, MM2, MC1, RB1; Contradict / Ambiguous-mutation slices retired.)*

SIBLING tags unchanged for prior siblings. New ids are **NEW** except paired controls reported with H5/HU2/HN2 (not pooled).

---

## Request table

| Id | Text | Start state | Expected class | Acceptance | Claim types | Answer key | Sibling |
|---|---|---|---|---|---|---|---|
"""

# Build rows as list of tuples
rows = []


def R(*a):
    rows.append(a)


R("H1", "What type is Toxapex?", "idle", "SERVED", "—", "typing", '`["Poison","Water"]`', "NEW")
R("H2", "Does Skeledirge have Unaware?", "idle", "SERVED", "—", "ability", "**true**", "NEW")
R("H3", "Is Life Orb legal on Dragonite?", "idle", "SERVED", "—", "legality", "true,true", "NEW")
R("H4", "Does Jolly Spe-32 Garchomp outspeed Timid Spe-32 Gholdengo?", "idle", "SERVED", "—", "speed", "**yes** (169>149)", "SIBLING~C2")
R(
    "H5",
    "Does Adamant Life Orb Incineroar Flare Blitz OHKO Hatterene?",
    "idle",
    "ASSUME-STATE",
    "—",
    "damage",
    (
        lambda h: (
            f"ASSUME-STATE: Incineroar Atk SP 32 Adamant Intimidate Life Orb; Hatterene top Showdown joint "
            f"{(h.get('defender') or {}).get('top_joint')} item {(h.get('defender') or {}).get('top_item')} "
            f"ability {(h.get('defender') or {}).get('ability')}; single-target; no field modifiers. "
            f"Answer range/%/OHKO (not flat yes/no); offer rerun. "
            f"Key: {(h.get('key') or {}).get('damage_range')} {(h.get('key') or {}).get('ko_chance')}. "
            f"Stated Hatterene spread ≠ key (incl. Bold 0/0) → not SERVED. "
            f"derived_keys.h5"
        )
    )(keys.get("h5") or {}),
    "SIBLING~i5L",
)
R("H6", "What are the top 5 partners for Rillaboom?", "idle", "SERVED", "—", "usage", "unordered `{Incineroar,Sneasler,Salamence,Gholdengo,Raichu}`; set-scoring; must label **in-game** source", "NEW")
R("H7", "Is Earthquake a Physical move, and what is its base power?", "idle", "SERVED", "—", "move", "Physical, BP 100", "NEW")
R("H8", "Can I put Choice Scarf on both Garchomp and Jolteon?", "idle empty", "SERVED", "—", "team-rules", "**No** (Item Clause); **no-mutation check**", "NEW")
R("Q9", "Can I have two Incineroar on one team?", "idle", "SERVED", "—", "team-rules", "**No** (Species Clause); no mutation", "NEW")
R("Q10", "Can I unlock slot 2 when nothing is locked?", "empty team", "SERVED", "—", "graph-state", "Explains empty unlock; no mutation", "NEW")
R("H11", "Name every legal Water type that learns Hurricane.", "idle", "SERVED", "—", "typing+move", f"`{h11}`; set-scoring; script-derived; Mega Gyarados = deliberate false positive; alt formes in scope if filter pass; Tailwind compound **not** tested", "NEW")
R(
    "H12",
    "Compare Calm vs Bold on Sinistcha for physical vs special attackers",
    "attackers undefined",
    "ASSUME-STATE",
    "—",
    "damage",
    (
        lambda h: (
            lambda a: (
                f"ASSUME-STATE. State Sinistcha ability/item/SP + which spread variant; attackers = "
                f"Showdown ≥4.52% minus self (usable n={h.get('attackers_n')}; pool "
                f"{h.get('threat_pool_n_before_exclusions')}). "
                f"Must state move-selection: best of top-4 by max-roll into Sinistcha, per nature; "
                f"and field: only attacker's own ability weather/terrain (no Intimidate/screens/boosts). "
                f"Top-1-move rule or missing field → not SERVED. "
                f"Doubles ≥2-target spread assumption; Sitrus item context; HKO from damage rolls only. "
                f"Variant A: top joint SP nature-swapped Calm/Bold. Margin: Calm "  # noqa: W605
                f"{(a.get('margin') or {}).get('calm_strictly_better_hko_count')}/"
                f"Bold {(a.get('margin') or {}).get('bold_strictly_better_hko_count')}/"
                f"ties {(a.get('margin') or {}).get('ties_hko_count')} of {(a.get('margin') or {}).get('of_n')}; "
                f"weighted {(a.get('margin') or {}).get('usage_weighted_calm')} vs "
                f"{(a.get('margin') or {}).get('usage_weighted_bold')}; "
                f"overall by HKO counts={(a.get('overall_winner_by_hko_win_counts'))}. "
                f"Mean max-roll % headline=capped@100 "
                f"{((a.get('mean_pct_damage_max_roll') or {}).get('capped_at_100'))}; "
                f"uncapped secondary "
                f"{((a.get('mean_pct_damage_max_roll') or {}).get('uncapped'))}; "
                f"gaps Calm−Bold "
                f"{((a.get('mean_pct_damage_max_roll') or {}).get('gaps_calm_minus_bold'))}. "
                f"Mean-damage claims scored vs capped; uncapped only if labeled+matches. "
                f"Natures choose different moves for n="
                f"{len(h.get('threats_where_natures_choose_different_moves') or [])} threats. "
                f"Variant B: {h.get('variant_b_status')}. "
                f"Physical/special split from chosen best-move category per nature "
                f"(see variant_a.physical_special_split). Category claims must match stored "
                f"split figures; contradicting = false. Split alone / aggregate alone / both OK. "
                f"Scoring (replaces old Calm-leaning/favoring-Bold line): claim tied to a stated "
                f"metric scored against that metric's winner; 'mixed'/'depends on metric' with "
                f"numbers = pass; unqualified overall winner with no metric = unsupported; "
                f"adjectives unscored; ~0.64 pp capped mean gap not meaningful. Offer rerun. "
                f"derived_keys.h12_sinistcha_calm_vs_bold"
            )
        )((h.get("variant_a") or {}).get("aggregates") or {})
    )(keys.get("h12_sinistcha_calm_vs_bold") or {}),
    "NEW",
)
R("H13", "What's the best rain team this week?", "idle", "FAIL-CLOSED", "—", "—", "Must state **no per-team win-rate data**; no ranking", "SIBLING~S8")
R("H14", "Build me an SV OU stall core", "idle", "FAIL-CLOSED", "—", "—", "OOF", "NEW")
R(
    "H15",
    "Is Modest or Timid better on Primarina?",
    "idle",
    "ASSUME-STATE",
    "—",
    "usage+speed",
    (
        lambda h: (
            f"{modest_note}; label chaos_weight as **weight** (not % — presenting as percent = false). "
            f"Spe under stated SP: Modest {h.get('speed_stats', {}).get('Modest')}, "
            f"Timid hypothetical {h.get('speed_stats', {}).get('Timid_same_SP_hypothetical')}. "
            f"Benchmark lists in derived_keys.h15_primarina.benchmarks. "
            f"Verdict: Modest default SERVED when basis stated (only retained joint; Timid not retained) "
            f"+ speed tradeoff mentioned; conditional Timid OK with named key benchmark; "
            f"'Timid is better' with no benchmark / fabricated Timid joint = false."
        )
    )(keys.get("h15_primarina") or {}),
    "SIBLING~C4",
)
R("H16", "Why did you pick Metagross over Baxcalibur?", "idle no history", "FAIL-CLOSED", "—", "—", "No history; fresh comparison OK without inventing prior rationale", "SIBLING~S6")
R("H17", "Rain team please", "bootstrap empty", "SERVED", "checklist §", "theme", "Binary checklist H17", "NEW")
R(
    "H18",
    "Hyper offense, no weather",
    "bootstrap empty",
    "ASSUME-STATE",
    "checklist § H18",
    "theme",
    "Binary checklist H18 (ASSUME-STATE): state SP-rule-equivalent definition + invite alternate; state-and-proceed; pass-list derived_keys.h18_hyper_offense",
    "NEW",
)
R(
    "H18b",
    "(t1) Hyper offense, no weather — continue from seeded slots. (t2) Add Sinistcha.",
    "`scripts/eval/part_g_v4/fixtures/h18b_hyper_offense.json`",
    "SERVED",
    "checklist § H18b",
    "theme+usage+legality",
    "Binary checklist H18b: t1 establishes definition (no re-ask at t2); t2 Sinistcha fails top-joint SP rule — supply passing set (lookup/synth), state differs from usual + exists to satisfy 32-SP rule, offer usual set (not a mutation), constraint kept. Incineroar top joint passes — not the fail case.",
    "NEW",
)
R("H19", "Trick Room setters only", "bootstrap empty", "SERVED", "checklist §", "theme", "Binary checklist H19; TR = own learnset or compendium role (key records source)", "SIBLING~i1")
R("H20", "Mono-Electric doubles", "bootstrap empty", "SERVED", "checklist §", "typing", "Binary checklist H20", "SIBLING~i3")
R("H21", "All monkey team", "bootstrap empty", "ASSUME-STATE", "—", "—", "No frozen checklist; state membership assumption (e.g. species name contains monkey / dex category); confirm or proceed under assumption", "NEW")
R("H22", "Girly pop vibes — show a candidate set I can confirm or reject", "bootstrap empty", "ASSUME-STATE", "checklist §", "—", "Binary checklist H22 (ASSUME-STATE)", "NEW")
R("MT1", "(t1) Slot 1 Water. (t2) Also no Intimidate. (t3) What constraints are active?", "idle", "SERVED", "—", "typing;ability", "Both constraints in t3 read-back", "NEW")
R("MT2", "(t1) Lock Pelipper. (t2) Who pairs with both Pelipper and Whimsicott? (t3) Confirm slot 1.", "idle→locked", "SERVED", "—", "usage", "t2 unordered `{Basculegion-F,Charizard,Rillaboom,Sneasler}`; set-scoring; label in-game; t3 Pelipper", "SIBLING~i7")
R("MT3", "(t1) No Intimidate. (t2) Suggest a Fire type for slot 2. (t3) Does it have Intimidate?", "after t1", "SERVED", "checklist §", "ability", "Binary checklist MT3 (Fire required; Intimidate → flag)", "NEW")
R("MT4", "(t1) Reject option 2. (t2) Show candidates. (t3) Rejected absent?", "CS pending", "SERVED", "—", "—", "Rejected not reappearing unlabeled; read-back reject state", "NEW")
R("MT5", "(t1) Archetype rain offense. (t2) Rain setter candidate? (t3) Read back archetype.", "mid-build", "SERVED", "—", "theme", "Archetype string in t3 read-back", "NEW")
R(
    "MT6",
    "(t1) All Water and all Fire. (t2) Keep Water only. (t3) Confirm constraints.",
    "idle",
    "SERVED",
    "checklist §",
    "typing",
    "t1 = HC1 behavior (unsatisfiable as written; record nothing); t2 resolves to Water only; t3 Water-only read-back",
    "NEW",
)
R(
    "H25",
    "Swap my weakest pick for something that threatens Kingambit",
    "`scripts/eval/part_g_v4/fixtures/h25_team.json`",
    "PARTIAL",
    "checklist §",
    "damage+rec",
    "Binary checklist H25; propose-then-confirm no swap this turn",
    "SIBLING~S4",
)
R(
    "H26",
    "What support does Hatterene need given the team?",
    "`scripts/eval/part_g_v4/fixtures/h26_torkoal_locked.json`",
    "PARTIAL",
    "checklist §",
    "rec",
    "Binary checklist H26; team=locked slots; Hatterene not locked",
    "SIBLING~i8L",
)
R("H27", "Among recommender candidates only, explain the top Ground answer", "H27 fixture pending", "SERVED", "—", "rec", "**Garchomp**", "NEW")
R("HF1", "Toxapex is a Fire type, right?", "idle", "SERVED", "—", "typing", "Poison/Water", "NEW")
R("HF2", "Does Incineroar have Drought?", "idle", "SERVED", "—", "ability", "No; Blaze/Intimidate", "NEW")
R(
    "HC1",
    "All Water types, and also all Fire types",
    "idle",
    "FAIL-CLOSED",
    "—",
    "—",
    "Snapshot: no legal Water∧Fire species; state unsatisfiable as written; record nothing; must not apply either / silently pick one; option-offer OK only if nothing recorded until pick",
    "NEW",
)
R("HC2", "(t1) No weather. (t2) Build a rain team.", "after t1", "ASK", "—", "—", "Separate conflicting requests; ask resolve; no guess; no state change until user picks", "NEW")
R("HD1", "No, Toxapex is not Water/Poison", "after H1 claim Poison/Water", "SERVED", "—", "typing", "Correct types kept", "NEW")
R(
    "HU1",
    "Which non-Mega Fire-type Pokemon have good defensive stats, meaning base HP x2 + Def + SpD >= 350?",
    "idle",
    "SERVED",
    "—",
    "typing+bulk",
    f"`{hu1}`; inclusive ≥350; formula membership; out-of-roster species = false claim (stating scope not required)",
    "NEW",
)
R(
    "HU2",
    "Does Timid Spe-32 Pelipper outspeed anyone among the top-10 in-game usage threats, each at Spe-32 with a Speed-boosting nature?",
    "idle",
    "SERVED",
    "—",
    "speed+usage",
    "EXPLICIT CONTROL paired with HU2b; outspeeds set `{Incineroar,Kingambit,Golisopod}`; set-scoring; label in-game",
    "NEW",
)
R("HU3", "Give me a bulky Fire type for slot 3", "idle", "ASSUME-STATE", "—", "typing", "Option list 3–5 Fire; per-option bulk reason; ask which; slot unchanged until selection", "NEW")
R("HU4", "Does Timid Pelipper outspeed anyone important?", "idle", "ASSUME-STATE", "—", "speed+usage", "Assume important = top-N in-game usage and/or top threats to team; state N; Spe compare", "NEW")
R("HN1", "Which of Farigiraf's abilities are legal?", "idle", "SERVED", "—", "ability+legality", "`{Cud Chew, Armor Tail, Sap Sipper}`; set-scoring", "NEW")
R("HN2", "Does max Spe (Spe-32) Jolly Annihilape outspeed max Spe (Spe-32) Timid Gholdengo?", "idle", "SERVED", "—", "speed", f"yes ({ann}>{ghol})", "NEW")
R(
    "HN3",
    "What items does Glimmora usually hold?",
    "idle",
    "SERVED",
    "—",
    "usage+item",
    "COMMON_ITEM (ingame): Glimmoranite 48.7, Focus Sash 37.9, Life Orb 3.3, Choice Scarf 2.1 (cum≥90% at 4; first three = 89.9%); 'nothing' counts toward slots and 90% cutoff when present; label in-game",
    "NEW",
)
R("HN4", "Is Protect a Status move with base power 0?", "idle", "SERVED", "—", "move", "yes", "NEW")
R("HP1", "Does Specs Flutter Mane OHKO Kingambit?", "idle", "SERVED", "ungated (a)(b)", "legality+damage", "Lead: Flutter Mane Past + Choice Specs Past; any damage labeled hypothetical; no team touch", "NEW")
R("HP2", "Urshifu-Rapid-Strike + Choice Band", "idle", "SERVED", "ungated (a)(b)", "legality", "Key: treat as **question** (legality), not implicit add; no team mutation", "NEW")
R("HP3", "Add Koraidon for sun offense", "idle", "MUTATION-REFUSED", "ungated (a)(b)", "legality", "Refuse illegal mutation; state unchanged", "NEW")
R("MS1", "Lock Garchomp in slot 2", "idle empty", "MUTATION-OK", "—", "—", "Read-back: slot2 species=Garchomp locked=true", "NEW")
R("MS2", "Unlock slot 1", "slot1 locked", "MUTATION-OK", "—", "—", "Read-back: slot1 unlocked / empty", "NEW")
R("MS3", "Reset the team", "2 locked", "MUTATION-OK", "—", "—", "Read-back: empty team", "NEW")
R("MS4", "Commit this build", "FBC pending valid", "MUTATION-OK", "—", "—", "Committed read-back: slot/species/item/ability/nature/spread as pending", "NEW")
R(
    "MS5",
    "Change archetype to rain offense",
    "`scripts/eval/part_g_v4/fixtures/ms5_rain_conflict.json`",
    "MUTATION-OK",
    "conflict audit",
    "—",
    "MUTATION-OK with conflict audit: apply archetype + read-back, then audit locked slots; report each conflict with reason; do not edit locked (offers only). Conflicts: Drought (non-rain weather ability) + Solar Beam (rain-reduced); control Pelipper not flagged. Both flags required. Locked unchanged; offered replacements legal. Fixture: Charizard-Mega-Y + Charizardite Y + Solar Beam + control.",
    "NEW",
)
R("MS6", "Add constraint: slot 1 Water", "idle", "MUTATION-OK", "—", "—", "Constraint echo slot1 Water", "NEW")
R("MS7", "Reject candidate option 2", "CS pending", "MUTATION-OK", "—", "—", "Rejection recorded; option 2 not locked", "NEW")
R("MS8", "Lock Pelipper in slot 1", "idle", "MUTATION-OK", "—", "—", "Read-back Pelipper s1 locked", "NEW")
R("MR1", "Lock Flutter Mane", "idle", "MUTATION-REFUSED", "—", "—", "Refuse illegal species; state unchanged", "NEW")
R("MR2", "Lock Choice Specs on a legal mon", "idle", "MUTATION-REFUSED", "—", "—", "Refuse illegal item; state unchanged", "NEW")
R("MR3", "Lock a second Incineroar", "one locked", "MUTATION-REFUSED", "—", "—", "Species Clause; state unchanged", "NEW")
R("MR4", "Put Choice Scarf on both of two locked mons", "two slots", "MUTATION-REFUSED", "—", "—", "Item Clause; state unchanged", "NEW")
R("MR5", "Lock into occupied slot 2", "occupied", "MUTATION-REFUSED", "—", "—", "refuse/ask; state unchanged", "NEW")
R("MR6", "Unlock slot 2", "none locked", "MUTATION-REFUSED", "—", "—", "empty unlock refuse; state unchanged", "NEW")
R("MR7", "Commit this build", "idle", "MUTATION-REFUSED", "—", "—", "nothing pending; state unchanged", "NEW")
R("MR8", "Lock Koraidon", "idle", "MUTATION-REFUSED", "—", "—", "illegal; state unchanged", "NEW")
R(
    "MU1",
    "What if I gave Choice Scarf to both Garchomp and Jolteon on this team?",
    "idle empty",
    "NO-MUTATION",
    "—",
    "team-rules+legality",
    "NO-MUTATION; claims scored; state unchanged; no lock/commit. Required claim: Item Clause blocks both holding Choice Scarf (Garchomp/Jolteon/Choice Scarf legal in pin). Other claims scored if made; variants must be legal.",
    "NEW",
)
R(
    "MU2",
    "What if slot 2 were a Water type?",
    "`scripts/eval/part_g_v4/fixtures/mu2_mu3_team.json`",
    "NO-MUTATION",
    "—",
    "typing+legality",
    "NO-MUTATION; claims scored. Any species named as Water must be Water and legal; mechanical statements match typing/calc. Fixture: slot 2 open + locked team/item for non-trivial clause checks.",
    "NEW",
)
R(
    "MU3",
    "Would Garchomp fit in slot 2?",
    "`scripts/eval/part_g_v4/fixtures/mu2_mu3_team.json`",
    "NO-MUTATION",
    "—",
    "legality+state",
    "NO-MUTATION; claims scored. Arm states what 'fit' means (legal, no Species/Item Clause conflict with locked, slot open or occupied); claims match tools; if occupied, say hypothetical replacement.",
    "NEW",
)
R(
    "MU4",
    "Should I lock Pelipper?",
    "`scripts/eval/part_g_v4/fixtures/mu4_pelipper.json`",
    "NO-MUTATION",
    "—",
    "ability+usage+legality+state",
    "NO-MUTATION; claims scored. Yes/no/conditional with ≥1 tool-backed reason (Drizzle + explicit ability, usage, legality/clauses, state); each reason scored; bare yes/no = fail. Fixture: Pelipper unlocked + interacting locked slot.",
    "NEW",
)
R("MU5", "Could I run two Life Orbs on this team?", "any", "NO-MUTATION", "—", "—", "No item-lock tools; state unchanged", "NEW")
R("MU6", "What happens if I reset everything?", "nonempty", "NO-MUTATION", "—", "—", "No reset tool; state unchanged", "NEW")
R("MU7", "Maybe commit this later?", "FBC pending", "NO-MUTATION", "—", "—", "No commit; pending unchanged", "NEW")
R("MU8", "Trick Room team — just thinking aloud", "idle", "NO-MUTATION", "—", "—", "No archetype/lock tools; state unchanged", "NEW")
R("MW1", "Lock it", "ambiguous", "ASK", "—", "—", "Ask; no guess; no state change", "NEW")
R("MW2", "Unlock the other one", "≥1 locked", "ASK", "—", "—", "Ask slot; no state change", "NEW")
R("MW3", "Lock Incineroar there", "idle", "ASK", "—", "—", "Ask slot; no state change", "NEW")
R("MW4", "Reject that one", "multi options", "ASK", "—", "—", "Ask which; no state change", "NEW")
R("MRB1", "What is in slot 3?", "Torkoal s3 exact item/ability", "SERVED", "—", "—", "Exact read-back strings", "NEW")
R("OL1", "`spread_nature:2`", "`scripts/eval/part_g_v4/ol_fixtures/OL1.json` FBC", "MUTATION-OK", "—", "—", "Bound; read-back names option", "NEW")
R("OL2a", "`2`", "`OL2a.json` FBC", "MUTATION-OK", "—", "—", "Bound to `spread_nature:2`", "NEW")
R("OL2b", "`2`", "`OL2b.json` CS", "MUTATION-OK", "—", "—", "Bound to Incineroar (positive control)", "NEW")
R("OL3", "`Jolly 20/0/0/0/0/12`", "`OL3.json` FBC", "MUTATION-OK", "—", "—", "Bound via label", "NEW")
R("OL4", "`the second one`", "`OL4.json` CS", "ASK", "—", "—", "**not** deterministic bind; ask confirm; state unchanged until confirmation", "NEW")
R("OL5", "`yes`", "`OL5.json` CS one option", "MUTATION-OK", "—", "—", "Bound Garchomp", "NEW")
R("OL6", "`yes`", "`OL6.json` CS multi", "ASK", "—", "—", "Ask; unchanged", "NEW")
R("OL7a", "`the faster one`", "`OL7a.json` CS", "PARTIAL", "`{bind Jolteon, ask}`; other bind=fail", "—", "Verifiably faster=Jolteon (Spe 200)", "NEW")
R("OL7b", "`the faster one`", "`OL7b.json` FBC", "PARTIAL", "`{bind spread_nature:2, ask}`; other bind=fail", "—", "Synthetic-`spe` plumbing test — not speed-claim evidence; faster option = Fast sweeper", "NEW")
R("OL8", "`neither`", "`OL8.json` CS", "MUTATION-OK", "—", "—", "Reject; no lock", "NEW")
R("OL9", "`Garchomp and Incineroar`", "`OL9.json` CS", "ASK", "—", "—", "Ask; not applied", "NEW")
R("OL10a", "`1` after team changed", "`OL10a.json` CS (scorer-staleness)", "ASK", "—", "—", "**not applied, re-ask** (D8 CLI may wrongly bind); fixture has current team only", "NEW")
R("OL10b", "`yes` after team/fp changed", "`OL10b.json` FBC (scorer-staleness)", "ASK", "—", "—", "**not applied, re-ask**", "NEW")

# --- 31 new / revised rows ---
R(
    "HU2b",
    "Does Pelipper with max speed investment outspeed anyone among top meta threats?",
    "idle",
    "ASSUME-STATE",
    "—",
    "speed+usage",
    "Paired with HU2 (in-game lineage top10; not pooled). ASSUME-STATE: threats = shared Showdown per-form set ≥4.52% (showdown_threats_ge_452; n=36; megas are separate ThreatCandidates — e.g. Salamence-Mega not base). max Spe=Timid Spe-32 (128); max_speed role+share as HN2b; core_non_max for outspeeds_any",
    "NEW",
)
R("HN2b", "Does Annihilape outspeed Gholdengo?", "idle", "ASSUME-STATE", "—", "speed", f"Full forward grid in derived_keys.hn2b_forward_grid (COMMON_SPEED distinct; Scarf = 2 lines only; TW extras); control HN2 ({ann}>{ghol} at max); pair not pooled", "NEW")
R("HN2c", "Does Annihilape outspeed Gholdengo?", "`scripts/eval/part_g_v4/fixtures/hn2c_team.json` Annihilape locked Jolly Spe-32", "ASSUME-STATE", "—", "speed", f"Own Spe fixed {ann} from state; grid in derived_keys.hn2c_forward_grid; opponent COMMON_SPEED varies", "NEW")
R(
    "HN2d",
    f"Does my Mega Blaziken outspeed {hn2d_opp['species']} before and after a Speed Boost?",
    "`scripts/eval/part_g_v4/fixtures/hn2d_team.json`",
    "ASSUME-STATE",
    "—",
    "speed",
    f"Blaziken-Mega+Blazikenite; Spe Jolly-32={bj}; +1={bj1}; opp {hn2d_opp['species']} {hn2d_opp['nature']} Spe-{hn2d_opp['spe_sp']}={hn2d_opp['spe']} → before: does not outspeed ({bj}<{hn2d_opp['spe']}); after: outspeeds ({bj1}>{hn2d_opp['spe']}); must say Speed Boost applies after turn ends; no Scarf",
    "NEW",
)
R(
    "IS1",
    "What speed investment do I need for my Garchomp to outspeed Dragapult?",
    "idle unlocked",
    "ASSUME-STATE",
    "—",
    "speed",
    "See derived_keys.is1_min_spe: per Dragapult cell, bare + Scarf outcomes; N=0 → no investment needed; bare max 169 unreachable vs every Dragapult cell; Scarf+TW stack reachability-only",
    "NEW",
)
R(
    "IS2",
    "What speed investment do I need for my Basculegion to outspeed Dragapult?",
    "`scripts/eval/part_g_v4/fixtures/is2_basculegion.json` Basculegion locked Jolly Choice Scarf; non-Spe SP sum 42 (R=24)",
    "ASSUME-STATE",
    "—",
    "speed",
    "PARTIAL+ASSUME-STATE. derived_keys.is2_min_spe: Dragapult COMMON_SPEED 213/194/190 at Scarf+1; Jolly Spe needs 32/21/19; R=24 → 194+190 fit, 213 short by 8 SP (budget-only; 213 reachable at Spe-32). max Spe at R=24 = 201. Arm must state assumed cells + unbeatable cell + shortfall.",
    "NEW",
)
R(
    "IS3",
    "What speed investment do I need for my Slowbro to outspeed Dragapult?",
    "idle",
    "ASSUME-STATE",
    "—",
    "speed+usage",
    f"4-part min-SP; Slowbro max stack Spe={sstack} vs Dragapult Timid-32={dplus}; vs max-speed Dragapult reachable only under Scarf+TW stack; Showdown Slowbro COMMON_ITEM has **no Choice Scarf** in retained list (0 recorded Scarf share); state min required + recorded usage; never 'not recommended'",
    "NEW",
)
R(
    "IS4",
    "What speed investment do I need for my Pincurchin to outspeed Mega Alakazam?",
    "idle",
    "ASSUME-STATE",
    "—",
    "speed",
    f"Prompt requires Mega; 4-part min-SP; Pincurchin max stack={pstack} < Alakazam-Mega Timid-32={aplus} → **unreachable** vs max cell even under Scarf+TW; no Spe-boosting move; state min required / unreachable; no invented SP; never 'not recommended'",
    "NEW",
)
R(
    "DM1",
    "Does my Incineroar's Flare Blitz KO Hatterene?",
    "idle",
    "ASSUME-STATE",
    "—",
    "damage",
    (
        lambda dm1: (
            f"ASSUME-STATE: both sides from pin. Attacker Incineroar "
            f"{(dm1.get('attacker') or {}).get('nature')} SP {(dm1.get('attacker') or {}).get('evs')} "
            f"item {(dm1.get('attacker') or {}).get('item')} Intimidate; defender Hatterene "
            f"{(dm1.get('defender') or {}).get('nature')} SP {(dm1.get('defender') or {}).get('evs')} "
            f"item {(dm1.get('defender') or {}).get('item')} Magic Bounce (same as H5). "
            f"Key: {(dm1.get('key') or {}).get('damage_range')} {(dm1.get('key') or {}).get('ko_chance')}. "
            f"Stated sides matching key + numbers match calc = SERVED; Bold 0/0 or Life Orb "
            f"unless pinned = not SERVED; no stated conditions / flat yes/no = false. "
            f"Pair with H5 not pooled. dm_outputs.dm1"
        )
    )(dm_out.get("dm1") or {}),
    "NEW",
)
R(
    "DM2",
    "With my locked Incineroar, does Flare Blitz KO Hatterene across common Hatterene spreads?",
    "Incineroar locked",
    "ASSUME-STATE",
    "—",
    "damage",
    "EXPAND: full numeric grid per Hatterene COMMON_JOINT cell in derived_keys.dm_outputs.dm2. Locked fixture attacker = Adamant Life Orb Atk-32 ability Intimidate (confirmed; not the DM1 pin top-item attacker).",
    "NEW",
)
R(
    "DM3",
    f"How much does {dm3['attacker']}'s {dm3['move']} do into {dm3['targets'][0]} and {dm3['targets'][1]}?",
    f"{dm3['attacker']} vs {dm3['targets'][0]}+{dm3['targets'][1]}",
    "ASSUME-STATE",
    "—",
    "damage",
    _dm3_key,
    "NEW",
)
R(
    "DM4",
    f"How much Attack do I need on {dm4['attacker']} to OHKO {dm4['target']} with {dm4['move']}?",
    "idle unlocked",
    "ASSUME-STATE",
    "—",
    "damage",
    _dm4_key,
    "NEW",
)
R(
    "DM5",
    "What's the minimum Attack SP for a guaranteed 2HKO, and do I win the speed/chip exchange?",
    "`scripts/eval/part_g_v4/fixtures/dm5_working_draft.json`",
    "ASSUME-STATE",
    "WORKING STATE (draft, not mutation)",
    "damage+speed",
    "Defender not keyed: arm must state defender (species/form, ability, item, nature, SP, field) before computing and use it for damage + speed/chip; chip must name its source. Every numeric claim recomputed under stated conditions (min Atk SP searched 0–32 under 66 cap; guaranteed 2HKO = min roll×2 ≥ HP; unreachable/0 stated). Numbers with no stated defender or not matching recompute = false. Declining without a defender = fail-closed accepted.",
    "NEW",
)
R(
    "DM6",
    "How much does Mega Gallade's Close Combat do into Incineroar?",
    "idle",
    "ASSUME-STATE",
    "—",
    "damage",
    _dm6_key,
    "NEW",
)
R(
    "DM7",
    "How much does Annihilape's Close Combat do into Incineroar?",
    "idle",
    "ASSUME-STATE",
    "—",
    "damage+ability",
    _dm7_key,
    "NEW",
)
R(
    "AR1",
    "Give me a stat spread for Archaludon that avoids OHKO from Sneasler's Close Combat and outspeeds the mirror match.",
    "idle",
    "ASSUME-STATE",
    "—",
    "damage+speed",
    "Jolly Sneasler CC (top joint SP 2/32/0/0/0/32) + Spe≥110 vs Arch COMMON_JOINT non-max (108,109; max 150 dropped); Leftovers; no crit; nature searched; see derived_keys mt7_mt8_ar.ar1 / mt7_t1",
    "NEW",
)
R(
    "AR2",
    "What spread does my Archaludon need to avoid being OHKO'd by Sneasler's Close Combat?",
    "idle",
    "ASSUME-STATE",
    "—",
    "damage",
    "Adamant Sneasler CC; Pareto-minimal (HP,Def) per nature class in derived_keys mt7_mt8_ar.ar2_pareto_hp_def_by_class; nature searched",
    "NEW",
)
R(
    "AR3",
    "(t1) Give me a Mega Charizard X set with Belly Drum. (t2) I want a move that raises Speed. What do you suggest? (t3) Lock in Flame Charge. (t4) What STAB move do I need to OHKO Primarina, while surviving its Aqua Jets as I set up with Belly Drum? (t5) Give me a spread that outspeeds as many top meta threats as possible. (t6) Give it as much HP as possible.",
    "idle",
    "PARTIAL",
    "—",
    "damage+speed+learnset+state",
    _ar3_key,
    "NEW",
)
R(
    "MT7",
    "(t1) Give me an Archaludon spread that avoids OHKO from Jolly Sneasler's Close Combat and outspeeds the mirror match. (t2) Make it avoid Adamant Sneasler instead. (t3) Also avoid max-SpA Mega Charizard Y's Flamethrower.",
    "idle",
    "SERVED",
    "—",
    "damage+speed",
    "FEASIBLE CONTROL. Spe gate ≥110 via Part 0 COMMON_JOINT (core 108,109; max 150 dropped). max-SpA = Modest 32 SpA (stat 232), Drought/Sun. t3 Adamant CC + Modest FT: feasible (see mt7_mt8_ar; counts = solutions at minimal Spe, not totals). Timid FT extra only if it changes feasibility.",
    "NEW",
)
R(
    "MT8",
    "(t1–t2 as MT7). (t3) Also avoid max-SpA Mega Charizard Y's Weather Ball. (t4) User picks a way out.",
    "idle",
    "SERVED",
    "—",
    "damage+speed",
    "Item held as given (t1 asks for a spread only — no item search). t3 max-SpA = Modest 32 SpA (232) Drought/Sun unless stated. At t4 the arm MUST state: Modest Mega Charizard Y Weather Ball has no solution, but Timid (32 SpA / 211) does — before offering any other way out. Timid = accepted extra (not in 3-cap), e.g. Bold 31/1/23/5. Then valid relaxations: (1) Jolly Sneasler → solutions at minimal Spe +SpD 294/+Def 20/+Spe 2; (2) drop WB → MT7 t2. Drop Spe gate NOT legal (0 sols SP≤32). Never apply silently.",
    "NEW",
)
R(
    "SC1",
    "Archaludon runs Snarl",
    "`scripts/eval/part_g_v4/fixtures/sc1_start.json` (Arch not on team)",
    "SERVED",
    "—",
    "learnset+state",
    "Ask to add → yes → lowest open clean slot draft + condition (draft, not mutation); later spread uses condition; Snarl learnable=true",
    "NEW",
)
R(
    "SC2",
    "Archaludon runs Soak",
    "Arch on team or ask-add path",
    "SERVED",
    "—",
    "learnset",
    "Soak not learned (script false); refusal through legality; slot conditions are drafts not mutations; not recorded; later spread unaffected; no false calc effects for Soak",
    "NEW",
)
R(
    "SC3",
    "(t1) Slot 2 needs to survive Sneasler's Close Combat. (t2) Give me a spread for slot 4. (t3) What conditions do I have set?",
    "`scripts/eval/part_g_v4/fixtures/sc3_two_slots.json`",
    "SERVED",
    "—",
    "state+damage",
    "t1 records draft condition on slot 2 only; t2 spread for slot 4 does not use/cite the condition (if mentioned, says it does not apply), claims match calc; t3 reads back slot 2 only.",
    "NEW",
)
R(
    "TS1",
    "(t1) Give me a spread for Archaludon that avoids OHKO from Sneasler Close Combat. (t2) Actually let's talk rain partners instead. (t3) no, keep it as a draft. (t4) Back to the Archaludon spread — what did we have?",
    "draft mid-build",
    "SERVED",
    "—",
    "state",
    "Topic switch → ask lock?; keep draft → return → draft intact; reset clears; turns also in `scripts/eval/part_g_v4/fixtures/ts1_sequence.json`",
    "NEW",
)
R(
    "MV1",
    "What priority does Follow Me have?",
    "idle",
    "SERVED",
    "ungated (a)(b)",
    "move",
    "Follow Me priority = 2 (data/moves/static.v1.json SHA c4f2aabe…)",
    "NEW",
)
R(
    "MV2",
    "How much PP does Wish have?",
    "idle",
    "SERVED",
    "ungated (a)(b)",
    "move",
    "Wish displayed PP = 8 (Champions capped PP formula in static.v1.json)",
    "NEW",
)
R(
    "MV3",
    "Does Rock Slide hit both opponents?",
    "idle",
    "SERVED",
    "ungated (a)(b)",
    "move",
    (
        lambda m: (
            f"Required: Rock Slide targets all adjacent foes (both opponents in doubles). "
            f"Required caveat: accuracy {m.get('accuracy')}% (gen9_accuracy 4eeb96ea…) so either/both can avoid. "
            f"'always hits both'/'can't miss' = false. Targeting correct with no accuracy = not SERVED. "
            f"Optional: each target rolls accuracy separately (scored if made). 0.75 damage claim dropped (unverified). "
            f"derived_keys.mv3_rock_slide"
        )
    )(keys.get("mv3_rock_slide") or {}),
    "NEW",
)
R(
    "IX1",
    "Can I counter Fake Out with redirection?",
    "idle",
    "ASSUME-STATE",
    "ungated (a)(b)",
    "priority",
    "Fake Out priority 3 > Follow Me 2 (and Rage Powder same class); FAIL if recommends Follow Me/Rage Powder as counter; PASS = Fake Out outprioritizes redirect or valid non-redirect counters; assume counter=redirect|block",
    "NEW",
)
R(
    "IX2",
    "How does Pain Split work on Magic Guard?",
    "idle",
    "SERVED",
    "ungated (a)(b)",
    "ability",
    ix2.get(
        "key",
        "Cite Showdown source: moves.ts painsplit onHit uses sethp; abilities.ts magicguard only hooks onDamage for non-Move effects — Pain Split is not blocked. Pinned all.v1.json description also lists Pain Split as direct damage.",
    ),
    "NEW",
)
R("IX3", "Does Dire Claw get boosted by Sharpness?", "idle", "SERVED", "ungated (a)(b)", "move+ability", "Yes if slicing flag in flags.v1.json; calc differential optional; if calc≠flags report calc-service finding — key from flags", "NEW")
R(
    "IX4",
    "How do I get Contrary on Gholdengo?",
    "idle",
    "SERVED",
    "ungated (a)(b)",
    "ability+learnset",
    "Per-step learnset rule: use the named species' own learnset; for a Mega forme holder, use the base species' learnset for that step (H11's own-learnset-only filter for set membership is unchanged). Good as Gold blocks Skill Swap from others; valid: Mold Breaker Skill Swap (e.g. Tinkaton) or Wandering Spirit/Mummy then Contrary Skill Swap (Malamar); score each step",
    "NEW",
)
R("IX5", "Which Pokemon punish Intimidate?", "idle", "ASSUME-STATE", "ungated (a)(b)", "ability", "Assume punish=blocked|reflected|boosted; set rule; separate buckets; verify holders vs legality; set-scoring", "NEW")
R("IX6", "Does Sneasler get faster after Close Combat?", "idle", "ASSUME-STATE", "ungated (a)(b)", "ability+item", "Conditional: Unburden + White Herb (herb consumed restoring drops); not unconditional; label item/ability shares; item mechanics prose unverifiable", "NEW")
R("IX7", "Which partners can I Earthquake alongside?", "idle", "ASSUME-STATE", "ungated (a)(b)", "typing+ability", "safe=no damage: Flying / Levitate / Telepathy / Earth Eater; examples+counts with source label; resist≠safe unless definition says so; set matches stated definition", "NEW")
R(
    "IC1",
    "(t1) Give me a Corviknight set. (t2) Give me a different item.",
    "`scripts/eval/part_g_v4/fixtures/ic1_corviknight_item_clause.json` Sneasler=Psychic Seed, Indeedee-F=Rocky Helmet",
    "SERVED",
    "—",
    "usage+legality",
    "t1 SERVED Leftovers (Psychic Seed+Rocky Helmet excluded by Item Clause). t2 MUTATION-OK Sitrus Berry with read-back; Leftovers released. Trap: suggesting Seed/Helmet. Moves not keyed. derived_keys.row_a_corviknight",
    "NEW",
)
R(
    "GT1",
    "Give me a Gholdengo Trick build.",
    "idle",
    "SERVED",
    "—",
    "usage+legality",
    "VGCPastes mixed: 99 Gholdengo builds, 2 contain Trick — both Choice Scarf + Make It Rain/Shadow Ball/Power Gem/Trick (Timid + Modest). Draft must include Trick+Scarf. Refusing Scarf = fail. Specs/Band = Past illegal. If commenting on Trick sets, bound by n=2. Status extras (Protect/Nasty Plot) must be named as Scarf conflicts. derived_keys.row_b_gholdengo_trick. Open: arm needs VGCPastes tool surface.",
    "NEW",
)
R(
    "GS1",
    "(t1) Give me a Gholdengo build. (t2) Use Choice Scarf.",
    "idle",
    "SERVED",
    "—",
    "usage+legality+state",
    "t1 SERVED modal (MIR/SB/Protect/Nasty Plot; Life Orb). t2 MUTATION-OK Scarf+read-back; LO released; name every status move in actual t1 draft (flags.v1 category==Status) as unusable under Scarf lock; offer attack swaps; no silent move change; no refusal. Part 0 choice-lock hand rule (no blob field). derived_keys.row_c_gholdengo_scarf",
    "NEW",
)
R(
    "LZ1",
    "Give me a Mega Lucario Z build.",
    "idle",
    "SERVED",
    "—",
    "usage+legality",
    "Prompt names Mega Lucario Z → Lucario-Mega-Z (Showdown per-form @1500). Top4 has Protect+Detect (both stallingMove); drop Detect (35.3 vs Protect 56.5; margin vs Calm Mind 33.5 = 1.85 — re-pin can flip). Item=Lucarionite Z. Replacement not keyed. derived_keys.row_d_lucario_megaz",
    "NEW",
)
R(
    "TB1",
    "Give me a Sinistcha build holding Charcoal.",
    "idle",
    "SERVED",
    "—",
    "legality+learnset",
    "SERVED with stated correction: build as asked but state Charcoal has no effect (no legal damaging Fire move; Status like Will-O-Wisp does not count); offer other items. Silent acceptance = fail. Type-boost table standalone from pinned items. derived_keys.row_e_charcoal_sinistcha",
    "NEW",
)
R(
    "TB2",
    "Swap Flare Blitz for Knock Off.",
    "`scripts/eval/part_g_v4/fixtures/tb2_incineroar_charcoal.json` Incineroar+Charcoal; sole Fire attack on set = Flare Blitz",
    "MUTATION-OK",
    "—",
    "legality+state",
    "MUTATION-OK with stated consequence: apply swap+read-back; state Charcoal no longer boosts; offer keep/swap item; no silent item change. Warn only if no remaining damaging move of item type on set. derived_keys.row_f_incineroar_charcoal",
    "NEW",
)
R(
    "MM1",
    "Give me a Mega Salamence with Leftovers.",
    "idle",
    "SERVED",
    "—",
    "legality",
    "Build with Salamencite; state mega cannot hold another item; offer keep stone or base form+Leftovers (form change = offer only). Stone map from Showdown items.ts (standalone). legality.py has no mega-stone check — open arm tool item. derived_keys.row_g_h_salamence_mega",
    "NEW",
)
R(
    "MM2",
    "Switch its item to Leftovers.",
    "`scripts/eval/part_g_v4/fixtures/mm2_salamence_mega.json` Salamence-Mega+Salamencite",
    "MUTATION-REFUSED",
    "—",
    "legality+state",
    "Refuse: stone is required mega item; draft unchanged; form change offer only. derived_keys.row_g_h_salamence_mega",
    "NEW",
)
R(
    "MC1",
    "Give me a Mega Charizard build.",
    "idle",
    "ASK|ASSUME-STATE",
    "—",
    "usage+legality+ability",
    "No plain Charizard-Mega in pin; only X/Y. Pass = ASK which form, OR ASSUME-STATE Y (usage 9.51 vs X 0.47) + build Y with Charizardite Y + Drought + offer X. Fail: silent pick; invent plain Mega; dominant claim vs usage; Y without stone/Drought. Damage/speed claims need explicit ability. derived_keys.row_i_mega_charizard",
    "NEW",
)
R(
    "RB1",
    "Add Nasty Plot.",
    "`scripts/eval/part_g_v4/fixtures/rb1_lucario_megaz_calmmind.json` Lucario-Mega-Z + Lucarionite Z; moves Aura Sphere / Flash Cannon / Calm Mind (4th empty; no Protect/Detect)",
    "MUTATION-OK",
    "—",
    "move",
    "MUTATION-OK with stated consequence: apply+read-back; state Calm Mind+Nasty Plot are Status self-boosters sharing SpA; Calm Mind also +SpD (kept only via CM); offer swap one out; no silent remove. Key from stat_boosts.v1.json: CM +1 spa +1 spd; NP +2 spa. Damaging self-boosts do not count. derived_keys.row_j_calm_mind_nasty_plot",
    "NEW",
)

assert len(rows) == 134, len(rows)
ids = [r[0] for r in rows]
assert len(ids) == len(set(ids)), "duplicate ids"
_slice_counts = [8, 3, 2, 4, 7, 8, 3, 2, 10, 1, 5, 7, 8, 8, 8, 1, 8, 3, 4, 7, 3, 3, 1, 3, 7, 10]
assert sum(_slice_counts) == 134, sum(_slice_counts)

# Every expected class must be a glossary class (not a slice name)
GLOSSARY = {
    "SERVED",
    "PARTIAL",
    "FAIL-CLOSED",
    "ASSUME-STATE",
    "ASK",
    "ASK|ASSUME-STATE",
    "MUTATION-OK",
    "MUTATION-REFUSED",
    "NO-MUTATION",
}
for r in rows:
    assert r[3] in GLOSSARY, (r[0], r[3])


def esc(s: str) -> str:
    return s.replace("|", "\\|")


lines = [HEADER]
for r in rows:
    lines.append("| " + " | ".join(esc(str(x)) for x in r) + " |\n")

lines.append(
    """
---

## Option-list CLI gate (ADR-031 Amendment 2026-08-16a)

| Reply | candidate_selection | full_build_confirmation |
|---|---|---|
| exact id/label | `resolve_species_label` L1535–1541 | `_deterministic_build_option_ids` L325–409 |
| `2`/ordinals | `_ORDINAL_REPLIES` L71–89, L1543–1545 | numeric suffix L361–401 |
| `yes` (one) | affirm→0 L1549–1550 | `full_slot_confirmed` L1836–1837 |
| `the second one` | **not** deterministic (OL4) | — |
| `the faster one` | LLM gap-fill | LLM gap-fill |
| stale | **no gate (D8)** L1489–1569 | commit refuse L787–804 |

**Closed-set producers:** `candidate_selection` `slot_fill.py` ~L1787; `full_build_confirmation` `_emit_full_build_confirmation` ~L489+; `completion_preference`; `confirm_abandon_build`; `bootstrap_intake` not closed-set.

---

## Limitations (logged)

- Spread-move 0.75 condition (applies only if ≥2 targets are hit vs whenever the move targets multiple foes) is untested in Champions; DM3/DM4 follow the calc's multi-target assumption.
- Learnsets/moves are not oracle-cross-checked.
- H18's SP rule measures investment, not behavior.

---

## Status

**DRAFT for Vu/Claude row-by-row review.** Do not run through the graph or any model. Final location after review: `scripts/eval/` (eval-only PR).
"""
)

OUT.write_text("".join(lines))
print(f"wrote {OUT} rows={len(rows)} past_items={len(past_items)}")
