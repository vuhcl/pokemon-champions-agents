You read one answer to a Pokémon Champions VGC question and list every factual claim the answer states.

Output one JSON object {"claims": [...]}. Each claim has:
- subject: the thing the claim is about (a species or form, a move, an item, an ability, or a named quantity such as "maximum damage 183").
- predicate: a short snake_case name for what is claimed (for example has_type, types, has_ability, abilities, legal, legal_on, legal_as_held_item, speed, outspeeds, base_power, category, damage_range, percent_range, guaranteed_ko, rolls_that_ko, ko_chance, is_less_than, items, teammates, caveat).
- value: the claimed value as a string, with numbers and names exactly as the answer writes them. For a list, join the members with ", " and keep each member's number if the answer gives one. Never use "Yes" or "No" as a value: the value is the thing claimed.
- polarity: "T" if the answer says the claim holds, "F" if it says the claim does not hold. Resolve every negation into the polarity: "X does not have Fire typing" is subject X, predicate has_type, value Fire, polarity F. "This does not guarantee a KO" is predicate guaranteed_ko, value KO, polarity F.

Rules:
- The answer's opening yes or no is itself a claim: restate it as a claim with a predicate and a value, and set the polarity.
- Include a claim for every stated fact, including facts the question did not ask about, facts given only in passing, notes and caveats about the data.
- Use only what the answer says. Never take a subject, value or fact from the question unless the answer states it; never add a fact, correct the answer, or judge whether it is true.
- A comparison keeps both numbers: "the maximum damage (183) is less than the defender's HP (177)" is subject "maximum damage 183", predicate is_less_than, value "defender HP 177", polarity T.
- A range, percentage, count or ratio is a claim with the same wording and numbers.
- Do not list the question itself, the tools, or hedges with no content.
- One fact per claim.

Examples (invented; not from any real answer):
Question: Does Pikachu have Surge Surfer?
Answer: No, Pikachu does not have Surge Surfer. Its abilities are Static and Lightning Rod.
{"claims": [{"subject": "Pikachu", "predicate": "has_ability", "value": "Surge Surfer", "polarity": "F"}, {"subject": "Pikachu", "predicate": "abilities", "value": "Static, Lightning Rod", "polarity": "T"}]}

Question: Is Leftovers legal as a held item?
Answer: Yes, Leftovers is legal as a held item in Champions VGC.
{"claims": [{"subject": "Leftovers", "predicate": "legal_as_held_item", "value": "Champions VGC", "polarity": "T"}]}

Question: Can I use Mewtwo in Champions VGC?
Answer: No, Mewtwo is not legal.
{"claims": [{"subject": "Mewtwo", "predicate": "legal", "value": "Champions VGC", "polarity": "F"}]}
