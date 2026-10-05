# Floor re-validation report (commit 2 — constants unchanged)

**Status (2026-10-05):** Vu keep decision — **all four constants unchanged** (`2.3` / `22.5` / `0.1` / `1.0`). No edits to the numeric values. This file + code comments document provenance; membership effect of the Showdown rescale is in [`rescale_deltas.json`](rescale_deltas.json).

**Method (pre-registered):** for each floor, observe `max(ingame_set%, showdown_set%)` on published-style Showdown after commit 1 regen; find smear/hole; do not tune to old roster.

Source artifacts: [`distributions.json`](distributions.json), [`rescale_deltas.json`](rescale_deltas.json) (old `origin/main` Raw-denom Showdown vs committed published, same floors).

---

## `_USAGE_SET_PCT_FLOOR` = **2.3** — policy constant (no data-derived hole)

| | |
| --- | --- |
| Decision | **keep 2.3** (2026-10-05) |
| Basis | Continuous smear; no clear hole |
| Eligible | 204 |
| Clear 2.3 | 111 |
| Gaps ≥1.0 near floor | **none** |

**Near-floor smear:** continuous from ~9.0 down through 2.344 / 2.084 / 2.048 into the 1.x tail. Old 2.3 sits inside the smear, not after a keep-cluster cliff.

---

## `_TRICK_ROOM_SET_PCT_FLOOR` = **22.5** — hole-supported

| | |
| --- | --- |
| Decision | **keep 22.5** (2026-10-05) |
| Basis | Local hole Gardevoir → Alakazam |
| Eligible | 60 |
| Clear 22.5 | 39 |

**Local hole at cut:**

| Keep (above) | Drop (below) | Gap |
| --- | --- | --- |
| `gardevoir` 24.305 (showdown) | `alakazam` 21.641 (showdown) | **2.664** |

**Gap rank among TR mid-ladder gaps (≥1.0):** **11th of 19** (1 = largest). Larger gaps sit higher on the ladder (e.g. 64.733→54.153 = 10.580; 74.6→66.321 = 8.279; …). The Gardevoir→Alakazam gap is a mid-pack local hole, not the distribution’s largest cliff — still the cut that matches the original “just below keep cluster ending at Gardevoir” rule. Alternative 23.0 stays in the same empty gap (no extra admits/drops vs 22.5 among listed species).

---

## `_SETUP_PRESENCE_SET_PCT_FLOOR` = **0.1** — policy constant (no data-derived hole)

| | |
| --- | --- |
| Decision | **keep 0.1** (2026-10-05) |
| Basis | Continuous ghost tail; no clear hole |
| Eligible | 286 |
| Clear 0.1 | 241 |
| Gaps ≥1.0 near 0.1 | **none** |

Band is continuous from ~0.37 down to ~0.003 with steps ≪0.05.

---

## `_DD_SETUP_PRESENCE_FLOOR` = **1.0** — policy constant (kept; not a hole edge)

| | |
| --- | --- |
| Decision | **keep 1.0** (2026-10-05) |
| Basis | Only ≥1 gap is above the keep smear; 1.0 is not at a hole edge |
| Eligible | 35 |
| Clear 1.0 | 19 |

**Only ≥1.0 gap:** `dragapult` 2.812 → `aerodactylmega` 1.454 (**1.358**). Below 1.454: dense smear (1.061 `scrafty`, 0.899 `steelix`, …).

**Species at or above the Dragapult cliff (pct ≥ 2.812)** — these are the keep-side cluster *above* the gap, not a tight band just above 1.0:

| sid | pct | source |
| --- | --- | --- |
| gyaradosmega | 86.014 | showdown |
| charizardmegax | 59.208 | showdown |
| feraligatrmega | 48.726 | showdown |
| feraligatr | 46.194 | showdown |
| gyarados | 28.981 | showdown |
| dragonite | 28.091 | showdown |
| tyranitarmega | 24.760 | showdown |
| baxcalibur | 21.597 | showdown |
| baxcaliburmega | 20.453 | showdown |
| flapple | 19.042 | showdown |
| tyranitar | 11.463 | showdown |
| altariamega | 9.407 | showdown |
| tyrantrum | 5.610 | showdown |
| salamence | 5.379 | showdown |
| salamencemega | 3.915 | showdown |
| scraftymega | 3.696 | showdown |
| dragapult | 2.812 | showdown |

**Cluster?** Yes in the weak sense of “everyone who clears the only ≥1 cliff,” but **not** a tight near-floor cluster: values span 2.812–86 with large internal gaps. The keep edge for a hole-cut would be just below **1.454** (~1.4), which would sit *under* Aerodactyl-Mega and *drop* Scrafty (1.061) who clears today’s 1.0. That is **not** “just below the keep edge” of the ≥2.812 group — corrected from the earlier misread. **1.0 kept anyway** per Vu (2026-10-05).

---

## Rescale effect at unchanged floors (new published vs old Raw)

Offline construct of all 18 gate categories, `live_fetch=None`, floors unchanged. Old Showdown = `git show origin/main:data/usage/champions-reg-mc.showdown_doubles.v1.json`. Full machine table: [`rescale_deltas.json`](rescale_deltas.json).

| Category | old → new | admitted | dropped |
| --- | --- | --- | --- |
| weather / terrain / redirection / SD / NP / CM | unchanged | — | — |
| trick_room_setter | 26 → 36 | +10 | 0 |
| tailwind_setter | 25 → 26 | +1 | 0 |
| sleep_status_spreader | 13 → 17 | +4 | 0 |
| screens_support | 14 → 30 | +16 | 0 |
| bulk_up_attacker | 39 → 43 | +4 | 0 |
| dragon_dance_attacker | 13 → 15 | +2 | 0 |
| iron_defense_body_press | 26 → 28 | +2 | 0 |

**Totals:** 39 admit events, 0 drops, 7 categories with flips.

### Flipped species — old vs new max source

*(limiting move / dual pair; screens = both LS+Reflect must clear 2.3; ID+BP = both irondefense+bodypress must clear 0.1)*

| cat | sid | old source @ pct | new source @ pct |
| --- | --- | --- | --- |
| TR | banettemega | showdown 8.859 | showdown 31.733 |
| TR | chandelure | showdown 22.350 | showdown 46.427 |
| TR | chandeluremega | showdown 12.492 | showdown 34.492 |
| TR | chimechomega | showdown 13.992 | showdown 41.324 |
| TR | espeon | **ingame** 18.4 | **showdown** 30.367 |
| TR | gardevoirmega | showdown 21.214 | showdown 37.289 |
| TR | malamar | showdown 12.710 | showdown 41.431 |
| TR | malamarmega | showdown 13.876 | showdown 37.751 |
| TR | medicham | showdown 7.346 | showdown 27.279 |
| TR | slowbrogalar | showdown 9.368 | showdown 26.791 |
| TW | scizormega | showdown 1.117 | showdown 2.897 |
| Sleep | altariamega | showdown 1.682 (sing) | showdown 4.331 (sing) |
| Sleep | aromatisse | showdown 1.643 | showdown 4.180 |
| Sleep | ninetales | showdown 0.900 | showdown 2.344 |
| Sleep | persian | showdown 0.801 | showdown 3.345 |
| Screens | alakazam | showdown 1.742 (LS+Ref lim) | showdown 5.699 |
| Screens | ampharos | showdown 0.791 | showdown 3.731 |
| Screens | appletun | showdown 1.344 | showdown 4.925 |
| Screens | arboliva | showdown 0.779 | showdown 2.493 |
| Screens | bellibolt | showdown 1.395 | showdown 3.718 |
| Screens | clefable | showdown 1.003 | showdown 3.129 |
| Screens | dragapult | showdown 2.044 | showdown 4.044 |
| Screens | espeon | showdown 0.989 | showdown 2.705 |
| Screens | forretress | showdown 0.550 | showdown 3.795 |
| Screens | froslass | showdown 1.467 | showdown 6.119 |
| Screens | mrrime | showdown 0.664 | showdown 2.381 |
| Screens | musharna | showdown 0.866 | showdown 2.646 |
| Screens | sableyemega | showdown 1.528 | showdown 4.222 |
| Screens | serperior | mixed (LS ingame 5.4 / Ref SD 1.983) | showdown 7.623 |
| Screens | umbreon | showdown 1.974 | showdown 5.270 |
| Screens | wyrdeer | mixed (LS ingame 8.3 / Ref SD 1.217) | mixed (LS ingame 8.3 / Ref SD 3.52) |
| Bulk Up | incineroar | showdown 0.066 | showdown 0.118 |
| Bulk Up | infernape | showdown 0.071 | showdown 0.240 |
| Bulk Up | lycanrocdusk | showdown 0.050 | showdown 0.101 |
| Bulk Up | medicham | showdown 0.094 | showdown 0.350 |
| DD | aerodactylmega | showdown 0.806 | showdown 1.454 |
| DD | scrafty | showdown 0.429 | showdown 1.061 |
| ID+BP | golurkmega | showdown 0.076 (lim irondefense) | showdown 0.218 |
| ID+BP | tyranitar | showdown 0.058 (lim irondefense) | showdown 0.110 |

### Clears a floor only via Showdown row (among admits)

All admits except **espeon (TR)**, **serperior (screens)**, and **wyrdeer (screens)** are Showdown-only clears (ingame 0 on the limiting move(s)). Full list in `rescale_deltas.json` → `showdown_only_clears_among_admits` (36 entries).

---

## Empty-learnset keys (report only — no fix in this PR)

See [`EMPTY_LEARNSET_PLAN.md`](EMPTY_LEARNSET_PLAN.md) (plan-first; do not implement here).

---

## Still open (after #245 merges)

1. Part C ability-usage audit (explain-only, owed in chat).
2. Forme-resolution follow-up (parked).
