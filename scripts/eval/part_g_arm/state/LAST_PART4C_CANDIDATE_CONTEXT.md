# 4c — candidate discovery: context report (BEFORE build)

Stop rule check: producer uses `query_threat_counters` + `present_candidates` / `run_slot_fill_terminal` with pinned usage + localhost calc — **no LLM**, **no live web**. `allow_live=False` required. No change outside `state/` for the arm wrapper.

## Context the producer needs

| input | where it comes from | empty team | partial team (≥1 locked) |
|---|---|---|---|
| open `slot_index` | tool arg | required | required |
| `regulation` | state / active_regulation | yes | yes |
| **anchor** (locked species+build) | first `all_locked` slot | **none** → CLI bypasses to `fill_team_draft` / bootstrap | yes (single_locked path) |
| role shape / support needs | derived from anchor | n/a | from `classify_anchor_role` + `query_support_needs` |
| threat counters | `query_threat_counters(anchor, …)` | n/a without anchor | calc + usage pins |
| locked_contexts | `collect_locked_anchor_contexts` | empty | all fully locked slots |
| constraints | `state["constraints"]` | optional filter | soft/hard filter on discovery |
| rejected list | `banned_profiles_from_rejected` | honor if non-empty | honor (MT4) |
| archetype | state archetype Attr | optional theme | optional |
| team_completion_preference | state | optional | multi_locked diversify |
| bootstrap intake | LLM bootstrap | **CLI uses this for empty** | not required |

## What `show_candidates` would pass

| start | pass into producer | return |
|---|---|---|
| **Empty team (H17/H18)** | No all_locked anchor → CLI does **not** call `query_threat_counters`; it routes `fill_team_draft` / bootstrap. Arm cannot supply bootstrap (LLM — stop rule). | **Blocked without an explicit anchor species argument or a non-bootstrap empty-team producer.** Rows H17/H18 not fully passable by show_candidates alone. |
| **Partial (1 fully locked + open slot)** | Mirror `build_anchored_slot_fill_context` + annotate + `run_slot_fill_terminal` with `banned_profiles` from rejected; `allow_live=False`. | Writes `candidate_selection` pending (options with species, source, evidence from producer). |
| **Multi locked** | Prefer `discover_multi_locked` / diverse select path (same as CLI). | Same pending shape. |
| **No candidates** | Producer empty / degraded with empty list | Refuse or return empty options; **do not write team**. |

## Pins / variance

- Usage: `data/usage/champions-reg-mc.ingame_doubles.v1.json` / showdown doubles pin (`63bcefe4…` / `31af0801…`).
- Legality snapshot; calc service for verified matchups (degraded → static types).
- Determinism: same team + pins + calc → same order; two calls must match. Calc downtime → degraded status (must be labeled).

## Registration facts (preview)

- Tool-determined: option identity, order, source, evidence strings from producer.
- Model-determined: when to call; narration.
- LLM call: **none** expected.

## Rows

| row | without bootstrap? |
|---|---|
| MT4 | yes (CS seed + show after reject) |
| H25 / H26 | yes (fixtures have locked members) |
| H17 / H18 | **no** — empty start needs bootstrap or extra empty-team producer (report to Vu if we cannot add without LLM) |

Next: build `show_candidates` for the single/multi-locked path; document empty-team limitation in the tool commit.
