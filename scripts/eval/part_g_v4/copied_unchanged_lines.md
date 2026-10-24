# copied_unchanged: what counts as a "line" (defined 2026-10-23, before any share was computed)

Vu's definition (amendment, 2026-10-23): a claim is `copied_unchanged` when the final_text contains the **entire text line from the tool result that
carries the claim**, verbatim after whitespace and case normalisation. The extractor computes the flag from the item's transcript; the scorer only reads it.

**Normalisation.** `norm(s)` = lowercase, runs of whitespace collapsed to one space, ends stripped. Nothing else is normalised: markdown, punctuation,
brackets and percent signs must match as written. The line's text must occur in `norm(final_text)` as a substring.

**Carrier lines, per tool.** A tool result is JSON; only these parts are lines:

| Tool | Lines |
|---|---|
| `get_typing` | each string entry of `types` |
| `get_abilities` | each string entry of `abilities` |
| `check_species_ability` | each string entry of `species_abilities` |
| `check_species_legal`, `check_item_legal` | `note` (a string) |
| `get_move_static` | the string fields `type` and `category` (`base_power` is an integer, not a line) |
| `get_speed` | `note` (a string). The `speed` stat is an integer field, not a line, so no line carries a Speed stat. |
| `calc_damage` | the string fields `ko_text` and `calc_desc`, and `kochance.text`. The roll list, range, HP and counts are numbers, not lines. |
| `get_usage_items` | each entry of `items`, rendered as one line `"{name} {pct}"` (pct written as the JSON number) |
| `get_usage_teammates` | each entry of `rows`, rendered as one line `"{name} {conditional_pct}"`, or `"{name}"` when `conditional_pct` is null (in-game lists); each string entry of `caveats` |
| `no_lookup_needed` | none |

A string field named `message` or `note` in any result is also a line. Nothing else is.

**When a line carries a claim.** The claim's *value strings* must all occur in the line, matched on token boundaries after `norm`:

| Claim kind | Value strings |
|---|---|
| `type_list_member`, `ability_list_member` | the name |
| `common_items`, `teammates` (membership) | the name |
| the same kinds on the usage-percentage line (`name=pct`) | the name and the percentage as the answer wrote it |
| `*_rank` (`name=rank`) | the name and the rank number |
| `speed_stat` | the number |
| `damage_range` | low and high |
| `percent_of_hp` | the two percentages |
| `ko_chance` | the percentage |
| `nhko`, `chance_nhko` | `{n}hko` (and the percentage for `chance_nhko`) |
| `category`, `move_type`, `base_power` | the value |
| `labelled_value` | the number |
| every other kind (verdicts such as `has_type`, `has_ability`, `item_legal`, `species_legal`, `outspeed`, `faster`, `guaranteed_ko`; and `ko_count`, `ko_needed`, `ko_threshold`, `hp_arithmetic`, `speed_margin`, `set:*`, `*_exact`) | none: no line carries them, so they are never `copied_unchanged` |

The flag is true iff the claim has value strings and some carrier line contains all of them and is itself contained in the final_text. This replaces the
earlier verbatim-value definition and its "no relation" clause. The definition is not widened after the shares are seen; a small share is reported as measured.
