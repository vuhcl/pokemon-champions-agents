# Part 1 — discovery for six candidate tools (report only; NO BUILD)

Cutoff context (Vu proposes): tools built/tested/reported by end of 2026-10-31; one prompt revision after; product changes outside `state/` on own branch+PR+ADR.

---

## T1 Mega-stone rule (MM1, MM2)

**Rows served:** MM1, MM2 (also hardens any future mega+non-stone lock).

**Where the rule lives:** `recommender/team_validation.py` (`validate_team_value` for `item` and possibly `species` when locking Mega forme). Optionally shared helpers in `recommender/item_conditions.py` / `legality.py`. ADR-002: legality is a tool call — the arm must refuse via the same validator the CLI uses, not LLM prose.

**Stone map at runtime:** **yes**, from vendored calc `MEGA_STONES` via `item_conditions.mega_stones_by_item_id()` (parses calc `items.js`). `scripts/eval/part_g_v4/key_artifacts/stone_map.v1.json` is a **key artifact** for Part G pins, not the runtime source.

**Today — Salamence + Leftovers / Mega + Leftovers:**
- `validate_team_value("item", "Leftovers", …)` → accept (species/item clause only; **no** mega-stone check).
- `apply_lock` uses that verdict; Mega+Leftovers and base+Leftovers both lock.
- Mega species can lock without forcing Salamencite.

**Tests / fixtures / covered rows that would change behavior:**
- `tests/recommender/test_team_validation.py` (and any apply_lock paths that currently accept non-stone on Mega).
- Fixture `mm2_salamence_mega.json` once wired.
- No current **covered** row depends on Mega+Leftovers succeeding (MM* are not-covered). Risk: any product path that locks a mega forme then a non-stone item in tests/fixtures.

**MM1 also needs:** stated consequence (“mega cannot hold another item”) + **offer** keep stone **or** base form+Leftovers (form change = offer only, not silent mutation). That is presentation/consequence on top of the refuse/rewrite rule — not covered by validator alone.

**Files outside `state/`:** `team_validation.py`, likely `item_conditions.py`, tests under `tests/recommender/`, possibly `nodes.apply_lock` messages. **Product PR + ADR-002 amendment** (draft in chat for Claude Project; do not edit mirror docs).

**LLM?** No — pure validator.

**Args:** none new for a gate inside validate; arm already passes species/item through lock tools (may need lock_item / batch lock if MM1 builds stone+forme together).

**Model vs tool:** Model interprets “Mega Salamence with Leftovers”; tool/validator decides stone requirement and refuse/offer structure.

**Effort:** 4–8 h (rule + tests + MM1 offer wording path + ADR draft).

**Risks:** forme display vs base+stone identity; Z-megas; locking order (species then item vs item then species); ADR-002 wording that “legality is a tool call” must include mega-stone as legality, not narrative.

**Recommendation:** **build** (product branch first) — highest-clarity mechanical refuse for MM2; MM1 needs offer UX.

---

## T2 Constraint and slot-condition tool (SC1, SC2, SC3; real path for MT3, HC2)

**Rows served:** SC1, SC2, SC3; unblocks correct MT3/HC2 constraint recording beyond judgment-only seeds.

**Existing nodes:**
- `nodes.record_constraint` + `constraint_enforcement.build_constraint` / `restore_constraint_axis` / `nodes.restore_constraint`.
- Payload comes from turn-intent LLM extraction (`type`, `predicate`, `scope`, `groundedness`, optional `mechanical_kind`/`value`).
- **No** first-class “draft slot condition” store distinct from team-wide `constraints` for SC1’s “Archaludon runs Snarl” future-slot draft. Slot conditions as drafts are **not** a shipped state field today.

**Without LLM extractor?** `build_constraint` itself is deterministic given a structured payload. Arm would need a tool that accepts structured args (predicate, scope, slot, groundedness) so the **model** fills args but the **tool** writes state — same pattern as lock_slot. Full NL→payload without LLM is not available.

**Read-back:** `read_team` does not echo constraints; constraints live on state; no arm `read_constraints` today (MRB1 is slot contents). T2 needs read-back of active constraints / draft conditions (SC3 t3).

**SC3 slot isolation:** scope must be slot-index-specific; solve_spread / any spread helper must accept optional condition **for the requested slot only**. Today judgment-only fixture tags are team_wide.

**SC2:** Soak not in Archaludon learnset — need learnset check tool or validator on recording a move-condition. “Refusal through legality; condition not recorded.”

**Files outside `state/`:** likely none if tools only wrap `record_constraint` + new draft-condition dict in arm state; **learnset check** may touch `legality.py` exposure. Fixture `_SLOT_BASE` entries for sc1/sc3 are `state/pending.py` only.

**LLM?** Write path can be LLM-free if args are structured; NL understanding stays in the model.

**Effort:** 8–14 h (draft-condition schema + tools + SC fixtures + learnset refuse + read-back).

**Risks:** conflating hard MechanicalSpec constraints with soft drafts; MT3/HC2 already covered with judgment-only seeds — changing product constraint semantics needs care; SP/weather rules remain unenforceable as today.

**Recommendation:** **build** for SC* + cleaner MT3/HC2; **needs Vu** on whether draft conditions are arm-only state vs product `constraints`.

---

## T3 Pending-screen staleness (OL10a, OL10b)

**Rows served:** OL10a, OL10b (ASK: not applied, re-ask).

**Frozen fixtures:**
- **OL10a:** `pending` + **current** `team` only. No presentation-time team, no stale flag, no dual team. Scorer-side note `traced_cli` only.
- **OL10b:** adds `provisional_fingerprint` (stale) on pending vs `provisional_fingerprint_now` on the file; loader `_load_ol` sets pending only → `provisional_slot` stays **null** → confirm/commit refuse as **missing**, not stale.

**Can ANY gate detect staleness with those frozen bytes?**
- **OL10a: no.** There is no prior team fingerprint in the file. A node change cannot reconstruct presentation-time team from current team alone. **Plainly: OL10a cannot be covered by a node change either** without changing/replacing the frozen fixture (key cut) or adding fields the freeze forbids.
- **OL10b: not with current loader.** Product `commit_full_slot` **does** compare fingerprints when provisional exists. Covering OL10b needs a **fixture route** that builds `provisional_slot` with the stale fp and a “now” mismatch — still no CS team-staleness for OL10a.

**Presentation-time team fingerprint (CLI D8):** would require CS producer (`present_candidates` / slot_fill emit) to record `team_fingerprint` (or per-slot fingerprints) on `pending_presentation` at presentation; `select_option` compares to current draft before bind. Tests: `test_pending_*`, arm `select_option` partial gate, any CLI closed-set tests. Product branch + tests; arm then consumes.

**Files outside `state/`:** `nodes.py` / `slot_fill.py` / classify pending path for D8; OL10a still blocked on fixture contents.

**Effort:** OL10b loader wire 1–2 h (`state/` only); full D8 CS gate 6–10 h product — **does not unlock OL10a** without fixture/key change.

**Risks:** key/fixture freeze; false “stale” on legitimate edits; FBC vs CS asymmetry.

**Recommendation:** **drop OL10a** for this run (not scorable / not coverable under freeze). **OL10b:** fixture-route wire (**build** small) or drop if provisional reconstruct is judged invented. Full D8 = **needs Vu** (product + possible key cut).

---

## T4 Archetype and bootstrap tool (MS5, H17, H18)

**Rows served:** MS5; partial base for H17/H18 (H17/H18 also need T6).

**`handle_archetype_change`:** deterministic. Writes locked `archetype` Attr from payload `components`; calls `reconcile_on_archetype_change` (calc client for mismatch flags; does **not** edit locked slots — pending flags / offers). **No LLM inside the node.** Network: only if reconcile hits calc (localhost calc service), not the public web.

**Bootstrap path:** `bootstrap` intake uses ChatOllama/ChatAnthropic (`llm_invoke`) — **LLM + provider network**. Writes bootstrap flags / initial preferences; not a pure tool.

**MS5 conflict audit needs:** after archetype=rain offense, scan locked slots for non-rain weather abilities (Drought on Charizard-Mega-Y) and rain-reduced moves (Solar Beam); control Pelipper not flagged; locked unchanged; offered replacements legal. Today reconcile may surface sibling/archetype flags — arm has **no** `change_archetype` / `read_archetype` / audit tool wrapping that node.

**H17/H18 beyond archetype:** candidate generation (T6) and (H18) stated SP-rule definition + invite alternate; H18b already covered separately with fixture.

**Files outside `state/`:** none if wrapping existing node; bootstrap tool that calls LLM would violate “arm tools are deterministic” preference — keep bootstrap out of arm tools.

**Effort:** 4–6 h for archetype change + read-back + MS5 audit surface; H17/H18 still blocked on T6.

**Risks:** exposing reconcile calc dependency; over-claiming bootstrap without LLM.

**Recommendation:** **build** archetype tool for MS5; **needs Vu** whether H17 is in-scope without bootstrap LLM (progress via archetype+candidates only).

---

## T5 Edit-consequence tool (TB2, RB1, GS1)

**Plan decision 8 (four-move list):** On TB2 fixture values fully locked via `_lock_internal`, `read_team` returns moveset `['Flare Blitz','Fake Out','U-turn','Parting Shot']` intact. RB1 fixture has **three** moves (4th empty) — list survives as stored. `format_turn` only shows locked members when `all_locked`; arm scoring should use `read_team`, not CLI `format_turn` alone.

**Deterministic consequences from data:**

| rule | source | rows |
|---|---|---|
| Item type-boost vs remaining damaging moves of that type | `TYPE_BOOST_ITEMS` / `item_conditions.mechanical_condition` + learnset/damaging-type check | TB2 (Charcoal), TB1 pattern |
| Choice-lock vs status moves | reconcile `_tier1_choice_status_moves` + `flags.v1` / snap category Status (except Trick/Switcheroo) | GS1 |
| Status self-boosters sharing a stat | `data/moves/stat_boosts.v1.json` (CM +1 spa+spd; NP +2 spa) | RB1 |

**How arm edits moveset today:** **`lock_slot` is species-only.** No arm tool for item/moveset/nature field edit. Product CLI uses turn-intent `edit` → apply_lock/edit paths. T5 needs `lock_attr` / `edit_slot_field` wrapping validated writes + optional consequence payload.

**`reconcile_on_sibling_change`:** on item/moveset sibling change, runs mechanical Choice/status and speed-direction checks, then calc diff, then archetype; may set `still_active=False` / pending flags / supersede — **does not silently rewrite moves** for Choice (flags costly/toss-up). Consequences for GS1/TB2 are “state + warn/offer,” matching request-set (no silent move/item change).

**Files outside `state/`:** possibly thin wrappers only; consequence helpers already in `item_conditions` / `reconcile`. New arm tools in `state/tools.py`.

**Effort:** 8–12 h (edit tool + three consequence reporters + fixture routes for tb2/rb1/mm2).

**Risks:** duplicating CLI edit semantics; Choice exception list drift; RB1 empty 4th slot vs replace.

**Recommendation:** **build** — unblocks three build-trap rows with clear data sources.

---

## T6 Candidate discovery (MT4; maybe H27; base for H17/H18)

**Rows served:** MT4 (required); H25/H26/H17/H18 if built; H27 already coverable via frozen pending without regenerating.

**Producer:** `query_threat_counters` (threat_counters.py) → slot-fill context → `present_candidates` / `run_slot_fill_terminal` (slot_fill.py). H27 loader already calls this offline.

**LLM?** No inside these functions. **Network?** Calc client to localhost for verified matchups; offline pinned usage/legality. `allow_live=False` for eval. Degraded path uses static type effectiveness.

**As read-only arm tool:** feasible — args: slot, optional n; returns option list (species, evidence, source) **or** writes `pending_presentation` like CLI (write). Read-only return without mutating pending would not satisfy MT4 t2 (“show candidates” that t3 checks rejects against). Prefer write-pending mirror of CS producer.

**Returns:** CS pending shape (options with species) + evidence; status available/degraded.

**Model-driven claim:** Exposing full recommender discovery makes the arm a **thin wrapper of the CLI recommender’s candidate node**. The arm remains model-driven for *when* to call and *how* to narrate, but candidate **identity/order** become tool-determined (already the product’s design for legality/mechanics). Honest framing: arm = model + **same** deterministic producers as CLI, not a separate recommender. That strengthens anti-hallucination; it weakens any claim that the arm invents its own shortlist.

**Files outside `state/`:** none required if importing existing functions; may need regulation from state.

**Effort:** 6–10 h (tool + MT4 wiring + tests that rejected species stay out).

**Risks:** non-determinism if calc/usage drift (pins protect); conflating arm eval with CLI win-rate; H27 double path (fixture pending vs live regen).

**Recommendation:** **build** — only way to cover MT4; enables H25/H26/H17 theme progress. **needs Vu** on “wrapper” framing for portfolio narrative.

---

## Effort / pick summary

| tool | hours | recommendation |
|---|---|---|
| T1 Mega-stone | 4–8 | **build** (product PR+ADR) |
| T2 Constraints/slot-conditions | 8–14 | **build**; Vu on draft-condition home |
| T3 Staleness | 1–2 loader / 6–10 D8 | **drop OL10a**; OL10b fixture wire or drop; D8 needs Vu |
| T4 Archetype | 4–6 | **build** (MS5); H17 needs T6 too |
| T5 Edit-consequence | 8–12 | **build** |
| T6 Candidates | 6–10 | **build** (MT4); Vu on wrapper claim |

**Anything that contradicts plan decisions:** OL10a coverage via “node fix” contradicts fixture reality (decision that frozen OL10 files are scorer-staleness / D8-open). Coverable-now list must not enter covered until readiness+scorability gate (honored here). Product validator T1 on own branch (honored). AR1/AR2 stay out aligns with MT7/MT8 DEV policy.
