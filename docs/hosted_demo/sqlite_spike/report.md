# SqliteSaver spike (2026-11-04)

D3 is one shared `SqliteSaver` (`open_sqlite_checkpointer`: one connection, `check_same_thread=False`, the project msgpack allowlist). Fake parsers only. Calc on 127.0.0.1:4173 was the main checkout at the same commit as this branch. Scripts: `sqlite_checks.py`, `stream_checks.py`.

## Concurrency

10 sessions, each its own `compile_graph(checkpointer=shared_saver)` and `thread_id`, two user messages each, from a 10-thread pool.

No exceptions. No cross-talk (`obs_thread_id` matched the session, and no session history contained another session's text). Every final `turn` was 2, which is the two messages sent. Wall clock 1.946 s.

## Restart

A child process played format-id plus "Rain with Pelipper", "yes", "yes" (turn 3), wrote a marker, and was killed with SIGKILL. A new process, new fake parsers, same file and `thread_id`, read the checkpoint and sent one more "yes".

Normalized state matched the pre-kill marker. `turn` was 3 before the extra message and 4 after. Revived `TargetRoleDecision.evidence` is a `list`. The saver already documents that ormsgpack revives tuples as lists, so a raw `==` against the pre-kill objects fails for that reason. The normalized fingerprint matched, and no field was dropped.

## Allowlist

No msgpack warnings on the file-backed saver.

The turn-3 checkpoint contained `Attr`, `Slot`, `CandidateEvidence`, `ReasonRef`, `TargetRoleDecision`. A two-message stop in the earlier run also contained `ProvisionalSlot` and `PendingSlotIntent`.

An accept-defaults walk (turn 14, six locked) round-tripped `MatchupResult` and `MatchupCaveats` in the final checkpoint. An intermediate checkpoint in that walk also round-tripped `SharedTeammate`, `SharedTeammateQueryResult`, `TeammateEvidence`, and `TeammateQueryResult` with no warning. Those teammate objects are not still in the final checkpoint; a later step clears them.

## Files

While a connection is open the directory can contain `checkpoints.db`, `checkpoints.db-wal`, and `checkpoints.db-shm`. After `conn.close()` this run left `checkpoints.db` only. The canary scan should cover the `-wal` and `-shm` files anyway, because they are present during use.

## Streaming (installed LangGraph 1.2.9 and 1.2.14)

`StreamMode` at both versions: `values`, `updates`, `checkpoints`, `tasks`, `debug`, `messages`, `custom`.

On a one-node graph whose body sleeps 0.2 s:

- `tasks`: a start event (`id`, `name`, `input`, `triggers`) at 0.0 s, then a result after the sleep. Same on 1.2.14.
- `debug`: a `task` event at 0.0 s, then `task_result` after the sleep. Same on 1.2.14.
- `updates`: one event after the sleep (about 0.20 s). No start event.
- `values`: state before the node and state after the sleep. The first value is not a node name.
- `checkpoints`: nothing without a checkpointer. With `MemorySaver`, events at the start and again after the node. The payload is a checkpoint, not a node-start name.
- `messages` and `custom`: nothing from this node. `messages` needs a chat model. `custom` needs a `StreamWriter` inside the node.

On the recommender graph, `stream_mode="tasks"` delivered `classify_input` start before the fake parser returned from a 0.605 s sleep. That is a usable start signal. The label can change while the parser is still inside the node.

Node starts, in order, for the baseline three user messages:

1. `classify_input`, `record_bootstrap_response`, `route_team_phase`, `bootstrap_direction`
2. `classify_input`, `refine_provisional_slot`
3. `classify_input`, `commit_full_slot`, `route_team_phase`, `discover_single_locked`

The six-paste message took the same path as step 1. `classify_input` is the parser call. `bootstrap_direction` and `discover_single_locked` are the other slow steps. Their start events also fire before those bodies return.

Invoke and `tasks` stream matched on the baseline (turn 3), the six-paste (turn 1), and accept-defaults (turn 14, 15 trace rows). A parser that raises finished at turn 1, still `bootstrap_intake`, for both. A parser that sleeps left `turn` at 0 while it was inside the node, and at 1 after it finished, for both. `get_state` during the sleep returned in under 0.002 s.

`MemorySaver` (stream comparison only, no allowlist) printed unregistered-type warnings, including the matchup and teammate types. The file-backed saver with the project allowlist did not.
