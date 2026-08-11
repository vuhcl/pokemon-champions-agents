# CLI stress Tracks A–D — discovery (2026-08-10)

**Status:** Ran against real `compile_cli_graph` + `handle_line` (same path as
`python -m recommender`). Live Ollama (`qwen2.5:7b`) used for Track A bootstrap
intake. Stub parsers used for deterministic B–D probes. Runner:
`artifacts/cli_stress_runner_2026-08-10.py`; raw JSON:
`artifacts/cli_stress_results_2026-08-10.json`.

## Method

Lock-sequence / meta probes via `handle_line`, not hand-typed REPL transcripts.
Each track records phase, pending kind, locked species, and presentation heads.

## Track A — Happy path + Ollama

**Probe:** free-form `"you pick a rain team starting with Archaludon"` with real
Ollama parser; then autopilot ordinal/`yes` locks.

**Findings:**

1. **Ollama smoke passed.** Parser configured; bootstrap advanced to
   `candidate_selection`.
2. **Parser often prefers Pelipper for “rain …” phrasing** over Archaludon when
   both direction and anchor compete — product-acceptable for delegated rain, but
   not a strict Archaludon lock-sequence. Explicit Rain+Archaludon is covered by
   the unit regression `test_explicit_anchor_survives_mismatched_direction_filter`
   (Fork A fix: named anchor is not filtered out by direction role mismatch).
3. **Reached 5 locks** (`Pelipper`, `Garchomp`, `Milotic`, `Delphox-Mega`,
   `Hydreigon`) in `multi_locked` with a live `candidate_selection` still pending
   (not dead-ended). Did **not** reach `complete` in the autopilot budget —
   several candidates fail provisional refine (`incomplete_build` on moves) and
   are skipped after rediscovery.
4. **Calc degradation is routine** (`calc_incomplete` on coverage / verification).
   Under ADR-029, `multi_locked` stays fail-closed (`pending_presentation=None`) when
   team review is unavailable — CLI/autopilot can dead-end at 2+ locks. That usability
   gap is real backlog (ADR-029 deferred “support/shared-only banner”), not something
   to paper over with unlabeled continue-on-degraded discovery.

**Verdict:** Partial happy path. Live Ollama works; full 6-lock autopilot is
blocked by provisional-build completeness for some species, not by Fork A vocab.

## Track B — Ctrl+C / resume

**Probe:** bootstrap to `candidate_selection`, close checkpointer, reopen same
thread DB, continue with `1`.

**Findings:** Pending kind and options survive resume; continue advances to
`full_build_confirmation`. Matches ADR-010 session durability intent.

**Verdict:** Pass.

## Track C — Adversarial / meta

| Probe | Result |
|-------|--------|
| OOR ordinal `99` | Stays on `candidate_selection`; `Didn't catch that.` prefix |
| `:new Archaludon` | **Not** meta-`:new` (exact strip match only); treated as free-form pending input → unmatched |
| Exact `:new` | Mints new `team-…` thread; returns to `bootstrap_intake` |
| Typo anchor `Archaludonn` | Fail-closed intake notice; no inventing species |
| No provider | Fix hint present; **no** unmatched prefix |

**Verdict:** Pass. `:new Archaludon` policy matches plan (exact meta only).

## Track D — `multi_locked` + `complete` via real CLI path

**Probe:** stub Rain+Archaludon → lock autopilot toward six.

**Findings:**

1. After Fork A direction/anchor fix, Archaludon + Pelipper bootstrap presents
   correctly (`bulky_special_attacker` + `rain_setter`).
2. Enters `multi_locked` after second lock; asks `completion_preference` then
   candidates.
3. Autopilot reached 3 locked with further candidates available; did not hit
   `complete` in budget (same refine/skip pressure as Track A).
4. Phase bucket is a single `multi_locked` for 2+ locks — no extra phase names.

**Verdict:** Phase routing pass; terminal `complete` not reached under autopilot
(documented ceiling: incomplete provisional builds).

## Bugs found and fixed during A–D

| Bug | Fix |
|-----|-----|
| Rain + explicit Archaludon → “Couldn't resolve starting role” (direction filter dropped kit identity) | Exempt explicit anchor from requested-role filter (`bootstrap.py`) |
| Single TW mechanism short-circuited Pelipper to `tailwind_setter` before Rain Track 1 | Defer single speed-control until after non-speed Track 1 |
| Threat-only partners presented with `target_role_decision=None` → refine dead-end | Kit identity fallback (`slot_fill_kit_role_policy`) on annotate/merge/refine |
| Failed refine left `pending_presentation=None` | Conditional graph edge: refine failure → `route_team_phase` rediscovery |

**Reverted (not shipped):** an interim change that continued `multi_locked` discovery
after calc-unavailable review without ADR-029 row-level honesty markers
(`estimate_kind` / degradation tokens / sort firewall). Restored hard-stop +
`test_calc_evidence_failure_aborts_multi_discovery_without_partial_ranking`. Proper
labeled support-only / banner path remains backlog.

## Out of scope / known ceilings

- Autopilot rarely reaches lock 6 when many top candidates have incomplete
  movesets under current refine — product fix belongs to Tier-3 completeness,
  not Fork A vocabulary.
- Live calc `damage[…] === 0` noise remains; `multi_locked` calc-unavailable
  usability (honest labeled continue) is deferred per ADR-029, not silently shipped.
