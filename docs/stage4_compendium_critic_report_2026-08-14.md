# Stage 4 — Critic reports (no persist)

Construct + `critique_role_ranking` only. **No** `persist_approved` / `data/roles/*.v1.json` writes. Each cluster needs explicit sign-off before any follow-up persist task.

Pool size: 314.

---

## Cluster 1 — Staleness rebuilds (SD, NP, Trick Room)

### `swords_dance_attacker`

- **Admitted:** disk 26 → live **54** (rejected 47)
- **Tiers:** disk {'Good': 9, 'Excellent': 7, 'Acceptable': 10} → live **{'Excellent': 3, 'Good': 40, 'Acceptable': 11}**
- **Critic:** approved=True flags=0

**Members (live)**

- **Excellent** (3): Aegislash, Kingambit, Scrafty-Mega
- **Good** (40): Absol, Absol-Mega, Banette-Mega, Beedrill-Mega, Blaziken-Mega, Ceruledge, Charizard-Mega-X, Chesnaught-Mega, Decidueye, Decidueye-Hisui, Diggersby, Excadrill-Mega, Feraligatr, Feraligatr-Mega, Gallade, Gallade-Mega, Garchomp, Garchomp-Mega, Gliscor, Hawlucha-Mega, Heracross-Mega, Kleavor, Leafeon, Lopunny-Mega, Lucario-Mega, Lycanroc-Dusk, Lycanroc-Midnight, Mawile-Mega, Mimikyu, Pangoro, Pinsir-Mega, Quaquaval, Rhyperior, Samurott-Hisui, Scizor, Scizor-Mega, Skarmory-Mega, Sneasler, Tinkaton, Torterra
- **Acceptable** (11): Ariados, Beartic, Falinks-Mega, Lucario, Lycanroc, Overqwil, Qwilfish, Samurott, Talonflame, Toxicroak, Weavile

**Disk → live diff**

- Tier changes among survivors: **16**
  - Absol-Mega: Excellent → Good — setup calc/membership re-eval / tier 'Excellent' → 'Good' (score=1.106, branches=A)
  - Aegislash: Good → Excellent — setup calc/membership re-eval / tier 'Good' → 'Excellent' (score=1.406, branches=A+B)
  - Blaziken-Mega: Excellent → Good — setup calc/membership re-eval / tier 'Excellent' → 'Good' (score=1.221, branches=A)
  - Ceruledge: Acceptable → Good — setup calc/membership re-eval / tier 'Acceptable' → 'Good' (score=0.933, branches=A)
  - Charizard-Mega-X: Acceptable → Good — setup calc/membership re-eval / tier 'Acceptable' → 'Good' (score=1.154, branches=A)
  - Decidueye: Acceptable → Good — setup calc/membership re-eval / tier 'Acceptable' → 'Good' (score=0.981, branches=A)
  - Gallade-Mega: Excellent → Good — setup calc/membership re-eval / tier 'Excellent' → 'Good' (score=1.067, branches=A)
  - Garchomp-Mega: Acceptable → Good — setup calc/membership re-eval / tier 'Acceptable' → 'Good' (score=1.157, branches=B)
  - Heracross-Mega: Acceptable → Good — setup calc/membership re-eval / tier 'Acceptable' → 'Good' (score=1.117, branches=A)
  - Leafeon: Acceptable → Good — setup calc/membership re-eval / tier 'Acceptable' → 'Good' (score=0.944, branches=A)
  - Mawile-Mega: Excellent → Good — setup calc/membership re-eval / tier 'Excellent' → 'Good' (score=1.199, branches=A)
  - Mimikyu: Excellent → Good — setup calc/membership re-eval / tier 'Excellent' → 'Good' (score=1.177, branches=A+B)
  - Scizor: Acceptable → Good — setup calc/membership re-eval / tier 'Acceptable' → 'Good' (score=1.001, branches=A)
  - Scizor-Mega: Acceptable → Good — setup calc/membership re-eval / tier 'Acceptable' → 'Good' (score=0.935, branches=A)
  - Scrafty-Mega: Acceptable → Excellent — setup calc/membership re-eval / tier 'Acceptable' → 'Excellent' (score=1.382, branches=A+B)
  - Skarmory-Mega: Excellent → Good — setup calc/membership re-eval / tier 'Excellent' → 'Good' (score=1.013, branches=A)
- Newly admitted: **29**
  - [Acceptable] Ariados
  - [Good] Banette-Mega
  - [Acceptable] Beartic
  - [Good] Chesnaught-Mega
  - [Good] Decidueye-Hisui
  - [Good] Diggersby
  - [Acceptable] Falinks-Mega
  - [Good] Gallade
  - [Good] Gliscor
  - [Good] Hawlucha-Mega
  - [Good] Kleavor
  - [Good] Lopunny-Mega
  - [Acceptable] Lucario
  - [Good] Lucario-Mega
  - [Acceptable] Lycanroc
  - [Good] Lycanroc-Dusk
  - [Good] Lycanroc-Midnight
  - [Good] Pangoro
  - [Good] Quaquaval
  - [Acceptable] Qwilfish
  - [Good] Rhyperior
  - [Acceptable] Samurott
  - [Good] Samurott-Hisui
  - [Good] Sneasler
  - [Acceptable] Talonflame
  - [Good] Tinkaton
  - [Good] Torterra
  - [Acceptable] Toxicroak
  - [Acceptable] Weavile
- Dropped: **1**
  - [Good] Blaziken
- Payoff set changed (survivors): **25**
- Modal payoff flips: **15**
  - Absol: suckerpunch → closecombat
  - Absol-Mega: suckerpunch → knockoff
  - Aegislash: shadowsneak → poltergeist
  - Ceruledge: shadowsneak → bitterblade
  - Decidueye: suckerpunch → leafblade
  - Feraligatr: aquajet → liquidation
  - Feraligatr-Mega: aquajet → doubleedge
  - Garchomp-Mega: stompingtantrum → dragonclaw
  - Heracross-Mega: lunge → closecombat
  - Kingambit: suckerpunch → kowtowcleave
  - Leafeon: quickattack → leafblade
  - Mawile-Mega: suckerpunch → ironhead
  - Overqwil: gunkshot → barbbarrage
  - Scizor: bulletpunch → bugbite
  - Scizor-Mega: bulletpunch → bugbite

**Critic flags (full)**

_No flags._

### `nasty_plot_attacker`

- **Admitted:** disk 6 → live **23** (rejected 50)
- **Tiers:** disk {'Excellent': 3, 'Good': 3} → live **{'Excellent': 2, 'Good': 14, 'Acceptable': 7}**
- **Critic:** approved=True flags=0

**Members (live)**

- **Excellent** (2): Gengar-Mega, Raichu-Mega-Y
- **Good** (14): Alakazam, Alakazam-Mega, Delphox-Mega, Froslass-Mega, Houndoom-Mega, Hydrapple, Lucario-Mega, Meowstic-F-Mega, Raichu-Alola, Salazzle, Simipour, Slowbro-Mega, Zoroark, Zoroark-Hisui
- **Acceptable** (7): Infernape, Lucario, Meowstic-M-Mega, Ninetales, Ninetales-Alola, Raichu-Mega-X, Simisear

**Disk → live diff**

- Tier changes among survivors: **4**
  - Alakazam-Mega: Excellent → Good — setup calc/membership re-eval / tier 'Excellent' → 'Good' (score=1.071, branches=A)
  - Delphox-Mega: Excellent → Good — setup calc/membership re-eval / tier 'Excellent' → 'Good' (score=1.028, branches=A)
  - Meowstic-F-Mega: Excellent → Good — setup calc/membership re-eval / tier 'Excellent' → 'Good' (score=0.899, branches=A)
  - Raichu-Mega-Y: Good → Excellent — setup calc/membership re-eval / tier 'Good' → 'Excellent' (score=1.180, branches=A)
- Newly admitted: **17**
  - [Good] Alakazam
  - [Excellent] Gengar-Mega
  - [Good] Hydrapple
  - [Acceptable] Infernape
  - [Acceptable] Lucario
  - [Good] Lucario-Mega
  - [Acceptable] Meowstic-M-Mega
  - [Acceptable] Ninetales
  - [Acceptable] Ninetales-Alola
  - [Good] Raichu-Alola
  - [Acceptable] Raichu-Mega-X
  - [Good] Salazzle
  - [Good] Simipour
  - [Acceptable] Simisear
  - [Good] Slowbro-Mega
  - [Good] Zoroark
  - [Good] Zoroark-Hisui
- Dropped: **0**
- Payoff set changed (survivors): **6**
- Modal payoff flips: **3**
  - Alakazam-Mega: psychic → expandingforce
  - Froslass-Mega: frostbreath → shadowball
  - Meowstic-F-Mega: psychic → expandingforce

**Critic flags (full)**

_No flags._

### `trick_room_setter`

- **Admitted:** disk 38 → live **28** (rejected 28)
- **Tiers:** disk {'Acceptable': 17, 'Good': 18, 'Excellent': 3} → live **{'Acceptable': 12, 'Good': 14, 'Excellent': 2}**
- **Critic:** approved=True flags=0

**Members (live)**

- **Excellent** (2): Farigiraf, Oranguru
- **Good** (14): Aromatisse, Chandelure, Cofagrigus, Gourgeist, Gourgeist-Large, Gourgeist-Small, Hatterene, Mimikyu, Runerigus, Sinistcha, Slowbro, Slowking, Spiritomb, Trevenant
- **Acceptable** (12): Armarouge, Audino, Audino-Mega, Gallade, Klefki, Malamar, Mr. Rime, Musharna, Reuniclus, Slowbro-Galar, Slowking-Galar, Wyrdeer

**Disk → live diff**

- Tier changes among survivors: **0**
- Newly admitted: **0**
- Dropped: **10**
  - [Good] Banette-Mega
  - [Good] Chandelure-Mega
  - [Acceptable] Chimecho-Mega
  - [Good] Espeon
  - [Excellent] Gallade-Mega
  - [Acceptable] Gardevoir-Mega
  - [Acceptable] Malamar-Mega
  - [Acceptable] Meowstic
  - [Good] Polteageist
  - [Acceptable] Slowbro-Mega
- Payoff set changed (survivors): **0**
- Modal payoff flips: **0**

**Critic flags (full)**

_No flags._

---

## Cluster 2 — Fresh setup builds (CM, BU, DD, ID+BP)

### `calm_mind_attacker`

- **Admitted:** **49** (rejected 32)
- **Tiers:** **{'Excellent': 8, 'Good': 30, 'Acceptable': 11}**
- **Critic:** approved=True flags=0

**Members**

- **Excellent** (8): Armarouge, Chandelure-Mega, Drampa-Mega, Floette-Eternal, Gardevoir-Mega, Hatterene, Primarina, Typhlosion-Hisui
- **Good** (30): Alakazam, Alakazam-Mega, Aromatisse, Aurorus, Chandelure, Chimecho-Mega, Clefable, Clefable-Mega, Delphox-Mega, Drampa, Espeon, Farigiraf, Florges, Glaceon, Jolteon, Lucario-Mega, Meowstic-F-Mega, Meowstic-M-Mega, Mr. Rime, Polteageist, Reuniclus, Slowbro, Slowbro-Galar, Slowbro-Mega, Slowking, Slowking-Galar, Sylveon, Vaporeon, Zoroark, Zoroark-Hisui
- **Acceptable** (11): Alcremie, Audino-Mega, Cofagrigus, Espathra, Klefki, Lucario, Musharna, Ninetales, Sinistcha, Spiritomb, Umbreon

**Critic flags (full)**

_No flags._

### `bulk_up_attacker`

- **Admitted:** **37** (rejected 26)
- **Tiers:** **{'Excellent': 5, 'Good': 29, 'Acceptable': 3}**
- **Critic:** approved=True flags=0

**Members**

- **Excellent** (5): Blaziken-Mega, Hawlucha-Mega, Medicham-Mega, Pangoro, Starmie-Mega
- **Good** (29): Annihilape, Barbaracle-Mega, Beartic, Ceruledge, Chesnaught-Mega, Conkeldurr, Corviknight, Crabominable-Mega, Decidueye-Hisui, Diggersby, Emboar-Mega, Falinks-Mega, Gallade-Mega, Heracross-Mega, Krookodile, Lucario-Mega, Lycanroc-Midnight, Machamp, Mimikyu, Palafin, Passimian, Pinsir-Mega, Quaquaval, Scrafty-Mega, Swampert-Mega, Tauros-Paldea-Aqua, Tauros-Paldea-Blaze, Tauros-Paldea-Combat, Toxicroak
- **Acceptable** (3): Emboar, Lycanroc, Sableye-Mega

**Critic flags (full)**

_No flags._

### `dragon_dance_attacker`

- **Admitted:** **12** (rejected 19)
- **Tiers:** **{'Excellent': 3, 'Good': 9}**
- **Critic:** approved=True flags=0

**Members**

- **Excellent** (3): Charizard-Mega-X, Feraligatr, Feraligatr-Mega
- **Good** (9): Dragapult, Dragonite, Flapple, Gyarados, Gyarados-Mega, Scrafty-Mega, Tyranitar, Tyranitar-Mega, Tyrantrum
- **Acceptable** (0): (none)

**Critic flags (full)**

_No flags._

### `iron_defense_body_press`

- **Admitted:** **24** (rejected 15)
- **Tiers:** **{'Excellent': 2, 'Good': 18, 'Acceptable': 4}**
- **Critic:** approved=True flags=0

**Members**

- **Excellent** (2): Chesnaught-Mega, Kommo-o
- **Good** (18): Aggron-Mega, Avalugg, Avalugg-Hisui, Bastiodon, Cofagrigus, Corviknight, Falinks-Mega, Forretress, Garganacl, Metagross-Mega, Orthworm, Rhyperior, Runerigus, Sandaconda, Skarmory-Mega, Slowbro-Mega, Steelix-Mega, Torterra
- **Acceptable** (4): Appletun, Mudsdale, Slowbro, Steelix

**Doc note (paste-ready):** Iron Defense + Body Press — permanent Stage 3 scope boundary. ID+BP payoff stays fixed to Body Press by design. Body Press damage is defined by the user's Defense stat, not by choosing among attacking moves, so Stage 1 per-defender best-move selection and Stage 2 plural payoff_moves / payoff_targets do not apply. The category keeps the single-string / fixed-payoff path (payoff_move_id: bodypress). This is an intentional permanent boundary, not an oversight and not deferred work.


**Critic flags (full)**

_No flags._

---

## Cluster 3 — Lost-support rebuilds (Tailwind, Sleep, Screens)

### `tailwind_setter`

- **Admitted:** **23** (rejected 4)
- **Tiers:** **{'Good': 9, 'Acceptable': 13, 'Excellent': 1}**
- **Critic:** approved=True flags=0

**Members**

- **Excellent** (1): Whimsicott
- **Good** (9): Aerodactyl, Aerodactyl-Mega, Dragonite-Mega, Noivern, Pidgeot-Mega, Skarmory-Mega, Staraptor-Mega, Talonflame, Volcarona
- **Acceptable** (13): Altaria, Altaria-Mega, Corviknight, Decidueye, Decidueye-Hisui, Dragonite, Gliscor, Hydreigon, Kleavor, Pelipper, Scizor, Toucannon, Vivillon

**Critic flags (full)**

_No flags._

### `sleep_status_spreader`

- **Admitted:** **14** (rejected 67)
- **Tiers:** **{'Acceptable': 11, 'Good': 2, 'Excellent': 1}**
- **Critic:** approved=True flags=0

**Members**

- **Excellent** (1): Vivillon
- **Good** (2): Venusaur, Vileplume
- **Acceptable** (11): Espathra, Gourgeist-Large, Milotic, Musharna, Politoed, Roserade, Skeledirge, Venusaur-Mega, Victreebel-Mega, Watchog, Wyrdeer

**Critic flags (full)**

_No flags._

### `screens_support`

- **Admitted:** **18** (rejected 123)
- **Tiers:** **{'Acceptable': 7, 'Good': 6, 'Excellent': 5}**
- **Critic:** approved=True flags=0

**Members**

- **Excellent** (5): Grimmsnarl, Klefki, Meowstic, Sableye, Whimsicott
- **Good** (6): Alakazam, Dragapult, Espeon, Froslass-Mega, Ninetales-Alola, Serperior
- **Acceptable** (7): Abomasnow-Mega, Aurorus, Avalugg, Florges, Musharna, Rotom-Wash, Vanilluxe

**Membership-gate reopen note:** Whimsicott is in Excellent (Prankster + usage-proven screens).


**Critic flags (full)**

_No flags._

---

## Stop condition

No persist performed. Approve clusters independently for follow-up persist tasks.
