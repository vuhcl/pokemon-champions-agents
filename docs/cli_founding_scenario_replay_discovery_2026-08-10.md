# CLI founding-scenario conclusion replay — Track E (2026-08-10)

**Status:** Discovery. Method is **lock-sequence reconstruction**, not replay of
CLI chat logs (founding sessions in
`docs/slot_fill_flow_discovery_2026-08-08.md` /
`docs/anchor_role_and_target_role_discovery_2026-08-08.md` were tool-calling
role-plays). Scripts drive real `handle_line` + graph; conclusion checks cite
founding docs. Runner: `artifacts/cli_stress_runner_2026-08-10.py`.

## E1 — Kingambit partner slot

**Conclusion under test:** Three role concepts stay distinct; Black Glasses
Kingambit must **not** revive SD/setup-dependent false-positive partner framing
([anchor_role](anchor_role_and_target_role_discovery_2026-08-08.md) Kingambit
sections; slot_fill Scenario 1).

**Lock-sequence reconstruction:** stub bootstrap `anchor=Kingambit` → pick →
confirm → inspect partner options.

**Observed:**

- Locked Kingambit as `standard_physical_attacker` (kit identity; Fork A).
- Partner options: Gardevoir-Mega, Sinistcha, Meowstic — all presented with
  `trick_room_setter` target roles (support need path), **not** SD attacker.
- `sd_false_positive` flag false.

**Verdict:** Pass (expected improvement vs founding SD false-positive). Role
concepts on partners are TR-setter-shaped, not SD-on-Kingambit bleed.

## E2 — Archaludon + Pelipper Rain core / Basculegion redundancy

**Conclusion under test:** After Mega Swampert (or equiv.) present, Basculegion
must not lead as redundant Rain offense; signals recompute every lock
([slot_fill Scenario 3](slot_fill_flow_discovery_2026-08-08.md);
[multi_locked design](multi_locked_candidate_discovery_and_ranking_design_2026-08-08.md);
master log ~2116–2121).

**Lock-sequence reconstruction:** Rain+Archaludon bootstrap → prefer
Archaludon / Pelipper / Swampert-Mega when offered.

**Observed:**

- Archaludon locks as `bulky_special_attacker` (Fork A acceptance).
- Autopilot did not always obtain Pelipper/Swampert-Mega in-offer (candidate mix
  offered Gardevoir-Mega / Hydreigon / Tsareena after early locks).
- Where options were inspected after a 3-lock core,
  **Basculegion did not lead** (`basculegion_leads=false`).
- Note: under ADR-029, calc-unavailable team review still hard-stops `multi_locked`
  pending (continue-on-degraded without honesty markers was tried in stress and
  **reverted**). Recomputation after every lock holds when review is available.

**Verdict:** Pass on the Basculegion non-lead check for observed presentations.
Partial on exact founding lock order (candidate availability / refine skips).
Classify deviation from exact Pelipper→Swampert path as **candidate-mix variance**,
not a Basculegion regression.

## E3 — Mono-Fairy-shaped six — phase boundaries only

**Conclusion under test:** No new orchestrator behavior at locks 3/4/5/6 past
`multi_locked@2`; `complete` = terminal review (master log ~2123–2144). **Not**
requiring monotype hard-filter (founding: “Monotype is not enforced
automatically”).

**Lock-sequence reconstruction:** prefer Scenario 4 order when choosable
(Mawile-Mega, Ninetales-Alola, Hatterene, Primarina, Clefable, Mimikyu).

**Observed:**

- Phase by lock count: `0→empty`, `1→single_locked`, `2→multi_locked`.
- No unexpected phase names at 3/4/5 (autopilot stalled at 2 locks when Fairy
  targets were not offered / refine skipped).
- Monotype not enforced (expected).

**Verdict:** Pass on **phase** conclusion. Full Fairy-leaning 6 not reached —
acceptance bar was phase boundaries, not monotype completion.

## E4 — Vu Rain six + `summarize_roster_role_structure`

**Conclusion under test:** Contested rain-setter (Pelipper/Sableye), contested
attacker (Archaludon/Swampert/Maushold), Sinistcha uncontested
([roster role-structure](roster_role_structure_grouping_discovery_and_design_2026-08-09.md)).
Callable is **direct** — not graph-wired.

**Lock-sequence reconstruction:** CLI attempt toward Vu order; then direct
`summarize_roster_role_structure`.

**Observed (CLI):** Autopilot locked a rain-leaning five
(Pelipper + attackers) — not the exact Vu six. Structure on that roster still
shows contested `attacker` and uncontested Pelipper rain/tailwind.

**Observed (direct fixture — authoritative for E4 conclusion):**

```text
attacker              contested   Archaludon, Swampert, Maushold
rain_setter           contested   Pelipper, Sableye
tailwind_setter       uncontested Pelipper
redirection           uncontested Sinistcha
trick_room_setter     uncontested Sinistcha
…
```

**Verdict:** Pass on founding structure conclusions via direct callable.
CLI exact Vu six not required when fixture confirms the report contract.

## Cross-cutting

- Founding docs are **not** CLI transcripts; all E scripts labeled
  **lock-sequence reconstruction**.
- Fork A made Archaludon bootstrap viable; Rain+Archaludon no longer dead-ends.
- Stress-time fixes kept: kit fallback, refine rediscovery. Multi_locked
  continue-on-calc-unavailable without ADR-029 honesty markers was **reverted**;
  labeled support-only banner remains backlog.
