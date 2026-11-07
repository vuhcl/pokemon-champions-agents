# Matchup memo under concurrent sessions (2026-11-05)

Measurement only. Nothing in `recommender/` was edited. Each run is its own Python process, so the memo starts empty. Inside a run: one shared file-backed `SqliteSaver`, one `compile_graph(checkpointer=shared_saver)` per session, its own `thread_id`, fake parsers, and the calc service already listening on `127.0.0.1:4173`.

Machine: Darwin 24.6.0 arm64, Apple M4 Pro, 14 cores, 24 GB. The calc process was node pid 7145, cwd `/Users/nowaki027/pokemon-champions-agents` (the main checkout). These are local-dev numbers, not hosting numbers.

Percentiles are nearest-rank (`ceil(p/100*n) - 1`). At N = 3, 5, and 10 that makes wall p95 the slowest session in the sample, so p95 and max match. Alone is one session, so p50, p95, and max are that one wall. HTTP time is the time this session spent inside `CalcClient._json_request` (`POST /calculate/batch`). Memo hits and misses are this session's calls. "Locked after" is the fully locked species after that message. Every session of a script had the same locked list at every index (`locked_after_same` true). The turn parser was called 0 times. No message raised.

Script A is the accept-defaults floor path: bootstrap "Rain with Pelipper", then "yes" / preference "1". It locked Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal (14 messages).

Script B names Incineroar in the bootstrap parser, answers "2" on a candidate list when a second option exists (otherwise "yes"), and answers "2" on the completion preference. The first "2" selects the second suggested Pokémon, so the locked roster is not Incineroar. It locked Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse, Audino (14 messages). Message 8 had one candidate, so the reply there was "yes".

Mixed runs alternate A, B, A, B. N = 5 is three A and two B.

## Run totals

| Run | Wall s | HTTP batches | HTTP s | Mean batch ms | Max HTTP in flight | Memo clears | Clears during another invoke | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| alone (A, A again, B) | 80.0 | 26676 | 31.0 | 1.16 | 1 | 2 | 0 | 0 |
| seq N=3 A | 96.6 | 46333 | 53.2 | 1.15 | 1 | 17 | 0 | 0 |
| seq N=5 A | 159.4 | 77205 | 88.4 | 1.15 | 1 | 29 | 0 | 0 |
| seq N=10 A | 316.3 | 154385 | 174.4 | 1.13 | 1 | 59 | 0 | 0 |
| seq N=5 mix | 208.2 | 105941 | 122.3 | 1.15 | 1 | 31 | 0 | 0 |
| seq N=10 mix | 433.7 | 226224 | 257.6 | 1.14 | 1 | 64 | 0 | 0 |
| conc N=5 A | 100.1 | 74713 | 179.2 | 2.40 | 5 | 29 | 29 | 0 |
| conc N=10 A | 200.1 | 140982 | 683.7 | 4.85 | 10 | 59 | 59 | 0 |
| conc N=5 mix | 121.2 | 103639 | 254.5 | 2.46 | 5 | 28 | 28 | 0 |
| conc N=10 mix | 304.6 | 215055 | 1224.7 | 5.69 | 10 | 64 | 64 | 0 |

HTTP s is the sum of per-request time across sessions, so concurrent runs count overlapping requests separately. Mean batch time is that sum divided by the batch count.

Sequential runs never had two calc requests in flight. Concurrent runs peaked at N in flight. Mean batch time rose from about 1.1 ms with one request in flight to 2.4 ms at N = 5 and 4.9–5.7 ms at N = 10. The Node calc process is one event loop; it queued. Nothing was tuned.

The message wall rose by more than the batch time. On concurrent N = 10 script A, message 5's median wall was 48.69 s of which 15.50 s was inside HTTP. The rest is in-process work from the ten sessions sharing one interpreter. On the sequential run the same message was 7.86 s, of which 4.34 s was HTTP.

## Largest per-message wall at N = 10

| Mode | Script | Message | Wall max |
|---|---|---|---:|
| Sequential, all A | A | 5, confirming the second lock (Pelipper, Goodra) | 8.28 s |
| Sequential, mixed | A | 5, same | 8.20 s |
| Sequential, mixed | B | 9, confirming the fourth lock (through Arcanine-Hisui) | 11.33 s |
| Concurrent, all A | A | 5, second lock | 49.81 s |
| Concurrent, mixed | A | 5, second lock | 53.06 s |
| Concurrent, mixed | B | 9, fourth lock | 78.45 s |

The concurrent N = 10 script A message-5 walls were 48.39–49.81 s across all ten sessions, not one outlier. A per-message timeout set from the sequential 8–11 s figures would cut the concurrent case.

## Does the second game start cold?

No for the first lock, yes for the two-lock message.

Game 2 message 3 (first full-build confirm, Pelipper) had 46 memo hits, 0 misses, 0 HTTP, wall 0.66 s. After that message the memo was still bound to game 1's thread id and still held game 1's 5111 entries. `discover_single_locked` calls `classify_matchup` and does not call `bind_matchup_memo_thread`, so it reused the previous thread's dict.

Game 2 message 5 is the first `discover_multi_locked` on the new thread. Bind saw the new id, cleared, and the message was cold again: 3708 batches, 2435 misses, wall 7.81 s, against game 1's 3665 batches, 2404 misses, wall 7.62 s. The final fingerprints of the two A games were equal.

Round-robin shows the same split. Message 3 stays on the previous session's memo (46 hits, 0 HTTP) because the rosters match. Message 5 clears and repeats about 3708 batches and 7.8–8.3 s on every session. Message 10, the completion preference, is 1.57 s and 0 HTTP when the memo is kept (alone), and about 5.2 s with 3235 batches when the previous session has cleared it (sequential N = 10).

Script B's alone game reached `MATCHUP_MEMO_MAX_ENTRIES` (8192) by message 12. Later puts evict. Script A stayed near 5100.

## Correctness

### Where the memo lives

`recommender/matchup.py` keeps one process-wide `OrderedDict` (`_MATCHUP_MEMO`, cap 8192), one stats dict, and one string slot (`_MEMO_THREAD_ID`). It is not a per-thread dict.

`bind_matchup_memo_thread` is called from `_compute_team_review` in `recommender/nodes.py`, which `discover_multi_locked`, `refresh_team_signals`, and `generate_team_review` use. If the slot is empty, bind stores the id and keeps the dict. If the id differs, `clear_matchup_memo` drops the dict, zeroes the stats, and then stores the new id. There is no lock around the check, the clear, or `OrderedDict` get / move-to-end / put / evict.

The cache key is `(build fingerprint, build fingerprint, field fingerprint)`. A build fingerprint is species, item, ability, nature, level, move list in list order, and EVs sorted by stat. A field fingerprint is game type, weather, terrain, gravity, magic room, wonder room, trick room, and the listed side flags plus spikes. The key does not include the thread id.

`_evaluate_exchange` sends `dict(attacker)` and `dict(defender)` to the calc. The fingerprint omits `abilityOverride`, `boosts`, `curHP`, `substitute`, `substituteHp`, `endure`, `form`, and `types`. The builders on this path (`coverage._slot_to_spec`, `threat_counters._set_to_spec`) do not set those fields, so a hit in this run is a hit on the fields that were actually sent. A caller that did set `boosts` would get a cached result computed without them.

### Thread safety of run 4

Not thread-safe. In every concurrent run, every memo clear happened while another session's invoke was still in flight (the "clears during another invoke" column equals the clear count). A session can have its dict wiped, or filled with another session's entries for the same key, between its own `classify_matchup` calls. No invoke raised, including no `OrderedDict` error that escaped the graph.

### Differential test

Compared, in order: every locked `Attr` on `team_draft` (value and locked flag), coverage rows (threat species, outcome, severity, covering-slot order, weather, terrain, caveat flags, turn-economy note), SPOF rows, pending kind and option order, and `candidate_discovery_error`.

Every script A session in runs 2 and 4 matched alone game 1. Every script B session matched the script B game in the alone process. Sessions inside a run matched each other. No ordering difference. SHA-256 prefixes of the canonical fingerprints: script A `374aa94c92b3f415`, script B `38f7e06329564997`.

The race was observed and the stored outputs still matched. That is consistent with a deterministic calc for a given key. It does not show that a torn read cannot happen.

## What a different memo would touch

A per-thread memo would replace the one `OrderedDict` and the one `_MEMO_THREAD_ID` in `matchup.py` with a bounded dict per thread id, and `bind_matchup_memo_thread` would select that dict instead of clearing. It would also have to cover `discover_single_locked`, which calls `classify_matchup` today without binding, or that path would keep reading whichever dict was bound last. A shared memo keyed by the full calc inputs would delete the clear and keep cross-session hits, and it would still be one unsynchronized dict under the threadpool unless the get and put were locked. Either change can serve a stale or partial result if the key still omits a field the calc request sends, and a per-thread cap of 8192 would multiply that memory by the number of live sessions.

## Per-message tables

Kind and reply text are in the trace. Script A replies are bootstrap "Rain with Pelipper", candidate "yes", confirm "yes", preference "1". Script B replies are bootstrap "Incineroar", candidate "2" when a second option exists, confirm "yes", preference "2".

### 1. Alone, script A, cold process

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.19 | 0.19 | 0.19 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | — |
| 3 | 0.83 | 0.83 | 0.83 | 68 | 0.13 | 0 | 46 | Pelipper |
| 4 | 0.04 | 0.04 | 0.04 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 7.62 | 7.62 | 7.62 | 3665 | 4.12 | 529 | 2404 | Pelipper, Goodra |
| 6 | 0.06 | 0.06 | 0.06 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 3.06 | 3.06 | 3.06 | 504 | 0.54 | 1937 | 355 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 5.85 | 5.85 | 5.85 | 2504 | 2.89 | 154702 | 2009 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 1.57 | 1.57 | 1.57 | 0 | 0.00 | 156711 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 2.40 | 2.40 | 2.40 | 239 | 0.29 | 327848 | 200 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.04 | 0.04 | 0.04 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 0.34 | 0.34 | 0.34 | 113 | 0.14 | 3363 | 97 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 1b. Alone, script A, second thread, same process

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.10 | 0.10 | 0.10 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | — |
| 3 | 0.66 | 0.66 | 0.66 | 0 | 0.00 | 46 | 0 | Pelipper |
| 4 | 0.04 | 0.04 | 0.04 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 7.81 | 7.81 | 7.81 | 3708 | 4.27 | 498 | 2435 | Pelipper, Goodra |
| 6 | 0.07 | 0.07 | 0.07 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 3.32 | 3.32 | 3.32 | 504 | 0.56 | 1937 | 355 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 5.72 | 5.72 | 5.72 | 2504 | 2.86 | 154702 | 2009 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 1.59 | 1.59 | 1.59 | 0 | 0.00 | 156711 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 2.59 | 2.59 | 2.59 | 239 | 0.30 | 327848 | 200 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 0.34 | 0.34 | 0.34 | 113 | 0.13 | 3363 | 97 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 1c. Script B, after the two A games, same process

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.45 | 0.45 | 0.45 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.01 | 0.01 | 0.01 | 0 | 0.00 | 0 | 0 | — |
| 3 | 7.11 | 7.11 | 7.11 | 1582 | 2.22 | 101 | 1603 | Garchomp |
| 4 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Garchomp |
| 5 | 6.15 | 6.15 | 6.15 | 2037 | 2.48 | 1561 | 1141 | Garchomp, Whimsicott |
| 6 | 0.08 | 0.08 | 0.08 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott |
| 7 | 6.35 | 6.35 | 6.35 | 2999 | 3.37 | 2599 | 1630 | Garchomp, Whimsicott, Indeedee-F |
| 8 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F |
| 9 | 9.40 | 9.40 | 9.40 | 5526 | 6.30 | 258132 | 3787 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 10 | 2.01 | 2.01 | 2.01 | 0 | 0.00 | 261919 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 11 | 0.13 | 0.13 | 0.13 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 12 | 3.36 | 3.36 | 3.36 | 371 | 0.39 | 617936 | 248 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 13 | 0.18 | 0.18 | 0.18 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 14 | 0.21 | 0.21 | 0.21 | 0 | 0.00 | 4372 | 87 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse, Audino |

### 2. Sequential round-robin, N=3, script A, script A

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.12 | 0.17 | 0.17 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | — |
| 3 | 0.62 | 0.75 | 0.75 | 0 | 0.00 | 46 | 0 | Pelipper |
| 4 | 0.03 | 0.04 | 0.04 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 8.28 | 8.47 | 8.47 | 3708 | 4.67 | 498 | 2435 | Pelipper, Goodra |
| 6 | 0.07 | 0.07 | 0.07 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 4.85 | 5.15 | 5.15 | 2053 | 2.15 | 894 | 1398 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 6.49 | 6.78 | 6.78 | 3235 | 3.56 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 5.38 | 5.45 | 5.45 | 3235 | 3.60 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 4.99 | 5.15 | 5.15 | 2535 | 2.77 | 325973 | 2075 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.03 | 0.06 | 0.06 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 1.01 | 1.03 | 1.03 | 670 | 0.78 | 2882 | 578 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 2. Sequential round-robin, N=5, script A, script A

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.10 | 0.19 | 0.19 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | — |
| 3 | 0.63 | 0.76 | 0.76 | 0 | 0.00 | 46 | 0 | Pelipper |
| 4 | 0.04 | 0.04 | 0.04 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 7.85 | 8.29 | 8.29 | 3708 | 4.29 | 498 | 2435 | Pelipper, Goodra |
| 6 | 0.06 | 0.07 | 0.07 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 5.16 | 5.26 | 5.26 | 2053 | 2.48 | 894 | 1398 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 6.48 | 6.59 | 6.59 | 3235 | 3.57 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 5.29 | 5.33 | 5.33 | 3235 | 3.52 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 5.18 | 5.24 | 5.24 | 2535 | 2.97 | 325973 | 2075 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 1.02 | 1.04 | 1.04 | 670 | 0.81 | 2882 | 578 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 2. Sequential round-robin, N=10, script A, script A

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.09 | 0.18 | 0.18 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.02 | 0.05 | 0.05 | 0 | 0.00 | 0 | 0 | — |
| 3 | 0.63 | 0.77 | 0.77 | 0 | 0.00 | 46 | 0 | Pelipper |
| 4 | 0.04 | 0.04 | 0.04 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 7.86 | 8.28 | 8.28 | 3708 | 4.34 | 498 | 2435 | Pelipper, Goodra |
| 6 | 0.07 | 0.11 | 0.11 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 4.95 | 5.17 | 5.17 | 2053 | 2.28 | 894 | 1398 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 6.45 | 6.63 | 6.63 | 3235 | 3.53 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 5.22 | 5.51 | 5.51 | 3235 | 3.49 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 5.08 | 5.29 | 5.29 | 2535 | 2.89 | 325973 | 2075 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.03 | 0.08 | 0.08 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 1.02 | 1.06 | 1.06 | 670 | 0.80 | 2882 | 578 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 3. Sequential round-robin, N=5, mixed, script A

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.09 | 0.18 | 0.18 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | — |
| 3 | 0.71 | 0.77 | 0.77 | 46 | 0.07 | 22 | 24 | Pelipper |
| 4 | 0.04 | 0.04 | 0.04 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 7.81 | 8.42 | 8.42 | 3708 | 4.33 | 498 | 2435 | Pelipper, Goodra |
| 6 | 0.07 | 0.07 | 0.07 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 5.07 | 5.20 | 5.20 | 2053 | 2.36 | 894 | 1398 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 6.54 | 6.65 | 6.65 | 3235 | 3.58 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 5.36 | 5.48 | 5.48 | 3235 | 3.58 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.03 | 0.04 | 0.04 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 5.17 | 5.17 | 5.17 | 2535 | 2.94 | 325973 | 2075 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 1.03 | 1.04 | 1.04 | 670 | 0.81 | 2882 | 578 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 3. Sequential round-robin, N=5, mixed, script B

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.41 | 0.42 | 0.42 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.01 | 0.01 | 0.01 | 0 | 0.00 | 0 | 0 | — |
| 3 | 6.71 | 6.78 | 6.78 | 1558 | 2.10 | 108 | 1579 | Garchomp |
| 4 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Garchomp |
| 5 | 7.52 | 8.11 | 8.11 | 3192 | 3.86 | 387 | 2315 | Garchomp, Whimsicott |
| 6 | 0.08 | 0.13 | 0.13 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott |
| 7 | 9.06 | 9.22 | 9.22 | 5051 | 5.99 | 1089 | 3140 | Garchomp, Whimsicott, Indeedee-F |
| 8 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F |
| 9 | 11.21 | 11.30 | 11.30 | 7043 | 8.02 | 257111 | 4808 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 10 | 10.41 | 10.63 | 10.63 | 7043 | 8.06 | 257111 | 4808 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 11 | 0.14 | 0.17 | 0.17 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 12 | 8.47 | 8.83 | 8.83 | 4903 | 5.34 | 614691 | 3493 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 13 | 0.17 | 0.22 | 0.22 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 14 | 0.91 | 1.27 | 1.27 | 961 | 0.66 | 3624 | 835 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse, Audino |

### 3. Sequential round-robin, N=10, mixed, script A

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.09 | 0.18 | 0.18 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | — |
| 3 | 0.70 | 0.76 | 0.76 | 46 | 0.07 | 22 | 24 | Pelipper |
| 4 | 0.04 | 0.04 | 0.04 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 7.91 | 8.20 | 8.20 | 3708 | 4.43 | 498 | 2435 | Pelipper, Goodra |
| 6 | 0.07 | 0.07 | 0.07 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 5.12 | 5.20 | 5.20 | 2053 | 2.44 | 894 | 1398 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.02 | 0.02 | 0.02 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 6.27 | 6.38 | 6.38 | 3235 | 3.40 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 5.22 | 5.39 | 5.39 | 3235 | 3.47 | 154150 | 2561 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 5.10 | 5.44 | 5.44 | 2535 | 2.89 | 325973 | 2075 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 1.01 | 1.01 | 1.01 | 670 | 0.79 | 2882 | 578 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 3. Sequential round-robin, N=10, mixed, script B

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.41 | 0.43 | 0.43 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.01 | 0.01 | 0.01 | 0 | 0.00 | 0 | 0 | — |
| 3 | 6.66 | 6.75 | 6.75 | 1580 | 2.04 | 103 | 1601 | Garchomp |
| 4 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Garchomp |
| 5 | 7.60 | 7.68 | 7.68 | 3192 | 3.97 | 387 | 2315 | Garchomp, Whimsicott |
| 6 | 0.09 | 0.09 | 0.09 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott |
| 7 | 8.73 | 8.97 | 8.97 | 5051 | 5.70 | 1089 | 3140 | Garchomp, Whimsicott, Indeedee-F |
| 8 | 0.03 | 0.03 | 0.03 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F |
| 9 | 11.07 | 11.33 | 11.33 | 7043 | 7.93 | 257111 | 4808 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 10 | 10.48 | 10.59 | 10.59 | 7043 | 8.13 | 257111 | 4808 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 11 | 0.14 | 0.15 | 0.15 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 12 | 8.70 | 9.16 | 9.16 | 4903 | 5.51 | 614691 | 3493 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 13 | 0.18 | 0.19 | 0.19 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 14 | 1.21 | 1.31 | 1.31 | 961 | 0.95 | 3624 | 835 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse, Audino |

### 4. Concurrent, N=5, script A, script A

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.84 | 0.84 | 0.84 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.12 | 0.13 | 0.13 | 0 | 0.00 | 0 | 0 | — |
| 3 | 3.39 | 3.53 | 3.53 | 61 | 0.60 | 6 | 40 | Pelipper |
| 4 | 0.18 | 0.28 | 0.28 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 23.74 | 23.89 | 23.89 | 3550 | 7.81 | 711 | 2222 | Pelipper, Goodra |
| 6 | 0.38 | 0.49 | 0.49 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 17.90 | 18.02 | 18.02 | 1966 | 4.34 | 1035 | 1257 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.12 | 0.17 | 0.17 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 21.24 | 21.29 | 21.29 | 3095 | 7.48 | 154601 | 2110 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 13.52 | 13.59 | 13.59 | 3147 | 6.86 | 154550 | 2161 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.22 | 0.28 | 0.28 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 16.47 | 16.47 | 16.47 | 2464 | 7.96 | 326347 | 1701 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.20 | 0.22 | 0.22 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 1.89 | 1.90 | 1.90 | 652 | 0.87 | 2915 | 545 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 4. Concurrent, N=10, script A, script A

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1.50 | 1.51 | 1.51 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.21 | 0.25 | 0.25 | 0 | 0.00 | 0 | 0 | — |
| 3 | 7.78 | 7.92 | 7.92 | 60 | 1.10 | 8 | 38 | Pelipper |
| 4 | 0.51 | 0.59 | 0.59 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 48.69 | 49.81 | 49.81 | 3386 | 15.50 | 854 | 2071 | Pelipper, Goodra |
| 6 | 0.73 | 0.95 | 0.95 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 36.85 | 37.15 | 37.15 | 1854 | 8.05 | 1142 | 1149 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.26 | 0.71 | 0.71 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 41.48 | 41.86 | 41.86 | 2867 | 13.26 | 154816 | 1893 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 26.49 | 26.80 | 26.80 | 2973 | 13.44 | 154754 | 1955 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.32 | 0.35 | 0.35 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 30.73 | 30.76 | 30.76 | 2333 | 14.10 | 326505 | 1538 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.46 | 0.48 | 0.48 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 3.87 | 3.89 | 3.89 | 600 | 1.87 | 2958 | 499 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 4. Concurrent, N=5, mixed, script A

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.99 | 1.00 | 1.00 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.10 | 0.10 | 0.10 | 0 | 0.00 | 0 | 0 | — |
| 3 | 6.15 | 6.16 | 6.16 | 67 | 0.44 | 1 | 45 | Pelipper |
| 4 | 0.19 | 0.19 | 0.19 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 25.24 | 25.25 | 25.25 | 2945 | 11.23 | 1269 | 1664 | Pelipper, Goodra |
| 6 | 0.26 | 0.31 | 0.31 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 17.17 | 17.34 | 17.34 | 1758 | 4.70 | 1159 | 1133 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.10 | 0.10 | 0.10 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 17.91 | 17.91 | 17.91 | 3156 | 7.63 | 154479 | 2232 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 14.55 | 14.58 | 14.58 | 3256 | 9.14 | 154438 | 2273 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.11 | 0.13 | 0.13 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 13.24 | 13.26 | 13.26 | 2423 | 6.96 | 326359 | 1689 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.15 | 0.16 | 0.16 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 1.59 | 1.67 | 1.67 | 654 | 0.99 | 2911 | 549 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 4. Concurrent, N=5, mixed, script B

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 3.14 | 3.18 | 3.18 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.05 | 0.05 | 0.05 | 0 | 0.00 | 0 | 0 | — |
| 3 | 19.22 | 19.22 | 19.22 | 1519 | 6.32 | 147 | 1527 | Garchomp |
| 4 | 0.13 | 0.15 | 0.15 | 0 | 0.00 | 0 | 0 | Garchomp |
| 5 | 25.12 | 25.15 | 25.15 | 3041 | 11.87 | 511 | 2164 | Garchomp, Whimsicott |
| 6 | 0.37 | 0.40 | 0.40 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott |
| 7 | 26.63 | 26.64 | 26.64 | 5249 | 17.22 | 965 | 3199 | Garchomp, Whimsicott, Indeedee-F |
| 8 | 0.09 | 0.09 | 0.09 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F |
| 9 | 26.47 | 26.47 | 26.47 | 7686 | 19.72 | 256960 | 4824 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 10 | 8.17 | 8.18 | 8.18 | 7041 | 4.58 | 257370 | 4535 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 11 | 0.31 | 0.31 | 0.31 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 12 | 10.05 | 10.06 | 10.06 | 4901 | 4.87 | 614883 | 3219 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 13 | 0.40 | 0.40 | 0.40 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 14 | 0.94 | 0.94 | 0.94 | 961 | 0.46 | 3624 | 668 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse, Audino |

### 4. Concurrent, N=10, mixed, script A

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1.76 | 1.82 | 1.82 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.39 | 0.42 | 0.42 | 0 | 0.00 | 0 | 0 | — |
| 3 | 12.62 | 12.94 | 12.94 | 55 | 0.78 | 9 | 37 | Pelipper |
| 4 | 0.33 | 0.48 | 0.48 | 0 | 0.00 | 0 | 0 | Pelipper |
| 5 | 52.73 | 53.06 | 53.06 | 2894 | 21.53 | 1318 | 1615 | Pelipper, Goodra |
| 6 | 0.47 | 0.60 | 0.60 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra |
| 7 | 35.13 | 35.57 | 35.57 | 1670 | 9.23 | 1250 | 1042 | Pelipper, Goodra, Excadrill-Mega |
| 8 | 0.17 | 0.22 | 0.22 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega |
| 9 | 35.27 | 35.37 | 35.37 | 3017 | 15.14 | 154653 | 2058 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 10 | 43.77 | 43.97 | 43.97 | 3185 | 26.83 | 154561 | 2150 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 11 | 0.44 | 0.47 | 0.47 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion |
| 12 | 33.09 | 33.15 | 33.15 | 2319 | 16.70 | 326472 | 1576 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 13 | 0.31 | 0.31 | 0.31 | 0 | 0.00 | 0 | 0 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon |
| 14 | 5.26 | 5.26 | 5.26 | 630 | 3.62 | 2936 | 524 | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal |

### 4. Concurrent, N=10, mixed, script B

| # | wall p50 | wall p95 | wall max | HTTP batches p50 | HTTP s p50 | memo hits p50 | memo misses p50 | locked after |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 5.94 | 5.98 | 5.98 | 0 | 0.00 | 0 | 0 | — |
| 2 | 0.20 | 0.23 | 0.23 | 0 | 0.00 | 0 | 0 | — |
| 3 | 45.45 | 45.54 | 45.54 | 1353 | 11.51 | 349 | 1355 | Garchomp |
| 4 | 0.45 | 0.50 | 0.50 | 0 | 0.00 | 0 | 0 | Garchomp |
| 5 | 47.56 | 47.86 | 47.86 | 2831 | 19.35 | 754 | 1948 | Garchomp, Whimsicott |
| 6 | 0.83 | 0.94 | 0.94 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott |
| 7 | 56.84 | 57.04 | 57.04 | 5077 | 29.53 | 1192 | 3037 | Garchomp, Whimsicott, Indeedee-F |
| 8 | 0.25 | 0.32 | 0.32 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F |
| 9 | 78.00 | 78.45 | 78.45 | 7412 | 53.03 | 257406 | 4513 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 10 | 33.46 | 33.65 | 33.65 | 6849 | 20.46 | 257753 | 4166 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 11 | 1.04 | 1.25 | 1.25 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui |
| 12 | 30.28 | 30.30 | 30.30 | 4769 | 15.19 | 615186 | 2998 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 13 | 1.35 | 1.38 | 1.38 | 0 | 0.00 | 0 | 0 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse |
| 14 | 2.93 | 3.07 | 3.07 | 931 | 1.61 | 3778 | 681 | Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse, Audino |
