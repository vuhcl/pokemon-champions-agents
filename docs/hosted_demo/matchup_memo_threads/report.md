# Per-thread matchup memo remeasure (2026-11-05)

Same machine as #380 (Darwin 24.6.0, arm64), same scripts A and B, same calc service on 127.0.0.1:4173. One fresh process per plan. Fake parsers. Local-dev wall clock, not a hosting number.

Script A locks Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal. Script B locks Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse, Audino.

Percentiles are nearest-rank `ceil(p/100*n)-1`. At these sample sizes (1, 2, 3, 5, 10) p95 is the slowest sample, so p95 equals max. Hits are memo lookups that returned a stored result. Misses are new inserts. HTTP is `POST /calculate/batch` calls inside that message.

Every plan's locked attributes, coverage rows, SPOF rows, and pending option order matched the #380 alone-game fingerprints. `diffs=0` and `errors=[]` on all 12 plans.

The second script A game, on a new thread in the same process, was cold on its own: message 3 was 68 HTTP batches and 46 misses (0 hits), and message 5 was 3665 batches and 2404 misses. Those counts match the first game. Sequential message 10 stayed a memo hit with 0 HTTP batches (1.53–1.65 s on script A, about 2.0 s on script B).

Unrestricted concurrent N=10 still stacks in-process work: script A message 5 max was 49.37 s (all A) and 57.66 s (mixed), with the same 3665 batches as the alone game. Message 10 stayed at 0 HTTP batches and was slow only because ten sessions walked the memo in one interpreter (22.53 s p50 all A, 12.28 s p50 mixed).

A harness semaphore on the invoke, N=10 mixed, total wall and worst message:

| in flight | total wall s | worst message |
|---:|---:|---|
| 1 | 299.6 | B message 9, 10.56 s |
| 2 | 225.9 | B message 9, 22.46 s |
| 3 | 206.8 | B message 9, 29.98 s |
| unrestricted | 223.4 | A message 5, 57.66 s |

## Totals

| plan | wall s | HTTP batches | HTTP s | diffs |
|---|---:|---:|---:|---:|
| alone | 82.0 | 26697 | 33.3 | 0 |
| seq-5-A | 111.9 | 35465 | 42.5 | 0 |
| seq-10-A | 227.1 | 70930 | 87.9 | 0 |
| seq-5-mix | 147.9 | 46301 | 64.9 | 0 |
| seq-10-mix | 294.8 | 98020 | 122.6 | 0 |
| conc-5-A | 84.1 | 35465 | 97.3 | 0 |
| conc-10-A | 194.2 | 70930 | 426.5 | 0 |
| conc-5-mix | 99.9 | 46301 | 171.3 | 0 |
| conc-10-mix | 223.4 | 98020 | 671.8 | 0 |
| conc-10-mix-sem1 | 299.6 | 98020 | 126.8 | 0 |
| conc-10-mix-sem2 | 225.9 | 98020 | 192.3 | 0 |
| conc-10-mix-sem3 | 206.8 | 98020 | 256.0 | 0 |

## Largest per-message wall

| plan | message | wall s |
|---|---|---:|
| alone | B m9 | 9.71 |
| seq-5-A | A m5 | 9.06 |
| seq-10-A | A m5 | 8.67 |
| seq-5-mix | B m9 | 10.76 |
| seq-10-mix | B m9 | 10.50 |
| conc-5-A | A m5 | 23.44 |
| conc-10-A | A m5 | 49.37 |
| conc-5-mix | A m5 | 27.22 |
| conc-10-mix | A m5 | 57.66 |
| conc-10-mix-sem1 | B m9 | 10.56 |
| conc-10-mix-sem2 | B m9 | 22.46 |
| conc-10-mix-sem3 | B m9 | 29.98 |

## Per message

p50 wall, max wall, HTTP batches (p50), hits (p50), misses (p50).

### alone

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 2 | 0.10 | 0.17 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 2 | 0.02 | 0.03 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 2 | 0.76 | 0.77 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 2 | 0.03 | 0.04 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 2 | 7.81 | 8.95 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 2 | 0.07 | 0.07 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 2 | 3.18 | 3.18 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 2 | 0.01 | 0.02 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 2 | 5.80 | 5.90 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 2 | 1.53 | 1.57 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 2 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 2 | 2.43 | 2.50 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 2 | 0.03 | 0.04 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 2 | 0.36 | 0.37 | 113 | 3363 | 97 |
| B | 1 | bootstrap_intake | 1 | 0.44 | 0.44 | 0 | 0 | 0 |
| B | 2 | candidate_selection | 1 | 0.01 | 0.01 | 0 | 0 | 0 |
| B | 3 | full_build_confirmation | 1 | 6.77 | 6.77 | 1580 | 103 | 1601 |
| B | 4 | candidate_selection | 1 | 0.03 | 0.03 | 0 | 0 | 0 |
| B | 5 | full_build_confirmation | 1 | 6.36 | 6.36 | 2037 | 1561 | 1141 |
| B | 6 | candidate_selection | 1 | 0.09 | 0.09 | 0 | 0 | 0 |
| B | 7 | full_build_confirmation | 1 | 6.69 | 6.69 | 2999 | 2599 | 1630 |
| B | 8 | candidate_selection | 1 | 0.03 | 0.03 | 0 | 0 | 0 |
| B | 9 | full_build_confirmation | 1 | 9.71 | 9.71 | 5524 | 258134 | 3785 |
| B | 10 | completion_preference | 1 | 2.04 | 2.04 | 0 | 261919 | 0 |
| B | 11 | candidate_selection | 1 | 0.13 | 0.13 | 0 | 0 | 0 |
| B | 12 | full_build_confirmation | 1 | 3.48 | 3.48 | 371 | 617936 | 248 |
| B | 13 | candidate_selection | 1 | 0.19 | 0.19 | 0 | 0 | 0 |
| B | 14 | full_build_confirmation | 1 | 0.22 | 0.22 | 0 | 4372 | 87 |

### seq-5-A

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 5 | 0.09 | 0.19 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 5 | 0.02 | 0.02 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 5 | 0.71 | 0.75 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 5 | 0.03 | 0.04 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 5 | 8.23 | 9.06 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 5 | 0.06 | 0.07 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 5 | 3.10 | 3.22 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 5 | 0.01 | 0.06 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 5 | 5.49 | 5.66 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 5 | 1.53 | 1.57 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 5 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 5 | 2.48 | 2.50 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 5 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 5 | 0.35 | 0.36 | 113 | 3363 | 97 |

### seq-10-A

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 10 | 0.09 | 0.17 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 10 | 0.02 | 0.05 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 10 | 0.71 | 0.77 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 10 | 0.04 | 0.04 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 10 | 8.32 | 8.67 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 10 | 0.07 | 0.07 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 10 | 3.19 | 3.26 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 10 | 0.02 | 0.02 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 10 | 5.72 | 5.97 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 10 | 1.63 | 1.65 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 10 | 0.03 | 0.08 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 10 | 2.48 | 2.53 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 10 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 10 | 0.31 | 0.36 | 113 | 3363 | 97 |

### seq-5-mix

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 3 | 0.09 | 0.18 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 3 | 0.02 | 0.02 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 3 | 0.72 | 0.73 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 3 | 0.04 | 0.04 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 3 | 9.06 | 9.13 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 3 | 0.06 | 0.07 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 3 | 3.20 | 3.24 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 3 | 0.01 | 0.02 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 3 | 6.03 | 6.28 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 3 | 1.58 | 1.63 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 3 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 3 | 2.46 | 2.55 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 3 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 3 | 0.37 | 0.40 | 113 | 3363 | 97 |
| B | 1 | bootstrap_intake | 2 | 0.40 | 0.43 | 0 | 0 | 0 |
| B | 2 | candidate_selection | 2 | 0.01 | 0.01 | 0 | 0 | 0 |
| B | 3 | full_build_confirmation | 2 | 6.93 | 7.53 | 1580 | 103 | 1601 |
| B | 4 | candidate_selection | 2 | 0.03 | 0.03 | 0 | 0 | 0 |
| B | 5 | full_build_confirmation | 2 | 6.47 | 6.75 | 2037 | 1561 | 1141 |
| B | 6 | candidate_selection | 2 | 0.08 | 0.08 | 0 | 0 | 0 |
| B | 7 | full_build_confirmation | 2 | 7.00 | 7.12 | 2999 | 2599 | 1630 |
| B | 8 | candidate_selection | 2 | 0.03 | 0.07 | 0 | 0 | 0 |
| B | 9 | full_build_confirmation | 2 | 10.62 | 10.76 | 5524 | 258134 | 3785 |
| B | 10 | completion_preference | 2 | 1.99 | 2.06 | 0 | 261919 | 0 |
| B | 11 | candidate_selection | 2 | 0.14 | 0.15 | 0 | 0 | 0 |
| B | 12 | full_build_confirmation | 2 | 3.59 | 3.61 | 371 | 617936 | 248 |
| B | 13 | candidate_selection | 2 | 0.19 | 0.19 | 0 | 0 | 0 |
| B | 14 | full_build_confirmation | 2 | 0.22 | 0.22 | 0 | 4372 | 87 |

### seq-10-mix

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 5 | 0.09 | 0.17 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 5 | 0.02 | 0.02 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 5 | 0.74 | 0.79 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 5 | 0.04 | 0.04 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 5 | 8.40 | 8.50 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 5 | 0.07 | 0.07 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 5 | 3.20 | 3.21 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 5 | 0.02 | 0.02 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 5 | 5.55 | 5.68 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 5 | 1.59 | 1.59 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 5 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 5 | 2.44 | 2.52 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 5 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 5 | 0.35 | 0.37 | 113 | 3363 | 97 |
| B | 1 | bootstrap_intake | 5 | 0.42 | 0.46 | 0 | 0 | 0 |
| B | 2 | candidate_selection | 5 | 0.01 | 0.01 | 0 | 0 | 0 |
| B | 3 | full_build_confirmation | 5 | 7.08 | 7.12 | 1580 | 103 | 1601 |
| B | 4 | candidate_selection | 5 | 0.03 | 0.03 | 0 | 0 | 0 |
| B | 5 | full_build_confirmation | 5 | 6.51 | 6.51 | 2037 | 1561 | 1141 |
| B | 6 | candidate_selection | 5 | 0.08 | 0.12 | 0 | 0 | 0 |
| B | 7 | full_build_confirmation | 5 | 6.59 | 7.06 | 2999 | 2599 | 1630 |
| B | 8 | candidate_selection | 5 | 0.03 | 0.07 | 0 | 0 | 0 |
| B | 9 | full_build_confirmation | 5 | 9.98 | 10.50 | 5524 | 258134 | 3785 |
| B | 10 | completion_preference | 5 | 2.00 | 2.07 | 0 | 261919 | 0 |
| B | 11 | candidate_selection | 5 | 0.14 | 0.14 | 0 | 0 | 0 |
| B | 12 | full_build_confirmation | 5 | 3.60 | 3.64 | 371 | 617936 | 248 |
| B | 13 | candidate_selection | 5 | 0.18 | 0.19 | 0 | 0 | 0 |
| B | 14 | full_build_confirmation | 5 | 0.23 | 0.28 | 0 | 4372 | 87 |

### conc-5-A

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 5 | 0.84 | 0.84 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 5 | 0.11 | 0.11 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 5 | 3.52 | 3.56 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 5 | 0.21 | 0.28 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 5 | 23.05 | 23.44 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 5 | 0.30 | 0.36 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 5 | 14.91 | 15.04 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 5 | 0.10 | 0.17 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 5 | 19.62 | 19.77 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 5 | 8.44 | 8.72 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 5 | 0.13 | 0.21 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 5 | 11.70 | 11.75 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 5 | 0.15 | 0.16 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 5 | 0.97 | 1.57 | 113 | 3363 | 97 |

### conc-10-A

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 10 | 1.61 | 1.67 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 10 | 0.48 | 0.49 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 10 | 7.50 | 7.69 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 10 | 0.43 | 0.69 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 10 | 48.36 | 49.37 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 10 | 0.54 | 0.69 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 10 | 32.39 | 32.59 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 10 | 0.20 | 0.32 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 10 | 40.43 | 42.34 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 10 | 22.53 | 26.01 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 10 | 0.03 | 0.04 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 10 | 36.15 | 42.73 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 10 | 0.21 | 0.39 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 10 | 1.00 | 2.43 | 113 | 3363 | 97 |

### conc-5-mix

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 3 | 0.82 | 0.82 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 3 | 0.09 | 0.09 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 3 | 5.26 | 5.27 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 3 | 0.14 | 0.19 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 3 | 26.90 | 27.22 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 3 | 0.20 | 0.22 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 3 | 14.64 | 14.70 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 3 | 0.09 | 0.09 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 3 | 18.53 | 19.14 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 3 | 5.73 | 5.85 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 3 | 0.08 | 0.08 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 3 | 8.13 | 8.39 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 3 | 0.08 | 0.08 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 3 | 0.75 | 1.19 | 113 | 3363 | 97 |
| B | 1 | bootstrap_intake | 2 | 2.67 | 2.68 | 0 | 0 | 0 |
| B | 2 | candidate_selection | 2 | 0.03 | 0.03 | 0 | 0 | 0 |
| B | 3 | full_build_confirmation | 2 | 17.64 | 17.65 | 1580 | 103 | 1601 |
| B | 4 | candidate_selection | 2 | 0.11 | 0.15 | 0 | 0 | 0 |
| B | 5 | full_build_confirmation | 2 | 22.19 | 22.36 | 2037 | 1561 | 1141 |
| B | 6 | candidate_selection | 2 | 0.32 | 0.36 | 0 | 0 | 0 |
| B | 7 | full_build_confirmation | 2 | 19.30 | 19.80 | 2999 | 2599 | 1630 |
| B | 8 | candidate_selection | 2 | 0.05 | 0.06 | 0 | 0 | 0 |
| B | 9 | full_build_confirmation | 2 | 25.13 | 25.59 | 5524 | 258134 | 3785 |
| B | 10 | completion_preference | 2 | 3.35 | 3.72 | 0 | 261919 | 0 |
| B | 11 | candidate_selection | 2 | 0.16 | 0.31 | 0 | 0 | 0 |
| B | 12 | full_build_confirmation | 2 | 6.52 | 6.95 | 371 | 617936 | 248 |
| B | 13 | candidate_selection | 2 | 0.19 | 0.62 | 0 | 0 | 0 |
| B | 14 | full_build_confirmation | 2 | 0.22 | 0.93 | 0 | 4372 | 87 |

### conc-10-mix

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 5 | 1.76 | 1.79 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 5 | 0.31 | 0.32 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 5 | 12.35 | 12.38 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 5 | 0.38 | 0.49 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 5 | 57.17 | 57.66 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 5 | 0.42 | 0.49 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 5 | 29.02 | 29.20 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 5 | 0.16 | 0.99 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 5 | 41.33 | 42.07 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 5 | 12.28 | 13.28 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 5 | 0.10 | 0.12 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 5 | 24.95 | 25.14 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 5 | 0.08 | 0.21 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 5 | 1.09 | 1.75 | 113 | 3363 | 97 |
| B | 1 | bootstrap_intake | 5 | 5.85 | 5.92 | 0 | 0 | 0 |
| B | 2 | candidate_selection | 5 | 0.17 | 0.19 | 0 | 0 | 0 |
| B | 3 | full_build_confirmation | 5 | 43.20 | 43.31 | 1580 | 103 | 1601 |
| B | 4 | candidate_selection | 5 | 0.40 | 0.47 | 0 | 0 | 0 |
| B | 5 | full_build_confirmation | 5 | 46.31 | 46.86 | 2037 | 1561 | 1141 |
| B | 6 | candidate_selection | 5 | 0.80 | 0.89 | 0 | 0 | 0 |
| B | 7 | full_build_confirmation | 5 | 41.50 | 41.82 | 2999 | 2599 | 1630 |
| B | 8 | candidate_selection | 5 | 0.12 | 0.18 | 0 | 0 | 0 |
| B | 9 | full_build_confirmation | 5 | 53.78 | 54.26 | 5524 | 258134 | 3785 |
| B | 10 | completion_preference | 5 | 10.27 | 10.31 | 0 | 261919 | 0 |
| B | 11 | candidate_selection | 5 | 0.91 | 0.98 | 0 | 0 | 0 |
| B | 12 | full_build_confirmation | 5 | 17.74 | 18.04 | 371 | 617936 | 248 |
| B | 13 | candidate_selection | 5 | 1.26 | 1.70 | 0 | 0 | 0 |
| B | 14 | full_build_confirmation | 5 | 0.98 | 1.10 | 0 | 4372 | 87 |

### conc-10-mix-sem1

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 5 | 0.09 | 0.17 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 5 | 0.02 | 0.03 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 5 | 0.73 | 0.74 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 5 | 0.04 | 0.04 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 5 | 8.59 | 9.01 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 5 | 0.06 | 0.06 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 5 | 3.15 | 3.18 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 5 | 0.01 | 0.02 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 5 | 5.84 | 6.02 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 5 | 1.56 | 1.58 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 5 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 5 | 2.49 | 2.50 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 5 | 0.03 | 0.03 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 5 | 0.37 | 0.47 | 113 | 3363 | 97 |
| B | 1 | bootstrap_intake | 5 | 0.44 | 0.45 | 0 | 0 | 0 |
| B | 2 | candidate_selection | 5 | 0.01 | 0.01 | 0 | 0 | 0 |
| B | 3 | full_build_confirmation | 5 | 6.77 | 9.04 | 1580 | 103 | 1601 |
| B | 4 | candidate_selection | 5 | 0.03 | 0.03 | 0 | 0 | 0 |
| B | 5 | full_build_confirmation | 5 | 6.28 | 6.34 | 2037 | 1561 | 1141 |
| B | 6 | candidate_selection | 5 | 0.08 | 0.09 | 0 | 0 | 0 |
| B | 7 | full_build_confirmation | 5 | 6.64 | 7.05 | 2999 | 2599 | 1630 |
| B | 8 | candidate_selection | 5 | 0.03 | 0.03 | 0 | 0 | 0 |
| B | 9 | full_build_confirmation | 5 | 10.00 | 10.56 | 5524 | 258134 | 3785 |
| B | 10 | completion_preference | 5 | 2.03 | 2.04 | 0 | 261919 | 0 |
| B | 11 | candidate_selection | 5 | 0.14 | 0.14 | 0 | 0 | 0 |
| B | 12 | full_build_confirmation | 5 | 3.52 | 3.56 | 371 | 617936 | 248 |
| B | 13 | candidate_selection | 5 | 0.19 | 0.19 | 0 | 0 | 0 |
| B | 14 | full_build_confirmation | 5 | 0.22 | 0.23 | 0 | 4372 | 87 |

### conc-10-mix-sem2

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 5 | 0.24 | 0.38 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 5 | 0.03 | 0.25 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 5 | 1.39 | 2.30 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 5 | 0.05 | 0.08 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 5 | 10.59 | 13.06 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 5 | 0.07 | 0.12 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 5 | 5.36 | 5.90 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 5 | 0.02 | 0.02 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 5 | 7.82 | 8.34 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 5 | 3.26 | 3.38 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 5 | 0.03 | 0.07 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 5 | 4.64 | 4.67 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 5 | 0.05 | 0.09 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 5 | 0.44 | 1.35 | 113 | 3363 | 97 |
| B | 1 | bootstrap_intake | 5 | 0.53 | 1.07 | 0 | 0 | 0 |
| B | 2 | candidate_selection | 5 | 0.01 | 0.01 | 0 | 0 | 0 |
| B | 3 | full_build_confirmation | 5 | 8.11 | 8.29 | 1580 | 103 | 1601 |
| B | 4 | candidate_selection | 5 | 0.03 | 0.04 | 0 | 0 | 0 |
| B | 5 | full_build_confirmation | 5 | 9.14 | 11.49 | 2037 | 1561 | 1141 |
| B | 6 | candidate_selection | 5 | 0.14 | 0.29 | 0 | 0 | 0 |
| B | 7 | full_build_confirmation | 5 | 9.32 | 13.59 | 2999 | 2599 | 1630 |
| B | 8 | candidate_selection | 5 | 0.03 | 0.07 | 0 | 0 | 0 |
| B | 9 | full_build_confirmation | 5 | 14.32 | 22.46 | 5524 | 258134 | 3785 |
| B | 10 | completion_preference | 5 | 2.41 | 3.48 | 0 | 261919 | 0 |
| B | 11 | candidate_selection | 5 | 0.23 | 0.35 | 0 | 0 | 0 |
| B | 12 | full_build_confirmation | 5 | 4.57 | 6.16 | 371 | 617936 | 248 |
| B | 13 | candidate_selection | 5 | 0.20 | 0.22 | 0 | 0 | 0 |
| B | 14 | full_build_confirmation | 5 | 0.24 | 0.29 | 0 | 4372 | 87 |

### conc-10-mix-sem3

| script | m | kind | n | p50 s | max s | HTTP | hits | misses |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | 1 | bootstrap_intake | 5 | 0.53 | 0.77 | 0 | 0 | 0 |
| A | 2 | candidate_selection | 5 | 0.04 | 0.06 | 0 | 0 | 0 |
| A | 3 | full_build_confirmation | 5 | 1.98 | 3.03 | 68 | 0 | 46 |
| A | 4 | candidate_selection | 5 | 0.08 | 0.09 | 0 | 0 | 0 |
| A | 5 | full_build_confirmation | 5 | 16.47 | 24.95 | 3665 | 529 | 2404 |
| A | 6 | candidate_selection | 5 | 0.11 | 0.15 | 0 | 0 | 0 |
| A | 7 | full_build_confirmation | 5 | 8.33 | 10.13 | 504 | 1937 | 355 |
| A | 8 | candidate_selection | 5 | 0.02 | 0.05 | 0 | 0 | 0 |
| A | 9 | full_build_confirmation | 5 | 11.34 | 12.42 | 2504 | 154702 | 2009 |
| A | 10 | completion_preference | 5 | 2.43 | 3.54 | 0 | 156711 | 0 |
| A | 11 | candidate_selection | 5 | 0.04 | 0.05 | 0 | 0 | 0 |
| A | 12 | full_build_confirmation | 5 | 4.82 | 6.77 | 239 | 327848 | 200 |
| A | 13 | candidate_selection | 5 | 0.07 | 0.14 | 0 | 0 | 0 |
| A | 14 | full_build_confirmation | 5 | 0.45 | 1.64 | 113 | 3363 | 97 |
| B | 1 | bootstrap_intake | 5 | 1.01 | 1.54 | 0 | 0 | 0 |
| B | 2 | candidate_selection | 5 | 0.02 | 0.03 | 0 | 0 | 0 |
| B | 3 | full_build_confirmation | 5 | 11.42 | 11.85 | 1580 | 103 | 1601 |
| B | 4 | candidate_selection | 5 | 0.07 | 0.10 | 0 | 0 | 0 |
| B | 5 | full_build_confirmation | 5 | 14.03 | 17.01 | 2037 | 1561 | 1141 |
| B | 6 | candidate_selection | 5 | 0.18 | 0.23 | 0 | 0 | 0 |
| B | 7 | full_build_confirmation | 5 | 12.59 | 14.39 | 2999 | 2599 | 1630 |
| B | 8 | candidate_selection | 5 | 0.05 | 0.06 | 0 | 0 | 0 |
| B | 9 | full_build_confirmation | 5 | 19.18 | 29.98 | 5524 | 258134 | 3785 |
| B | 10 | completion_preference | 5 | 4.91 | 6.09 | 0 | 261919 | 0 |
| B | 11 | candidate_selection | 5 | 0.34 | 0.52 | 0 | 0 | 0 |
| B | 12 | full_build_confirmation | 5 | 7.78 | 7.83 | 371 | 617936 | 248 |
| B | 13 | candidate_selection | 5 | 0.47 | 0.81 | 0 | 0 | 0 |
| B | 14 | full_build_confirmation | 5 | 0.47 | 1.05 | 0 | 4372 | 87 |

## Alone, per session (message 3 and 5)

The two script A games are separate threads in one process. `by_script` above pools them. Per session:

| session | script | m | wall s | HTTP | hits | misses |
|---:|---|---:|---:|---:|---:|---:|
| 0 | A | 3 | 0.77 | 68 | 0 | 46 |
| 0 | A | 5 | 8.95 | 3665 | 529 | 2404 |
| 0 | A | 10 | 1.53 | 0 | 156711 | 0 |
| 1 | A | 3 | 0.76 | 68 | 0 | 46 |
| 1 | A | 5 | 7.81 | 3665 | 529 | 2404 |
| 1 | A | 10 | 1.57 | 0 | 156711 | 0 |
| 2 | B | 3 | 6.77 | 1580 | 103 | 1601 |
| 2 | B | 5 | 6.36 | 2037 | 1561 | 1141 |
| 2 | B | 10 | 2.04 | 0 | 261919 | 0 |

