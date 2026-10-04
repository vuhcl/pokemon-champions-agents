# Deterministic-graph capability discovery (role-play requests)

Discovery only. Not a frozen eval baseline. Scratch artifacts under `/tmp/det_graph_capability/`.

---

## Repo HEAD, regulation, and data state

| Field | Value |
|---|---|
| Recorded HEAD (run meta) | `88df2d7bda5e0f357e98631b7fd821aba6c328af` (`88df2d7 Fix VGCPastes M-C gid and harden GITHUB_OUTPUT reasons.`) |
| Format id | `[Gen 9 Champions] VGC 2026 Reg M-C` |
| `regulation_mod` | `champions` |
| File tag | `champions-reg-mc` |
| Legality snapshot formats | VGC + BSS Reg M-C |
| Primary usage dir | `scripts/eval/artifacts/_scratch_mc_showdown_fill/merged_usage_dir/` (Showdown half filled; meta `showdown_format=gen9championsvgc2026regmc`, 316 Showdown species) |
| Secondary usage dir | shipped `data/usage/` (Showdown half empty: `showdown_vgc_mb.species={}`) |
| Checkpointer | `MemorySaver` (never user SQLite) |
| Graph entry | `compile_graph` + `invoke_user_text` / CLI seam (`pending_input`) |
| Calc | real CalcClient (`/health` ok) |
| Turn cap | 6 |
| Artifacts | `/tmp/det_graph_capability/runs/*.json`, `independent_checks_{merged,shipped}.json`, `legality_precheck.json` |

Note: workspace HEAD may have moved after the run; capability results are keyed to the recorded meta HEAD above.

---

## Legality pre-check

Against production M-C legality snapshot (`load_snapshot` / `is_species_legal` / `is_item_legal`):

| Name | Kind | Legal |
|---|---|---|
| Kingambit | species | true |
| Hatterene | species | true |
| Farigiraf | species | true |
| Torkoal | species | true |
| Lilligant | species | **false** |
| Lilligant-Hisui | species | **false** |
| Tornadus | species | **false** |
| Tornadus-Therian | species | **false** |
| Garchomp | species | true |
| Pelipper | species | true |
| Gholdengo | species | true |
| Sinistcha | species | true |
| Walking Wake | species | **false** |
| Chi-Yu | species | **false** |
| Miraidon | species | **false** |
| Scovillain | species | true |
| Whimsicott | species | true |
| Choice Scarf | item | true |
| Choice Specs | item | **false** |

### Substitutions (capability set)

| Illegal | Substitute | Role | Used where |
|---|---|---|---|
| Lilligant | Scovillain | Chlorophyll sun offense | S4 seed (slot 2); i7 user text |
| Tornadus | Whimsicott | Prankster Tailwind | S5 seed (slot 0 locked) |

i7 wording used: `who pairs with both Torkoal and Scovillain` (scratch had `... torkoal and lilligant`).
i4 wording used (scratch exact): `scrap the whole team and start over`.
i1/i2/i3 wording used from scratch SESSIONS (not the short task paraphrases).

Illegal-entity probes P1–P3 kept illegal names on purpose.

---

## Models and settings

| Setting | Value |
|---|---|
| Models run | `qwen2.5:7b`, `qwen3.5:latest` (both present via Ollama) |
| Provider | Ollama (`build_ollama_bootstrap_intake_parser` + `build_ollama_turn_intent_parser`) |
| `keep_alive` | `30m` |
| Patches | **None** on `classify_pending` / parsers. Only scratch monkeypatch: `usage_data.USAGE_DIR` |
| Follow-ups | Minimal natural answers (`1` / `yes` / short bootstrap text); stop at idle or turn 6 |

Primary pass: merged usage, all requests, both models.
Secondary pass: usage/threat-dependent ids against shipped usage (`S3,S4,S8,i5L,i7,i8L,C1,C1b,C2,C3,D1,D1b`).
Non-determinism subset (merged, repeat=1): `S1,S2,S3` (+ attempted `C1,D1`; see risks).

Harness note: first main-process pass hit a scratch bug (`pending_presentation is None` → `.get` crash) for idle C1/C2/C3/C4/D1; those were re-run with the fixed harness. Report uses recovered run JSONs.

---

## Outcome counts

Capability set = 22 ids: S1–S9, i1–i4, i5L, i6L, i7, i8L, C1–C4, D1.  
Probes P1–P3 counted separately.  
C1b/D1b = extra FBC-seeded variants of C1/D1 (not in the 22).

### Primary (merged usage, repeat=0)

**qwen2.5:7b — capability (n=22)**

| Outcome | Count |
|---|---|
| FAIL-CLOSED | 15 |
| STALL/ERROR | 4 |
| PARTIAL | 2 |
| MISROUTED | 1 |
| SERVED | 0 |

**qwen2.5:7b — probes (n=3):** FAIL-CLOSED 3

**qwen3.5:latest — capability (n=22)**

| Outcome | Count |
|---|---|
| FAIL-CLOSED | 10 |
| STALL/ERROR | 9 |
| SERVED | 2 |
| PARTIAL | 1 |
| MISROUTED | 0 |

**qwen3.5:latest — probes (n=3):** FAIL-CLOSED 3

**FBC variants (merged)**

| Id | qwen2.5:7b | qwen3.5:latest |
|---|---|---|
| C1b | FAIL-CLOSED | PARTIAL (`compare`) |
| D1b | FAIL-CLOSED | PARTIAL (`compare`) |

### Secondary (shipped usage, usage-dependent subset)

**qwen2.5:7b (n=12):** FAIL-CLOSED 10, PARTIAL 2  
**qwen3.5:latest (n=12):** FAIL-CLOSED 6, PARTIAL 2, STALL/ERROR 4  

No outcome class flipped from “served” on merged to a different success class on shipped for this subset; most stayed FAIL-CLOSED / PARTIAL / STALL. Shipped vs merged mainly changes threat ranking for independent checks, not CLI success here.

---

## Per-request table (primary merged)

Columns: judged (2026-10-02 a/b/c/d), measured outcome, first intent, notes.

### qwen2.5:7b

| Id | Judged | Measured | First intent | Notes |
|---|---|---|---|---|
| S1 | c | FAIL-CLOSED | pending_response | Raw LLM emitted `constraint` type=Water; schema validation dropped it → edit-field clarify. No constraint recorded. |
| S2 | b | MISROUTED | repick_locked_slot | Empty team; repick on slot 4 failed; then auto-bootstrap built Venusaur + Charizard-Mega-Y (not bulky Fire@4). |
| S3 | c | PARTIAL | pending_response | Unmatched; no Fire@3 pick. |
| S4 | c | FAIL-CLOSED | pending_response | Seeded Farigiraf/Torkoal/Scovillain unchanged. |
| S5 | c | STALL/ERROR | repick_locked_slot | 6-turn stall after repick error → bootstrap candidate churn. Tailwind Whimsicott retained; slot5 not usefully swapped. |
| S6 | d | FAIL-CLOSED | pending_response | No Farigiraf context in state. |
| S7 | a | FAIL-CLOSED | pending_response | Edit-field clarify template (no `no_duplicate_items` constraint). |
| S8 | d | FAIL-CLOSED | pending_response | Clarify / no ranking tool path. |
| S9 | d | STALL/ERROR | continue | Bootstrap loop 6 turns. |
| i1 | c | STALL/ERROR | bootstrap_response | Direction map failures / bootstrap loop. |
| i2 | c | STALL/ERROR | bootstrap_response | Same. |
| i3 | a | FAIL-CLOSED | bootstrap_response | “mono electric…” not mapped; no Electric constraint recorded. |
| i4 | a | PARTIAL | reset | Reset fired; follow-ups re-entered bootstrap and locked new mons (Pelipper gone, team not left empty). |
| i5L | c | FAIL-CLOSED | pending_response | Misparsed toward item constraint; fell to edit clarify. No calc OHKO. |
| i6L | a | FAIL-CLOSED | pending_response | Clarify slot. |
| i7 | a | FAIL-CLOSED | pending_response | No shared-teammates path from idle. |
| i8L | b | FAIL-CLOSED | pending_response | Echoed question. |
| C1 | — | FAIL-CLOSED | pending_response | Idle; no FBC options. |
| C2 | — | FAIL-CLOSED | pending_response | Idle. |
| C3 | — | FAIL-CLOSED | pending_response | Idle. |
| C4 | — | FAIL-CLOSED | pending_response | Asked for team context (“better” undefined). |
| D1 | — | FAIL-CLOSED | pending_response | Idle. |
| P1 | d | FAIL-CLOSED* | pending_response | “That action isn't available here.” No state change; **no legality mention**. |
| P2 | a | FAIL-CLOSED* | pending_response | Same template; no legality mention. |
| P3 | b | FAIL-CLOSED* | pending_response | Edit-field clarify; no legality mention. |

\*Probe FAIL-CLOSED = no state change, but honesty bar for illegal entities not met (see probes section).

### qwen3.5:latest

| Id | Judged | Measured | First intent | Notes |
|---|---|---|---|---|
| S1 | c | SERVED† | constraint | Hard Water `per_slot` constraint recorded. †Slot index “2” not bound in mechanical payload; follow-ups stalled in bootstrap. |
| S2 | b | FAIL-CLOSED | pending_response | Clarified / did not serve bulky Fire@4. |
| S3 | c | PARTIAL | pending_response | Unmatched; no verified Fire outspeed pick. |
| S4 | c | FAIL-CLOSED | pending_response | Seed unchanged. |
| S5 | c | STALL/ERROR | repick_locked_slot | 6-turn bootstrap stall. |
| S6 | d | STALL/ERROR | continue | Bootstrap loop. |
| S7 | a | FAIL-CLOSED | pending_response | Free-text claim: “no restriction against duplicate items in standard competitive formats” (not tool-backed). |
| S8 | d | FAIL-CLOSED | pending_response | Asked for archetype clarification. |
| S9 | d | STALL/ERROR | continue | Bootstrap loop. |
| i1 | c | STALL/ERROR | bootstrap_response | Bootstrap loop. |
| i2 | c | STALL/ERROR | bootstrap_response | Bootstrap loop. |
| i3 | a | FAIL-CLOSED | bootstrap_response | No Electric constraint; direction map fail. |
| i4 | a | SERVED | reset | Reset cleared Pelipper; draft empty after reset turn (then bootstrap prompts for 5 more turns without re-locking). |
| i5L | c | STALL/ERROR | continue | Treated as team-continue / bootstrap, not damage calc. |
| i6L | a | FAIL-CLOSED | pending_response | Clarified slot. |
| i7 | a | FAIL-CLOSED | pending_response | No teammates tool path. |
| i8L | b | STALL/ERROR | continue | Bootstrap loop; no support_needs wrapper. |
| C1 | — | FAIL-CLOSED | pending_response | Idle. |
| C2 | — | STALL/ERROR | continue | Misrouted into bootstrap loop. |
| C3 | — | STALL/ERROR | continue | Same. |
| C4 | — | FAIL-CLOSED | pending_response | Clarified “better” needs team context. |
| D1 | — | FAIL-CLOSED | pending_response | Idle. |
| C1b | — | PARTIAL | compare | `build_compare` ran on FBC options; Spe figures wrong vs question (Timid option was low-Spe HP set). “No threat context”. |
| D1b | — | PARTIAL | compare | Compared usage Calm/Relaxed/Modest options; Spe-only notes; no Def/SpD damage table. |
| P1 | d | FAIL-CLOSED* | pending_response | Treated Specs Chi-Yu as discussable OHKO (“strong STAB Fire…”); **no illegal/Specs-illegal message**; no state change. |
| P2 | a | FAIL-CLOSED* | pending_response | Asked which slot for Miraidon+Scarf; **treated as legal add**; no state change. |
| P3 | b | FAIL-CLOSED* | pending_response | Offered to add Walking Wake / support; **no illegal message**. |

---

## Judged-vs-measured table

| Id | Judged | Measured (qwen2.5 / qwen3.5) | Agree? | Why |
|---|---|---|---|---|
| S1 | c (compositional) | FAIL-CLOSED / SERVED† | Partial | Type constraint kind exists; slot binding + idle→bootstrap friction. qwen2.5 validation drop shows parser fragility. |
| S2 | b (new kind) | MISROUTED / FAIL-CLOSED | Yes (gap) | “bulky” not a mechanical kind; Fire@slot4 not served. |
| S3 | c | PARTIAL / PARTIAL | Yes | Needs type∧outspeed composition + calc; not one intent. |
| S4 | c | FAIL-CLOSED / FAIL-CLOSED | Differs | Prior tool role-play assumed composition; graph never entered matchup/swap path from seeded idle. |
| S5 | c | STALL / STALL | Differs | Repick misroute; no “keep Tailwind ∧ handle Ground” composition. |
| S6 | d | FAIL-CLOSED / STALL | Mostly | Should fail closed; qwen3.5 wandered into bootstrap. |
| S7 | a | FAIL-CLOSED / FAIL-CLOSED | Surface yes, quality no | Duplicate-item constraint kind exists (`no_duplicate_items`) but was not applied; qwen3.5 asserted legality in prose. |
| S8 | d | FAIL-CLOSED / FAIL-CLOSED | Yes | No “best team” ranking intent. |
| S9 | d | STALL / STALL | Weak | Should fail closed on OU; instead bootstrap stall. |
| i1 | c | STALL / STALL | Differs | Archetype/Trick Room path not completed in 6 turns. |
| i2 | c | STALL / STALL | Differs | Same. |
| i3 | a | FAIL-CLOSED / FAIL-CLOSED | Differs | Type constraint kind exists; bootstrap direction path never recorded Electric team-wide constraint. |
| i4 | a | PARTIAL / SERVED | Mostly | `reset` intent exists and fires; qwen2.5 re-filled team afterward. |
| i5L (was i5 d) | c | FAIL-CLOSED / STALL | Differs | Legal OHKO still not a first-class idle intent; no classify_matchup route. |
| i6L (was i6 a) | a | FAIL-CLOSED / FAIL-CLOSED | Differs | Legal Garchomp+Scarf still needs lock/edit composition; clarify only. |
| i7 | a | FAIL-CLOSED / FAIL-CLOSED | Differs | `query_shared_teammates` exists in tools layer but not reached from turn intent. |
| i8L (was i8 b) | b | FAIL-CLOSED / STALL | Yes (gap) | support_needs still needs RoleShapeContext wrapper. |
| P1–P3 | d/a/b | FAIL-CLOSED* / FAIL-CLOSED* | **No on honesty** | No state change, but **not** honest legality fail-closed (esp. qwen3.5). |
| C1–C4, D1 | — | mostly FAIL-CLOSED / mix | — | See comparison section. |

---

## Schema-vs-composition list (what is missing)

| Request | Schema-only? | Composition? | Missing exactly |
|---|---|---|---|
| S1 slot Water | Mostly schema | Slot index binding | Constraint payload does not carry slot index; idle Water constraint then forces bootstrap. |
| S2 bulky Fire@4 | No | Yes | No `bulky` / bulk mechanical kind; slot-targeted typed candidate fill. |
| S3 Fire ∧ outspeeds max Spe Garchomp | No | Yes | No compound constraint; need type filter + CalcClient Spe vs reference set + slot lock. |
| S4 threatens X, swap weakest | No | Yes | Matchup over roster + threat_counters + rejection/repick in one plan. |
| S5 swap keep Tailwind ∧ Ground answer | No | Yes | Dual constraint (role/move Tailwind preserved + Ground handling). |
| S6 why A over B | — | Explanation | No contrastive rationale intent; should stay fail-closed without history. |
| S7 two Scarf | Schema | Soft | `no_duplicate_items` soft/hard constraint path not triggered from NL. |
| S8 best team | — | Fail-closed | No global ranking intent (correct). |
| S9 OU balance | — | Fail-closed | Cross-format reject; currently stalls instead. |
| i1 TR-only no weather | Partial | Yes | Archetype components + negative weather constraint + fill. |
| i2 HO no weather | No | Yes | Offense archetype packager + negative weather. |
| i3 mono-Electric | Schema | Bootstrap glue | Team-wide type constraint recording from NL (works in tool layer; not from bootstrap direction string). |
| i4 scrap team | Schema | — | `reset` works; need stop-after-reset policy. |
| i5L OHKO claim | No | Yes | Idle damage/matchup intent → CalcClient / classify_matchup. |
| i6L species+item | Schema | Lock composition | Multi-attr lock from short NL. |
| i7 who pairs with A+B | Schema bridge | — | Turn intent → `query_shared_teammates`. |
| i8L support needs | No | Yes | Wrapper RoleShapeContext from classify_anchor_role. |
| C1–C2 nature outspeed | Partial on FBC | Yes | Counterfactual Spe compare vs threat set; FBC `compare` only diffs listed options’ Spe, no threat list. |
| C3 max Atk OHKOs | No | Yes | Damage enumerate vs threat set at two Atk allocations. |
| C4 Modest vs Timid “better” | — | Fail-closed/clarify | Undefined objective (observed). |
| D1 max Def vs SpD vs split | Partial on FBC | Yes | Bulk spread enumerator + damage table; FBC compare emitted Spe-only. |

---

## Independent checks (calc service only)

SP rules (repo): Champions SP budget **66**, per-stat cap **32** (`recommender/recommend.py` `SP_BUDGET`/`_SP_CAP`; `usage_spreads` rejects sum≠66).

Threat sets: re-ranked via `species_usage.usage_rank` (merged Showdown fill otherwise returns near-dex order from `query_by_usage`).

### C1 — Pelipper Timid vs Modest @ Spe SP=32

| Data | Timid Spe | Modest Spe | Flips (outspeed changes) |
|---|---|---|---|
| Merged | 128 | 117 | Clefable (123), Machamp (117) |
| Shipped | 128 | 117 | Incineroar, Farigiraf, Sylveon (123); Tyranitar (124) |

System (C1b qwen3.5 compare): reported Modest option Spe **117** vs Timid option Spe **93** — the Timid FBC sibling was **not** Spe=32 (it was `Timid 32/0/0/32/2/0` → Spe 93). So compare ran but answered a different counterfactual than “Timid over Modest at equal Spe investment.” No threat list (“No threat context for damage/KO”).

### C2 — Garchomp Jolly vs Adamant @ Spe SP=32

| Data | Jolly Spe | Adamant Spe | Example flips |
|---|---|---|---|
| Merged | 169 | 154 | Charizard/Arcanine-Hisui/Ninetales/Arcanine |
| Shipped | 169 | 154 | Charizard, Staraptor, Excadrill |

System (idle C2): did not serve compare; qwen3.5 stalled into bootstrap.

### C3 — Kingambit Atk 32 vs Atk 16 (remainder HP→Spe→SpD; Adamant; Black Glasses)

Shipped target example **Sneasler** Kowtow Cleave: Atk32 damageRange [54,63] vs Atk16 [49,58]; KO class shifts on several targets (full tables in `independent_checks_shipped.json`).  
Merged target example **Charizard** Kowtow: Atk32 guaranteed 2HKO vs Atk16 43.8% 2HKO.

System: no damage compare served from idle.

### D1 — Sinistcha spreads

Assumed spreads (Bold, Hospitality, Sitrus Berry; remainder HP→Spa→Spe):

| Label | Spread |
|---|---|
| max_def_32 | `{hp:32, atk:0, def:32, spa:2, spd:0, spe:0}` |
| max_spd_32 | `{hp:32, atk:0, def:0, spa:2, spd:32, spe:0}` |
| split_16_16 | `{hp:32, atk:0, def:16, spa:2, spd:16, spe:0}` |

Attackers: usage `common_moves` (skip Protect); Adamant LO then Modest LO retry if 0 damage.

Shipped class flips (survive/KO band changes across spreads): **10** threats with ≥1 flip, including:
- Sneasler Dire Claw: max_def chip vs max_spd/split 2HKO  
- Incineroar Throat Chop: max_def 2HKO vs max_spd OHKO  
- Kingambit Sucker Punch: max_def 2HKO vs max_spd OHKO  

System (D1b qwen3.5): `compare` on usage Calm/Relaxed/Modest options; output Spe-only; **no** Def/SpD damage classes.

---

## Claims table

`iter_verifiable_claims_from_message` on all primary merged capability visibles: **0** extracted type/ability claims (denominators: 0 claim-bearing extractor hits / 0 claims / 0 false via extractor).

Hand audit of `pending_response` / compare user-visible factual claims (capability + probes, primary merged):

| Id | Model | Claim type | Text (abbrev) | Verify | Guard rewrite? |
|---|---|---|---|---|---|
| S7 | qwen3.5 | legality/item | “no restriction against duplicate items in standard competitive formats” | Unverified / misleading for this product (duplicate-item constraint exists as optional mechanical kind; not checked) | No (`correction_response` null) |
| P1 | qwen3.5 | legality + damage | Specs Chi-Yu “strong STAB Fire… could potentially OHKO Kingambit” | **False premise**: Chi-Yu illegal; Choice Specs illegal | No |
| P2 | qwen3.5 | legality | Slot question for Miraidon+Scarf | **False premise**: Miraidon illegal | No |
| P3 | qwen3.5 | legality | Offer to add Walking Wake | **False premise**: Walking Wake illegal | No |
| C1b | qwen3.5 | speed | Modest Spe 117 vs Timid Spe 93 | Spe numbers match those FBC options via compare path; **not** equal-Spe Timid-vs-Modest | No |
| D1b | qwen3.5 | speed | Spe 90/90/81/90 for options | Spe-only; not Def/SpD answer | No |
| S1–many qwen2.5 | qwen2.5 | other | Edit-field clarify template | N/A (not a species fact) | No |

Deterministic-mode claim exposure (extractor): claim-bearing messages **0**, claims **0**, false **0**, over capability primary merged visibles as denominator for extractor (messages with any user-visible LLM pending_response text were numerous, but none matched type/ability claim patterns).

---

## Parser / latency stats (primary merged, both models, repeat=0)

| Metric | Value |
|---|---|
| LLM parse calls logged | 137 |
| Parser exceptions / timeouts | **0 / 137** (no `error` on wrapped invoke) |
| LLM latency p50 | 53739 ms |
| LLM latency p90 | 141741 ms |
| LLM latency max | 232520 ms |
| Tool `log_tool_call` samples | 1229 |
| Tool latency p50 | ~0.36 ms |
| Tool latency p90 | ~870 ms |

qwen2.5:7b typically 0.4–3 s/turn when warm; qwen3.5:latest often 20–200 s/turn (thinking). Multi-turn bootstrap stalls dominate wall time.

Non-determinism subset (merged r0 vs r1): S1/S2/S3 outcomes **identical** per model across repeats. C1/D1 r1 FATAL on the long-lived main process (stale code); recovered C1/D1 from fixed re-run only once each — **no second fixed repeat** for C1/D1.

---

## Risks and unknowns

1. **Illegal-entity probes fail the honesty bar** while still “FAIL-CLOSED” on state: qwen3.5 discusses Chi-Yu/Specs, Miraidon, Walking Wake as usable. Not silent roster substitution, but silent legality.
2. **Idle + `bootstrap_intake_complete=True` seeding** still re-enters bootstrap after many intents (`continue`, failed repick), causing artificial STALL/ERROR under a 6-turn cap.
3. **Parser validation drops valid-looking constraint JSON** (S1 qwen2.5): raw model emits Water type constraint; post-parse becomes edit clarify.
4. **FBC `compare` is not a threat-counterfactual engine**: Spe-only, option-local, can pick low-Spe “Timid” siblings; answers C1/D1 only PARTIAL.
5. **Merged Showdown fill changes `query_by_usage` ordering**; independent checks must re-rank by `usage_rank` or use shipped ladder ranks for threat meaning.
6. **D1 move extraction** requires `common_moves` (not `moves`); empty moves would falsely show no flips.
7. **HEAD drift**: results recorded under `88df2d7…`; later workspace commits not re-run.
8. **Claim guard** (`correction_response`) never fired on these runs; free-text legality/damage claims in `pending_response` are unguarded.
9. **Outcome labels are harness heuristics** (constraint presence, draft diffs, intent tags) plus calc checks where noted — not eval oracles.

---

## Per-request transcripts (appendix)

Full JSON transcripts: `/tmp/det_graph_capability/runs/<id>__<model>__<usage>__rN.json`.

### S1 — “Slot 2 should be a Water type.” (idle)

**qwen2.5:7b:** T0 `pending_response` edit-field template. LLM raw had `constraint` Water. Outcome FAIL-CLOSED.  
**qwen3.5:latest:** T0 `constraint` hard Water per_slot recorded; T1–T5 bootstrap_response stalls (`Couldn't map direction: VGC doubles team…`). Outcome SERVED†.

### S2 — “Give me a bulky Fire type for slot 4.” (idle)

**qwen2.5:7b:** T0 `repick_locked_slot` slot 4 → error; then built Venusaur + Charizard-Mega-Y. MISROUTED.  
**qwen3.5:latest:** FAIL-CLOSED pending_response.

### S3 — Fire outspeeds max-speed Garchomp (idle)

Both: PARTIAL pending_response; no slot3 Fire pick; no calc Spe proof in-graph.

### S4 — threatens Kingambit / swap (seed Farigiraf, Torkoal, Scovillain)

Both: FAIL-CLOSED; seed unchanged; no matchup intents.

### S5 — swap slot5 Ground / keep Tailwind (seed Whimsicott, Garchomp@5)

Both: STALL/ERROR via `repick_locked_slot` then bootstrap.

### S6 — Farigiraf over Hatterene (idle)

qwen2.5 FAIL-CLOSED; qwen3.5 STALL bootstrap.

### S7 — two Choice Scarf (idle)

Both FAIL-CLOSED; qwen3.5 prose allows duplicates without tool check.

### S8 — best team Reg M-C (idle)

Both FAIL-CLOSED clarify.

### S9 — OU balance (idle)

Both STALL bootstrap (should prefer fail-closed).

### i1 / i2 — TR-only / HO no weather (cold bootstrap)

Both models STALL in bootstrap_response loops (direction mapping failures).

### i3 — mono electric (cold bootstrap)

Both FAIL-CLOSED; no Electric constraint recorded.

### i4 — scrap team (seed Pelipper)

qwen2.5: `reset` then re-filled → PARTIAL.  
qwen3.5: `reset` → empty draft → SERVED (then bootstrap prompts).

### i5L — Scarf Gholdengo OHKO Kingambit (idle)

qwen2.5 FAIL-CLOSED (misparsed constraint). qwen3.5 STALL continue/bootstrap. No calc.

### i6L — Garchomp + Scarf (idle)

Both FAIL-CLOSED clarify slot.

### i7 — pairs with Torkoal + Scovillain (idle)

Both FAIL-CLOSED; shared-teammates tool not invoked.

### i8L — support Hatterene needs (idle)

qwen2.5 FAIL-CLOSED echo; qwen3.5 STALL bootstrap.

### P1 — Specs Chi-Yu OHKO Kingambit

qwen2.5: “That action isn't available here.”  
qwen3.5: discusses Specs Chi-Yu OHKO potential — **illegal entity + illegal item treated as discussable**.

### P2 — Miraidon + Scarf

qwen2.5: action unavailable.  
qwen3.5: asks slot for Miraidon — **treated as legal**.

### P3 — support Walking Wake

qwen2.5: edit clarify.  
qwen3.5: offers to add Walking Wake — **treated as legal**.

### C1 (idle) / C1b (FBC Pelipper)

Idle both FAIL-CLOSED.  
C1b qwen3.5 PARTIAL compare Spe 117 vs 93, no threats. qwen2.5 FAIL-CLOSED pending_response on FBC.

### C2 / C3 (idle)

qwen2.5 FAIL-CLOSED; qwen3.5 STALL bootstrap.

### C4 — Modest or Timid better (idle)

Both FAIL-CLOSED clarify (expected for undefined “better”).

### D1 (idle) / D1b (FBC Sinistcha)

Idle FAIL-CLOSED.  
D1b qwen3.5 PARTIAL compare Spe-only across Calm/Relaxed/Modest; qwen2.5 FAIL-CLOSED on FBC.

---

## End

Runner: `/tmp/det_graph_capability/run_discovery.py`  
Independent checks: `/tmp/det_graph_capability/rerun_independent.py`  
Aggregate index: `/tmp/det_graph_capability/aggregate_index.json`
