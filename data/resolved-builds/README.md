# Resolved-build cache (ADR-016)

Curated, derived dataset of builds this project has resolved and (when marked)
tier-3-verified. Not a bulk mirror of any single competitive-data source.

Per-regulation JSONL files (e.g. `champions-reg-mb.jsonl`). When a regulation
changes, archive the prior file under its own tag — do not delete or merge
(Showdown mod-retirement pattern).

Key: species + moveset + item (Showdown `to_id` form), scoped by file.
