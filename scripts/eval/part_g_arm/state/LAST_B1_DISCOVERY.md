# B1 — scorable discovery (97 covered)

Part G claim scorer (`scripts/eval/part_g_v4/scorer.py`) scores battery answer JSONL, **not** arm transcripts → **mechanical+claims = none** today.

| row | key class (per-turn) | → mechanical vocab | bucket | reason |
|---|---|---|---|---|
| H1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H2 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H3 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H4 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H5 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H6 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H7 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H8 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| Q9 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| Q10 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H11 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H13 | FAIL-CLOSED | refused or no change (state unchanged; refuse) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| H14 | FAIL-CLOSED | refused or no change (state unchanged; refuse) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| H15 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H16 | FAIL-CLOSED | refused or no change (state unchanged; refuse) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| H18b | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H19 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| H20 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MT1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MT2 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MT3 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MT4 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MT5 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MT6 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HF1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HF2 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HC1 | FAIL-CLOSED | refused or no change (state unchanged; refuse) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| HC2 | ASK | no change (no successful state write; ask in text) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| HD1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HU1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HU2 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HU3 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HU4 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HN1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HN2 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HN3 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HN4 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HP1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HP2 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HP3 | MUTATION-REFUSED | refused (state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MS1 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MS2 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MS3 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MS4 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MS6 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MS7 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MS8 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MR1 | MUTATION-REFUSED | refused (state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MR2 | MUTATION-REFUSED | refused (state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MR3 | MUTATION-REFUSED | refused (state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MR4 | MUTATION-REFUSED | refused (state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MR5 | MUTATION-REFUSED | refused (state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MR6 | MUTATION-REFUSED | refused (state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MR7 | MUTATION-REFUSED | refused (state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MR8 | MUTATION-REFUSED | refused (state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MU1 | NO-MUTATION | lookup only or no change (no state tool success; state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MU2 | NO-MUTATION | lookup only or no change (no state tool success; state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MU3 | NO-MUTATION | lookup only or no change (no state tool success; state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MU4 | NO-MUTATION | lookup only or no change (no state tool success; state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MU5 | NO-MUTATION | lookup only or no change (no state tool success; state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MU6 | NO-MUTATION | lookup only or no change (no state tool success; state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MU7 | NO-MUTATION | lookup only or no change (no state tool success; state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MU8 | NO-MUTATION | lookup only or no change (no state tool success; state equals start) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MW1 | ASK | no change (no successful state write; ask in text) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MW2 | ASK | no change (no successful state write; ask in text) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MW3 | ASK | no change (no successful state write; ask in text) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MW4 | ASK | no change (no successful state write; ask in text) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| MRB1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| OL1 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| OL2a | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| OL2b | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| OL3 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| OL4 | ASK | no change (no successful state write; ask in text) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| OL5 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| OL6 | ASK | no change (no successful state write; ask in text) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| OL8 | MUTATION-OK | wrote (or bound then wrote) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| OL9 | ASK | no change (no successful state write; ask in text) | scorable-mechanical | state signature + tool outcome suffice; no claim leaf required |
| HU2b | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HN2b | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HN2c | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| HN2d | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| IS1 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| IS2 | PARTIAL+ASSUME-STATE | lookup only / no change (partial + assumed cells) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| IS3 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| IS4 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| DM1 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| DM2 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| DM3 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| DM4 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| DM6 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| DM7 | ASSUME-STATE | lookup only / no change (stated conditions + facts; state unchanged) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MV1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MV2 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MV3 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| IC1 | SERVED / MUTATION-OK | lookup only / no change (facts in text; state unchanged on question) ; wrote (or bound then wrote) | hand audit | compound class: state half mechanical, claim half has no transcript adapter on Part G scorer |
| TB1 | SERVED | lookup only / no change (facts in text; state unchanged on question) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
| MC1 | ASK|ASSUME-STATE | no change OR lookup only under stated assume (MC1) | hand audit | claim/fact match needed; frozen Part G scorer scores battery answers, not arm transcripts (plan decision 7) |
