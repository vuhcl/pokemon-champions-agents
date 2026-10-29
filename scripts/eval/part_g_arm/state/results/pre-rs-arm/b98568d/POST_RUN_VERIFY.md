# Post-run verification (b98568d)

- git HEAD at run branch tip after this commit (see git log)
- frozen manifest verify (at b98568d base): PASS frozen manifest (clean tree)
- calc health: {"status":"ok"}
- check_pins: PASS 14 pins match

## sha256

| path | sha256 |
|---|---|
| run_1/transcript.json | 7b423c80af785cde0f2cfe30e9f127307a9b8c71f94fdbda6cec1a8d19e1df9c |
| run_1/progress.json | 9c4aea21b33a6bb1a4aa71457b82c7e2feecf2533ee0b6bcb1df2fc2c6cde47c |
| run_1/run_record.json | 5f185213075f18bc870045dd7ef936ef103c841b674e8684864daefe61e3c1f9 |
| run_1/class_scorer.json | b2f158007c37f18a72a26350ffe37bde8c5412798fad3ce6af6b4c2c2de23f12 |
| run_1/clopper_pearson.json | 9d0e6c4c3ebfe6378f18413fd6010130d34cae3be5bd158ffe7ddde1a30101cd |
| run_2/transcript.json | 410addb115bd330529550450672f3959fef40c9679f561d00a3c2147e3c9fdc7 |
| run_2/progress.json | 4dcd7f52272886bca482da380c2d12472307ef63887246646a0f9447bbda1a36 |
| run_2/run_record.json | 0787d523cbc69ea626911ca3d5e4646c0edf5c80e2c833d5a6060677b54c18c3 |
| run_3/transcript.json | 48caa18236c47ecff2e56d925c5569e2e17955fe89538b92dd1f6b8558f41129 |
| run_3/progress.json | 6119a6843e047580c1e4db0864ae6079387b284d90328bc10af9cde2587b77b5 |
| run_3/run_record.json | 81365656c68c11b860795349ea8e12f5ca5c24cf64b2bfeab5506b395766221c |
| run_1_hand_audit/hand_audit_export_1.csv | 3bdbc2b6bbc1afef8134be0755170d8a2c1ad6f0695042cf6a802789acca8f07 |
| run_1_hand_audit/gemma_merge.json | 9a813f95bfd9d4e090518f29fb5158fb76adcf59231c096dfe46f0d2556c79be |
| run_1_hand_audit/gemma_merge_meta.json | c960fbcd079f702eb35e003191b65a11a453e9b30b7031f63c0bdb8d7931b0c7 |
| cursor_fixture_key_sweep.md | 2692055748048047c6dc983a29150561fb50fc820cb466793778ef8c7df58de4 |
| cursor_run1_tallies.md | 1d6a0dc1769d7c606337da96dfaa452f856afd36e08041898aecad4ecd37c0ad |
| row_level_verdicts.py | fe29de7d1720c2592549e2a29a5a62bcca4c79ecfb858f7a8426ab528195cc64 |
| row_level_verdicts.json | 6ff25de7112be02558449bdb3dd498996c21da5847dd349ecf2e6c9afd4672e5 |
| run_hand_audit_judge_merge.py | 43a6c3439eda5c9a97870f6470e44740e74341cea54737082edeb6c1b6d1d2ba |

## Notes

- run_2/run_3 have no class_scorer/clopper_pearson (only run_1 scored; compare_runs differ_count=0).
- First export hand_audit_export.csv (blank overall HF2 t1 / H18b t1): NOT FOUND on disk; final = hand_audit_export_1.csv.
- cursor_fixture_context.md / fixture_context.html: dropped (audit finished).

