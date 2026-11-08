# FU74 point diff (keys_fu72 IX rows ↔ keys_fu74)

Source draft: `ix_keys_draft_2026-11-07.md`. Any key change not in the draft is a bug.

## IX1
- pass_criteria_changed: False (old unreachable pending cut)
- old_point_count: 4
- new_point_count: 5
- unreachable_reason old: 'pending key cut (find_by_effect shipped in #393 / ix_tools_v1)'
- unreachable_reason new: ''
- expected_tools old → new: `get_move_static` → `find_by_effect;get_move_static`
- optional_tools old → new: `` → `get_type_effectiveness;get_abilities;describe`

### Old (keys_fu72 pending cut)
- `p1`: Fake Out priority 3 > Follow Me 2 (and Rage Powder same class)
- `p2`: FAIL if recommends Follow Me/Rage Powder as counter
- `p3`: PASS = Fake Out outprioritizes redirect or valid non-redirect counters
- `p4`: assume counter=redirect|block

### New (keys_fu74 draft)
- `p1`: The arm states what it means by "counter" (redirect it, or block it); the stated assumption is scored.
- `p2` [tool-backed]: The redirection moves it names come from the tool (Follow Me, Rage Powder); it names no other move as redirection.
- `p3` [tool-backed]: It gives the priorities from a tool: Fake Out 3 against Follow Me and Rage Powder 2.
- `p4`: The conclusion is that redirection used the same turn does not counter Fake Out, because Fake Out moves first. Recommending Follow Me or Rage Powder as the counter fails.
- `p5` [tool-backed] [conditional]: Not required: naming other counters. If it names any, each is a real counter backed by a tool result or describe in that turn (for example Protect, Detect, Armor Tail, Dazzling, Queenly Majesty, a Ghost-type target). A named non-counter fails (Endure, Mycelium Might, Stall).

## IX5
- pass_criteria_changed: True (old unreachable pending cut)
- old_point_count: 5
- new_point_count: 5
- unreachable_reason old: 'pending key cut (find_by_effect shipped in #393 / ix_tools_v1)'
- unreachable_reason new: ''
- expected_tools old → new: `find_species` → `find_by_effect;find_species`
- optional_tools old → new: `get_abilities` → `get_abilities;check_species_ability;check_species_legal`

### Old (keys_fu72 pending cut)
- `p1`: Assume punish=blocked|reflected|boosted
- `p2`: set rule
- `p3`: separate buckets
- `p4`: verify holders vs legality
- `p5`: set-scoring

### New (keys_fu74 draft)
- `p1`: The arm states what "punish" means, and the definition is about what the Pokemon does when an opposing Intimidate hits it: the effect is blocked, reflected, or turned into a gain (blocked, reflected or boosted, or a stated variant of those). The stated definition is scored. A definition that is not about the response to being Intimidated (for example "Pokemon that also have Intimidate") fails this point.
- `p2`: The arm splits its answer into separate buckets by mechanism (for example blocked, reflected, boosted); it does not give one mixed list. The buckets are the arm's own; no fixed membership.
- `p3` [tool-backed]: Each ability it puts in a bucket does what the bucket says to Intimidate, backed by that ability's description from a tool result in that turn (find_by_effect or get_abilities), whatever definition the arm stated. An ability in the wrong bucket, or one that does nothing to Intimidate, fails. Intimidate itself fails: its description lowers adjacent opponents' Attack, with no immunity, reflection or boost, so "Intimidate counters Intimidate" is a false claim. Rattled counts as boosted (Vu, 2026-11-07).
- `p4` [tool-backed]: Each Pokemon it names as a holder is legal and can have that ability (find_species with the ability, or check_species_ability). A named holder that cannot have the ability fails.
- `p5` [conditional]: Not required: an exhaustive list of abilities or holders. If the arm states a count or says the list is complete, it carries a source label and matches the tool result it cites.

## IX7
- pass_criteria_changed: True (old unreachable pending cut)
- old_point_count: 4
- new_point_count: 6
- unreachable_reason old: 'pending key cut (get_type_effectiveness + find_by_effect shipped in #393 / ix_tools_v1)'
- unreachable_reason new: ''
- expected_tools old → new: `find_species` → `get_type_effectiveness;find_by_effect;find_species`
- optional_tools old → new: `` → `get_abilities;check_species_legal;check_item_legal`

### Old (keys_fu72 pending cut)
- `p1`: safe=no damage: Flying / Levitate / Telepathy / Earth Eater
- `p2`: examples+counts with source label
- `p3`: resist≠safe unless definition says so
- `p4`: set matches stated definition

### New (keys_fu74 draft)
- `p1`: The arm states what "safe" means (takes no damage from the partner's Earthquake); the stated definition is scored. A resisting type is not safe unless its definition says so.
- `p2` [tool-backed]: Every type, ability or item it names as safe really gives no damage from Earthquake under that definition, backed by a tool result in that turn (get_type_effectiveness or find_by_effect). Naming a resisting type or Friend Guard as safe fails.
- `p3` [tool-backed]: Every species it names as a safe partner is legal and has the type, or can have the ability (find_species). An item it names is legal in Champions (check_item_legal) and the named holder can hold it. A named partner or item that does not meet the check fails.
- `p4` [tool-backed]: Examples and any counts come from tool results with a source label (Showdown text for item and move descriptions).
- `p5`: The set it gives matches its stated definition (a member the definition excludes, or a member whose immunity is conditional without the condition stated, fails; for example Levitate under Gravity).
- `p6` [conditional]: Not required: finding all of Flying, Levitate, Earth Eater, Eelevate, Telepathy or Air Balloon (Vu, 2026-11-07).

