# Part 2 — hand-audit load if all six tools land

Baseline: proposed covered **96** (MT4 dropped; see `STATE_MANIFEST_PROPOSAL.json`). B1 buckets on that 96: **53 hand audit**, **42 mechanical**, **1** MC1 (treated as hand → **54** hand-like).

## Union of rows the six tools would add

Excluded from union: OL10a (not coverable under freeze), AR1/AR2/MT7/MT8 (stay out / DEV), coverable-now rows that need no new tool (H12/H21/H22/H27/OL7a/OL7b — listed in Part 0 only), GT1/LZ1/IX*/TS1/DM5/AR3 (not served by T1–T6 as specified).

| id | tool(s) | scorable |
|---|---|---|
| MM1 | T1 | hand audit |
| MM2 | T1 | mechanical |
| SC1 | T2 | mechanical |
| SC2 | T2 | mechanical |
| SC3 | T2 | mechanical |
| OL10b | T3 fixture wire (not OL10a) | mechanical |
| MS5 | T4 | mechanical |
| H17 | T4+T6 | hand audit |
| H18 | T4+T6 | hand audit |
| TB2 | T5 | mechanical |
| RB1 | T5 | mechanical |
| GS1 | T5 | hand audit |
| MT4 | T6 | mechanical |
| H25 | T6 | hand audit |
| H26 | T6 | hand audit |

**Union size: 15**

| bucket | count in union |
|---|---|
| mechanical | 9 |
| hand audit | 6 |
| not scorable | 0 |

## If all tools land (optimistic)

| metric | value |
|---|---|
| new covered total | **111** (= 96 + 15) |
| hand-audit total | **60** (= 54 hand-like + 6) |
| mechanical total | **51** (= 42 + 9) |
| Vu hand-audits | the **6** new hand rows (MM1, H17, H18, GS1, H25, H26) plus existing 54 |

OL10a remains not-covered / not scorable. Coverable-now six stay off covered until Vu adds them by readiness (would be +6 → 117 if also accepted later).

## One line — plan contradictions

**OL10a cannot be covered by a node/tool change under the frozen fixture (no presentation fingerprint); counting it as T3-covered would contradict plan decision 8 / D8 open and the freeze.**
