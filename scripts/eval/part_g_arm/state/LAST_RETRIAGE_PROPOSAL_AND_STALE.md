# Items 3–4 — proposed additions + MT2/H6 stale check (2026-10-28)

**No covered_list.json write. No freeze.**

## 3. Proposed additions (Vu one-step decide)

Add the 9 coverable-now rows: `H12, H19, H20, H21, H22, H27, IX5, IX7, OL7a`.

| metric | current | if all 9 added |
|---|---|---|
| covered / not_covered | 99 / 35 | **108 / 26** |
| `covered_list.json` sha256 | `ebeef244f370688b73e2fd6e94b01c55cdb07a6e8123c43156352255a8a6ed85` | **`16312a209fe11f7a2869c99854ddbc4d5784ae0c5049c4bb9548240d7a3cf5ae`** (append adds to end of `covered`, drop from `not_covered`; matches MM1/MM2 append style) |
| audit form sections / cells | 71 / 232 | **80 / 269** (+9 sections, +37 cells via acceptance `;`-split) |

Hand-audit among the 9: H12, H19, H20, H21, H22, H27, IX5, IX7. Mechanical: OL7a only.

Alternate sha if lists were fully re-sorted: `0645235fe0df85f5901aac07ad531c31c6967c4794f89ff2525b882a9ecd469e` (not the append style).

H12 still needs the trivial empty_team seed before a real run (loader). Not written.

## 4. MT2 / H6 at current pins (pre–Nov 4 refresh)

Both remain in `covered` and are excluded from class rates as `excluded: "stale_pin"` via `errata.stale_pin_rows`.

| row | frozen request-set set | live `get_usage_teammates` / multi @ `champions-reg-mc` ingame | set match? | order match? |
|---|---|---|---|---|
| **H6** | `{Incineroar, Garchomp, Sneasler, Gholdengo, Raichu}` | order `Incineroar, Garchomp, Sneasler, Raichu, Gholdengo` | **yes** | no (Raichu↔Gholdengo) |
| **MT2** | `{Charizard, Garchomp, Sneasler}` | same three | **yes** | yes (unordered) |

Acceptance is **unordered set** scoring → **not content-stale at current pins**. They are preemptively marked stale because the request-set text is hardcoded and the next in-game refresh (Nov 4) can change ranks without a request-set cut.

**Errata options for Vu:** (a) keep `stale_pin` through registration so a mid-window refresh cannot poison scores; (b) remove from `stale_pin_rows` and score until Nov 4, then re-exclude. Recommendation: **(a)** while registration is before Nov 4.

### Scored-row math (99 covered)

| bucket | n |
|---|---|
| `scorable-mechanical` | 40 |
| `mechanical + hand audit` (dual; still rate-scored) | 3 |
| `hand audit` (excluded from rates) | 54 |
| `stale_pin` (MT2, H6; excluded entirely) | 2 |
| **rate-scored rows** | **43** (= 99 − 2 − 54) |

Audit form **includes** MT2/H6: 59 hand-audit rows incl. dual = 54 hand + 3 dual + 2 stale → 71 sections / 232 cells (unchanged by this retriage).
