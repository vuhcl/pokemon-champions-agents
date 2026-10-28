# Hand-audit HTML form (gemma-blind)

## Base file

**Based on** `scripts/eval/part_g_v4/audit_view.py` (HTML builder, localStorage autosave, Export CSV / Clear, Node-testable JS CSV helpers).

## Differences from Part G

| Part G | State arm |
|---|---|
| Exception types; export `audit_exceptions.csv` | Per rubric point `pass` / `fail` / `not_applicable`; overall; note; export `hand_audit_export.csv` |
| Page shows **scorer/extractor** claim verdicts (TRUE/FALSE/…) | **No gemma and no scorer verdicts** on the page |
| Battery claim rows | One section per transcript turn |

Part G did **not** embed gemma4; it did embed scorer verdicts. Omitting both on-page is deliberate so the second rater cannot anchor.

## Rubric points

Request-set `acceptance` cell; split on `;` → `p1…`, else single point `acceptance`. Fixtures may pass an explicit points list.

## Generator / tests

- Script: `hand_audit_form.py`
- Tests: `test_hand_audit_form.py` (dev/stub only; export round-trip via Node)
- Sample output (outside repo): `/Users/nowaki027/part-g-arm-state-out-audit/`
- Stub/dev `hand_audit.html` sha256: `bb2042515cdfec9f5ee68be3dae97c91375554f56125b0048d9a1efc9f5647ca` (3 sections / 4 CSV data lines)
- `--diff-runs`: build from `compare_runs` differ list + run 2/3 transcripts only
