# Laya turn_intent spike dataset

Hand-authored utterance → gold `turn_intent` rows (independent oracle).

- Source of labels: ADR / `TurnIntentName` / `classify_pending` rules — **not** any classifier.
- Edit utterances in `_rows.py`, then: `PYTHONPATH=. python write_jsonl.py`
- Splits: `dev.jsonl` (criteria tuning only), `held_out.jsonl` (scored once).
