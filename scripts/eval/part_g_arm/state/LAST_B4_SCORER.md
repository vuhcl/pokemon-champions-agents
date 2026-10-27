# B4 — class scorer

## Dev rows (out-final4; observed only, not request-set keys)

| row | mechanical classes | pass |
|---|---|---|
| dev-lock | ['wrote', 'refused'] | True |
| dev-unlock | ['refused'] | True |
| dev-commit | ['refused'] | True |
| dev-lookup | ['lookup only'] | True |
| dev-unlock-ok | ['wrote'] | True |
| dev-commit-ok | ['wrote'] | True |
| dev-hyp-item-clause | ['lookup only'] | True |
| dev-hyp-species-clause | ['lookup only'] | True |
| dev-hyp-unknown-species | ['lookup only'] | True |
| dev-hyp-legal | ['lookup only'] | True |
| dev-hyp-item-only | ['lookup only'] | True |
| dev-pick-named | ['bound'] | True |
| dev-select-bad | ['refused'] | True |
| dev-select-locked-target | ['refused'] | True |
| dev-confirm-fbc | ['wrote'] | True |
| dev-confirm-stale-fp | ['refused'] | True |
| dev-reject | ['recorded'] | True |
| dev-toss-all | ['recorded'] | True |
| dev-show-rejected | ['recorded', 'lookup only'] | True |
| dev-dismiss-later | ['dismissed'] | True |
| dev-reject-all-bad | ['refused'] | True |
| dev-mt7 | ['lookup only', 'lookup only', 'no change'] | True |
| dev-mt8 | ['lookup only', 'lookup only', 'lookup only', 'lookup only'] | True |

## Synthetic covered transcripts (not real arm runs)

```json
{
  "per_row": [
    {
      "row": "MS1",
      "excluded": null,
      "turns": [
        {
          "mechanical_class_observed": "wrote",
          "key_class_expected": "MUTATION-OK",
          "match": true,
          "state_expectation_met": true
        }
      ]
    },
    {
      "row": "MR1",
      "excluded": null,
      "turns": [
        {
          "mechanical_class_observed": "refused",
          "key_class_expected": "MUTATION-REFUSED",
          "match": true,
          "state_expectation_met": true
        }
      ]
    },
    {
      "row": "H1",
      "excluded": "hand audit",
      "turns": [
        {
          "mechanical_class_observed": "lookup only",
          "key_class_expected": "SERVED",
          "match": true,
          "state_expectation_met": true
        }
      ]
    },
    {
      "row": "MT2",
      "excluded": "stale_pin",
      "stale": true
    }
  ],
  "per_class": {
    "MUTATION-OK": {
      "n": 1,
      "match": 1,
      "state_ok": 1
    },
    "MUTATION-REFUSED": {
      "n": 1,
      "match": 1,
      "state_ok": 1
    }
  },
  "errata": "claude/request_set_errata_draft_2026-10-26.md (draft not present in worktree; cells taken from request-set acceptance text + Vu task brief)",
  "note": "ADR-078: rates are per class, never pooled"
}
```
