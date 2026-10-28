# Part 3 — seeds for the 7 unloaded rows

Built from `part3_request_set_v4.md` only. No covered row run to a model. No OL/v4/H27 fixture edits.

## MT4 answer

There is **no** show-candidates / present_candidates tool on the arm. Bound tools are lock/unlock/reset/commit/select/reject/read_*/check_hypothetical/solve_spread/lookups. `read_pending` only reads an existing screen. **MT4 stays not-covered** for the run (CS seed still loads so MS7 works; dry-run sees MT4 loaded).

## Constraint kinds

| seed | predicate | groundedness | mechanical |
|---|---|---|---|
| MT3 (`No Intimidate.`) | `no_intimidate` via `record_constraint` / `build_constraint` | **judgment-only** | `None` (no ban-ability mechanical kind) |
| HC2 (`No weather.`) | `no_weather_ability` | **judgment-only** | `None` (same as H18b fixture tags) |

## HD1 history

`run_turn` prepends `_message_history` as `HumanMessage` / `AIMessage` before the current user turn — same roles as a normal prior turn in one model invoke. Team draft stays empty. Runner plays only `No, Toxapex is not Water/Poison`.

## Seeds (sha256 of committed JSON)

| seed file | sha256 | rows | loaded | complete |
|---|---|---|---|---|
| `cs_pending.json` | `76b7c19ff34281139d9c326024fc0aafeb9952214efb19ad985a67fa7d06e9e5` | MS7, MT4 (load only) | yes | yes |
| `fbc_pending.json` | `4337ddd0dc15d319bbef0bc1ea8cbc9f978c45fa9de1768534b291df3de50af6` | MS4, MU7 | yes | yes |
| `mt3_after_t1.json` | `88c0f9038416e4d87e0e8739ab86901354700e85d716ea5f56fd0c4dc9da44bb` | MT3 | yes | yes |
| `hc2_after_t1.json` | `cc4a8657a7af73a1214d55e0bc5419e0b139023393e7ff8acb54c31d5c474f1d` | HC2 | yes | yes |
| `hd1_history.json` | `331da9c022897b7294549b01643ee7f6201cc82ad2ba4a8c74cde670606dd7c7` | HD1 | yes | yes |

### Justifications

- **cs_pending:** CS with ≥3 options (Pelipper/Toxapex/Corviknight; option 2 = Toxapex), open slot 2, `source=threat` via present_candidates (H27 route).
- **fbc_pending:** Valid FBC for Garchomp (Sand Veil, Sitrus Berry, Jolly, 4 legal moves, fingerprint `seed-fbc-garchomp-v1`).
- **mt3_after_t1:** t1 “No Intimidate.” as judgment-only `no_intimidate`; runner plays t2–t3.
- **hc2_after_t1:** t1 “No weather.” as judgment-only `no_weather_ability`; runner plays t2 only (ASK, no write until pick).
- **hd1_history:** H1 Q + assistant “Toxapex is Poison/Water.”; correction turn only.

### State signatures (summary)

- CS: `pending_kind=candidate_selection`, 3 options, empty draft, open internal slot 1.
- FBC: `pending_kind=full_build_confirmation`, provisional Garchomp, fingerprint match.
- MT3/HC2: empty draft, one judgment-only constraint, no pending.
- HD1: empty draft, `_message_history` length 2 (not part of steering signature).

Dry-run after seeds: **97/97 loaded**.
