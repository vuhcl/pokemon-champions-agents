# Design draft: hosted, gamified, bring-your-own-model demo (v0, revision 2)

Status: draft after four fresh-context reviews (clarity, fit with code, key security, failure modes), 2026-11-04. Basis: ADR-086 (`adr_086_hosted_demo_draft_2026-11-04.md`). Repo reading: `/home/claude/vuhcl/pokemon-champions-agents`, commit 3016a89 (Nov 1; may lag main). Nothing here is built. Items marked **[D]** are decisions for Vu; the proposed default is stated and is used until Vu changes it.

## 1. Goal and non-goals

Goal: a polished, reliable web page where a visitor, using their own model key, tries to get the team-building agent to reproduce a target team (round 1, guided), then does it again in as few turns as possible (round 2). The score is computed by code. A second mode, **sandbox**, is plain free play with the agent: the same session, parsers and team panel, with no target, no score, no rounds and no turn counter, for a visitor who just wants to work with the agent.

Non-goals (v0): leaderboard, accounts, stored history, custom endpoints, comparing models, anything from phase 2 (evaluation) or phase 3. Sandbox mode does not add anything beyond a mode flag: no saved sessions, no sharing, no export.

Round 2 measures **efficiency of the dialogue** with this graph, not team-building skill (see section 5). The page says so.

## 2. What the code does (read; one timing run, nothing else executed)

Verified against commit 3016a89 by the reviewers, with file:line.

1. The product path is a LangGraph graph with two injected parsers (bootstrap intake, turn intent): `compile_cli_graph` in `recommender/graph.py:178`. The visitor's model parses text into intents; the deterministic graph builds the team. The eval arm (`scripts/eval/part_g_arm`) is a separate tool-calling harness and is not the demo path.
2. Parsers are bound at compile time (`graph.py:86-92`, `functools.partial` on `classify_input`); no other node holds a parser. Compiling takes about 0.044 s. **Decision: compile one graph per session**, sharing one checkpointer through `compile_graph(checkpointer=shared_saver, ...)` (`graph.py:168-175`). `compile_cli_graph` must not be used: it opens a new SQLite file per call.
3. The per-visitor key needs no change to `resolve_llm_parsers`: the builders `build_anthropic_bootstrap_intake_parser` (`bootstrap.py:212`) and `build_anthropic_turn_intent_parser` (`turn_intent.py:1298`) forward `**chat_kwargs` to `ChatAnthropic`, so `api_key=` is passed directly. `resolve_llm_parsers` (`llm_provider.py:59-80`) reads env vars and is not used by the web layer.
4. **Never put a credential in `config["configurable"]`.** LangGraph copies string configurable values into checkpoint metadata (`langgraph/checkpoint/base/__init__.py:765-775`) and tracing metadata; its only filter is a name match on key/token/secret/password/auth (`langgraph/_internal/_config.py:424-440`). `config` carries `thread_id` only.
5. Session identity: `mint_thread_id()` returns `team-<uuid4 hex>`; `thread_config(thread_id)` is the config. The CLI's resume logic is not used, and the web layer must never call `list_thread_summaries` (`session.py:49` documents a deadlock with nested queries during a listing).
6. Checkpointer today: `SqliteSaver` on one connection with `check_same_thread=False` (`checkpointer.py:112`); the library serializes access with a lock. Safe across threads for sync invokes, process-local, async methods raise `NotImplementedError`. **Decision (Vu, 2026-11-04): Redis**, so the UI can show a live thinking/pending status. I could not find a recorded settlement in the repo (`architecture_decisions.md` still defers Postgres/Redis; ADR-086 item 9 said "Redis favored if streaming is wanted"); this decision is now recorded in ADR-086. Not verified: that a LangGraph Redis checkpointer exists at the installed LangGraph version, that it accepts the project's msgpack allowlist (`checkpointer.py:58-84`), and what the status channel is (Redis pub/sub or a polled status key). That is a spike at the start of stream 2.
7. **Measured floor (Cursor follow-up 38 report, 2026-11-04; fake parsers through `compile_graph`, raw log `docs/hosted_demo/floor_run_output.json`; no model, no network).** The baseline path takes 3 user messages to one locked slot (`state["turn"]` 3), the path in `tests/recommender/test_cli_repl.py:867-910`. **2 turns is not reachable.** Vu expected 2 (draft the whole team with full builds, then lock it in); measured: one message naming six full builds drafts 0 slots and locks 0, because the bootstrap schema carries one anchor and a name pool, not builds (`bootstrap.py:67-78`), and the opening candidate list is capped at 3 (`bootstrap.py:647-648`). Accepting defaults from that screen reached six locked at turn 13, and those six are the graph's suggestions, not the named sets. The turn schema is one `turn_intent` and one `slot_index` (`turn_intent.py:78,188-189,449,1010-1016`; `nodes.py:1020-1022`); `full_build_confirmation` is one provisional slot and `lock` is blocked on that screen (`nodes_classify.py:169-171`). The model can express several intents (Vu saw the eval arm lock six slots in one turn), but the demo graph's schema cannot carry them, and a prompt change cannot fix that: the schema and `apply_lock` would have to take a list of slots. A compound message with several lock intents applies one lock and drops the rest **with no notice**; a list of intents fails validation and shows `CLASSIFY_FAIL_USER_MSG`. Message length: a 20,000-character message is delivered whole, so no cap is needed in process (a provider context window was not measured). Not measured: turns to reproduce a specific target's exact builds (the visitor must edit the graph's suggested build after each lock); a live model.
8. The CLI guards the web layer repeats (`cli.py:154-165`): no pending presentation with no turn-intent parser raises `NotImplementedError` (`NO_PENDING_MESSAGE`); with a parser wired, that case goes to gap-fill instead. A state with `candidate_discovery_error` and no pending presentation is answered by `format_no_pending(state)`. Other exceptions show `CLASSIFY_FAIL_USER_MSG`.
9. `state["turn"]` is incremented when the graph finishes a user message (`nodes.py:177`); a message that raises is never checkpointed and never counted.
10. Team state is `state["team_draft"]`: six `Slot`s of `Attr(value, locked, ...)`; a value can be present while `locked` is false; a provisional slot is held outside `team_draft` until confirmation. A fully locked slot refuses a second lock (`nodes.py:925-926`).
11. Rendering (`present_text.py`) is text-only; the team panel reads `team_draft` directly. Default format `DEFAULT_FORMAT_ID = "[Gen 9 Champions] VGC 2026 Reg M-C"`; some tests use Reg M-B. **[D6]** below (decided: Reg M-C).
12. **The two arm-tool defects reach the product path.** (a) `_apply_lock_single` (`nodes.py:972-1016`) and `_apply_locks_batch` validate species and item only; `check_set` runs in `commit_full_slot` (`nodes.py:848`) and `nodes_classify.py:819`. A moveset lock through gap-fill (`attr` in `_SLOT_ATTRS` includes moveset, `turn_intent.py:448-451`) would skip the learnset check; whether a model emits it is unverified. (b) `_tier1_direct` (`reconcile.py:679-685`) is case-sensitive against `Rain/Sun/Sand/Snow`, the product path stores components unnormalized, and the parser prompt itself says `components=["sun"]` (`turn_intent.py:135`). Both are launch blockers (section 10).

## 3. Architecture

- **Browser:** single-page app: target card, chat, live team panel, turn counter, score, glossary, key field with the disclaimer.
- **API** (provisional; thin service, sync handlers in a threadpool, one worker):
  - `POST /session` body `{provider, model, api_key, mode}` (`mode` is `game` or `sandbox`, default `game`) returns `{session_token, state_view}`. Builds that visitor's parsers and graph in memory. **It first makes one minimal provider call to check the key (decided 2026-11-04); a wrong key is reported at once and costs no turn.** The disclaimer says the demo makes this call. In `sandbox` mode the response and later `state_view`s carry no `target`, `round`, `score` or turn count, and `/round` and `/hint` return 404.
  - `POST /session/{token}/message` body `{text, expected_turn}` returns `{reply_text, state_view, turn, score}`. 409 if another message is in flight or `expected_turn` is stale (no turn counted).
  - `POST /session/{token}/key` body `{api_key}`: replaces the parsers in an existing session after a key failure, keeping the game.
  - `POST /session/{token}/round` starts round 2 (fresh thread, same target); 409 while a message is in flight.
  - `POST /session/{token}/hint` returns authored hint text (round 1 only).
  - `DELETE /session/{token}` drops parsers and key.
- **Session token:** `secrets.token_urlsafe(32)`, separate from the checkpoint `thread_id`; sent in a header, never a cookie or URL; kept out of logs.
- **State view:** a JSON projection: slots (field value, `locked`), pending kind (one of the kinds in `state.py:438`) and options (id, label, and the message text a button sends), notices, `prompt_text`, `round`, `turn`, `max_len`, `score`. No key, no raw state dump. Full JSON Schema plus two sample transcripts are written **first** (section 9, step 0) and are the contract for the front end and the target file.
- **Error envelope:** `{error: {code, message, retryable, counts_as_turn}}` with status codes fixed in the schema.

## 4. Key handling (requirements)

Rationale for server memory over per-request keys from the browser: the graph is stateful across messages and a per-request key would need re-sending and re-parser-building each turn; server memory with a short idle limit keeps one place to protect. The cost is a process that holds keys, so the following are requirements:

1. The key arrives over HTTPS in the `POST /session` or `/key` body only.
2. It lives only in the per-session parser objects (a `SecretStr`, never `repr`ed). Not in `os.environ` (the process also spawns a subprocess with `{**os.environ}`, `calc_service.py:49`), `config`, graph state, the checkpointer, logs, error reports or analytics. No shared fallback key: a host `ANTHROPIC_API_KEY` must never be used for a visitor.
3. Provider calls are wrapped and re-raised as a fixed-message exception `from None`, so no cause chain or frame local carries the client object. Error reporters (if any) run with frame-locals off. Request bodies are never logged.
4. **Tracing off:** the server sets `LANGSMITH_TRACING=false` and `LANGCHAIN_TRACING_V2=false` at startup and refuses to boot if either is "true"; a test asserts `tracing_is_enabled()` is false.
5. The tool log (`artifacts/tool_calls.jsonl`, `tool_log.py:15,18`) is pointed at a non-persistent location or disabled.
6. **Allowlist:** the provider enum excludes `ollama` and `none`; `model` is matched against a server-side list; no `**chat_kwargs` passthrough; `base_url` pinned and `ANTHROPIC_BASE_URL` set explicitly. No visitor-supplied URLs.
7. **Abuse limits:** body cap about 8 KB; `Content-Type: application/json` required; CORS allowlist of the demo origin only; per-IP and global rate limits; cap on live sessions; cap on in-flight model calls (`invoke_with_timeout` abandons threads on timeout, `llm_invoke.py:62-72`, so slow calls pile up); idle TTL 30 minutes and a maximum session lifetime.
8. With Redis the thread survives a restart but the key does not: after a restart the visitor re-enters the key via `POST /key` and the game resumes. Redis holds checkpoints only, never keys; its RDB/AOF files are in the canary scan. Session end (delete, idle timeout, max lifetime, process restart) drops all references to the key. The page says "dropped", not "erased": Python cannot zero strings. Core dumps disabled on the host.
9. **Canary test before launch** (necessary, not sufficient): run full games, including deliberate 401, 429 and timeout failures and a fake provider that echoes its Authorization header into its error text, with a canary key; then scan for the canary and its base64, URL-encoded and last-8 forms in: the SQLite file and its `-wal` and `-shm`, stdout and stderr, access and application logs, `tool_calls.jsonl`, HTTP responses, the process environment, and a run with debug logging on. Also assert `os.environ` is unchanged after a session.
10. The disclaimer is written against the final implementation and checked line by line against these requirements.

## 5. Scoring and rounds

**Target:** a stored file of six members: species, item, ability, four moves. Spread and nature are not scored in v0.

**Score function** (one pure function, unit-tested): reads `team_draft` and counts a field only if `attr.locked` and the value is not None; unlocked or provisional values score nothing.
- Compare normalized ids (via `recommender/ids.py` and `forme_identity.py`), never display strings.
- Match slots to target members one-to-one by species; duplicate species cannot match the same target member twice; slot order is ignored.
- Moves compared as sets of four after dedupe.
- Mega: the target stores base species plus the mega stone (the game is item-driven, `species_forms.py`); scoring uses the same representation as the team state. To be confirmed by a unit test with a real mega pair.
- Reported: **members fully matched out of six** is the single number that ends a round; fields matched out of 24 is shown for feedback.

**Turn:** the increase in `state["turn"]` across an invoke; the page shows only that number. **The graph counts everything that finishes an invoke (D9, decided): a refused action (illegal pick, locking a fully locked slot), `NO_PENDING_MESSAGE`, a parser failure (`CLASSIFY_FAIL_USER_MSG`) and a bootstrap provider failure all increment the counter and are checkpointed** (`nodes.py:177`, `turn_intent.py:1136-1140`, `bootstrap.py:146-149`; verified by the floor run). The page says so in plain words: a message that fails to parse still uses a turn. These do not count because they never reach the graph: 409s, requests rejected at the API layer, hint use in round 1. A timeout checks `state["turn"]` before reporting, so a late checkpoint write is not silently counted. Decided 2026-11-04: `POST /session` makes one minimal provider call to check the key (no turn), so a wrong key costs no turns; the disclaimer says it makes that call.

**Round 1:** guided; hints free; any number of turns; ends at six of six.

**Round 2 (D8, decided: keep as is, no graph change):** fresh thread, same target; prompt text provisional ("Now you can be a Pokémon Champion yourself! Next, why don't you try to do it in as few turns as possible?"). Ends at six of six matching the target; the result is turns taken. **No promise about a minimum, and no message cap N** (the floor run found none needed). The page does not show a floor figure: the measured 13 is for accepting graph suggestions, not for reproducing a target, so showing it would mislead. Stream 1 instead produces a scripted reference run per target with fake parsers (turns to reproduce that target's exact builds), recorded in the target file; whether to show it is decided once it exists. Because the graph needs several messages per slot, round 2 measures dialogue efficiency with this graph, not team-building skill, and the page says so. If the target's sets equal the featured defaults, accepting suggestions wins in 13 turns, so targets should differ from the defaults on some slots. Hints are off in round 2. A give-up button ends round 2 and shows the team and the target side by side.

**Best result** is kept in the browser only. A server restart pauses a running round until the key is re-entered.

## 6. Help layer

Static authored copy, no model-written explanations (the copy tells visitors to make one change per message, because extra lock intents in a message are dropped without notice, and that a message that fails to parse still uses a turn): a glossary of about ten terms as tooltips; clickable starter messages (each maps to message text); a hint button returning one authored line per stage; tool or graph results supply specifics. Copy is reviewed by Vu. **Lock-in reminder (authored, required):** the score counts locked fields only (section 5), so a drafted team that is not locked scores zero. The page says so in three places: (1) in the round 1 and round 2 intro text ("Drafted is not locked: your team only counts once you lock it in"); (2) in the team panel, where drafted and locked fields look different and a banner appears whenever a drafted team has unlocked fields ("Your team is drafted but not locked yet. Lock it in to be scored"), with a one-click "Lock it in" starter message; (3) at the end of a round, if the visitor gives up with unlocked fields, the result screen names them. Exact wording is Vu's. The banner is driven by the `locked` flags in the state view, not by the model's text. **Frequency (Vu: don't nag):** the intro line shows once per round. **Trigger (Vu, simplest rule):** the banner shows only when the drafted team already satisfies the grader and only locking is missing: the score function run over drafted values (ignoring lock flags) gives six of six, while the locked-only score is below six. This covers a fully drafted, partly locked team, and it cannot fire while the draft is still wrong or incomplete, so it does not fire on every edit. Dismissing it hides it for the rest of the round; it also appears on the give-up screen if the condition holds. No repeat toast or modal. The score function therefore takes an `include_unlocked` option, and the banner is computed from the state view, not from the model's text. Two consequences: the banner tells the visitor their draft is correct, which is acceptable in round 1 and counts as a free hint in round 2 (a visitor in round 2 learns the draft matches only by seeing the banner; accepted, since it costs no turn and the lock turn counts anyway); and a visitor whose draft is wrong gets no reminder, so the intro line carries that case. Terms used on the page are defined on the page (slot, lock, pending choice); internal words (arm, pin, `Attr`) do not appear. Sandbox mode reuses the glossary, starter messages and key field, and drops the target card, hint button, lock-in banner and scoring; its intro line says there is no score and the team is not graded.

## 7. Failure cases (each gets a plain message and a path that keeps the game)

| Case | Behavior | Counts as turn |
|---|---|---|
| Wrong, expired or unauthorized key | Message; visitor re-enters via `POST /key`; game kept | no |
| Provider rate limit or outage | Message; retry button. On the bootstrap path the graph counts it as a turn (D9) | yes (graph counts it); API-layer failures before the graph: no |
| Slow turn / hung model | Progress indicator; timeout message; before reporting, check `state["turn"]` so a late checkpoint write is not silently counted; the worker is cancelled where the client allows | no |
| Parser cannot use model output | `CLASSIFY_FAIL_USER_MSG`; the graph counts it and checkpoints it (`turn_intent.py:1136-1140`) | yes (D9) |
| Refused action (illegal pick) | Graph's own message | yes |
| Double submit, or second tab | 409 while in flight or if `expected_turn` is stale; per-session lock | no |
| `POST /round` while a message is in flight | 409 | no |
| Tab closed | No server action; idle TTL drops the key; game ends | n/a |
| Server restart | Thread kept in Redis; visitor re-enters the key and resumes | n/a |
| Unsupported or untested model | Warning before the game, not a block | n/a |

## 8. Tests

- **Unit:** score function (full, partial, empty, extra members, wrong order, mega pair, forme alias, duplicate species, locked species with unlocked item, unlocked value scoring nothing); state projection (no key fields); the CLI guards; turn counter on success and on every failure path.
- **UI:** the lock-in banner stays hidden for an incomplete or wrong draft, shows when the drafted team scores six of six with `include_unlocked` but below six locked (including a partly locked team), stays hidden after dismissal, and clears once all are locked; the score function is tested with and without `include_unlocked`; the "Lock it in" starter sends the message the graph accepts as confirmation.
- **Sandbox:** a `sandbox` session returns no target, round, score or turn count; `/round` and `/hint` return 404; the same key-handling, limit and concurrency tests apply to both modes.
- **Integration:** scripted game with a fake parser to six of six, plus a per-target reference run (turns to reproduce that target's exact builds); compound-message behavior (one lock applied, the rest dropped, and the page's help text matches); a long message delivered whole (no cap); two concurrent sessions with different fake keys never share a parser; double submit and two tabs on one session; timeout leaves no counted turn; threaded invokes on the shared checkpointer (Redis for the demo; `SqliteSaver` in dev); tracing-off assertion; allowlist rejects `ollama` and unlisted models; limits (body size, rate, session cap).
- **Security:** the canary scan (section 4 item 9).
- **Manual:** real key against Anthropic through every failure case; mobile width.
- **Acceptance (initial; Vu to adjust):** a first-time visitor with a valid key reaches six of six in round 1 without outside help; page usable at phone width; 10 concurrent sessions on one worker with no cross-talk; every row in section 7 produces its message.

## 9. Work split for Cursor

0. **Contract first (Elephant, before any stream):** JSON Schema for the endpoints and `state_view`, the error envelope, two sample transcripts, the target-file schema, and a fake-parser fixture. Streams 3 and 4 depend on this, not on stream 1.
1. **Engine adapter:** a scripted reference run per target with fake parsers (turns to reproduce that target's exact builds; recorded in the target file); per-session graph (compile per session, shared saver), explicit credentials, guards, projection, score function, scripted-game floor run. Python.
2. **API and sessions:** first a spike on the Redis checkpointer and status channel (section 2 item 6); then endpoints, per-session locks and limits, timeouts, sanitized errors, tracing-off check, canary test. Python.
3. **Front end:** page, tooltips, starter messages, failure states. Vu steers the look.
4. **Target data:** target file with source, event, player and legality check against the pin. Gated on the source sites' terms.

Launch checklist: the P1 (`check_set` skip) and P2 (archetype case) fixes landed after the pin; the page states the system is shown as of the pin; the canary test passes; the disclaimer matches the code; terms of the target source read.

## 10. Decisions for Vu

Decided by Vu, 2026-11-04:
- **D1** Round 2: fewest turns, with no promised minimum. Superseded by D8: the floor run showed a message naming six builds drafts and locks 0 slots, and 2 turns is not reachable on this graph (section 5).
- **D2** Providers: Anthropic plus one more; the second is OpenAI (see D7). The builder (bootstrap intake and turn intent, with explicit `api_key`) and a tested-models entry are new work in stream 1.
- **D3** Checkpointer: Redis (section 2 item 6), with a spike first.
- **D4** Hints off in round 2. **D5** No easy mode in v0.
- **D6** Regulation: Reg M-C, the code's default format string and the active regulation in `data/active_regulation.json` as of 2026-11-04 (defaults accepted). Tests that use Reg M-B and the project memory's M-B wording are stale for the demo. Target legality is checked under M-C.
- **D7** Second provider: OpenAI (default accepted).
- **D8** Round 2: keep as is with no graph change (see section 5).
- **D9** Parser and provider failures count as a turn, as the graph does: decided for v0. The graph fix (`nodes.py:177`) is not part of v0; it would land as a revision after the pin if wanted later.

Still to approve: this design draft as a whole.

Other measured facts from the contract work: a dropped remainder of a compound message is **not** a visible failure (extra lock intents are dropped with no notice), so the page cannot promise to flag it and the help text must say one change per message works best; `state_view` carries `provisional_slot` because `full_build_confirmation` lives outside `team_draft`; graph options have species only, so the API projects `id`/`label`/`send_text`; the graph has no `round`; the Redis spike must allowlist the msgpack types the run warned about (`Attr`, `Slot`, `ProvisionalSlot`, matchup and teammate types); P1 and P2 are still open.

## 11. Still open (not blocking the draft)

Hosting provider; tested-models list; logging policy (proposed: no request bodies, no per-visitor logs beyond counts); target team and its terms (should pass `check_set` under M-C and differ from the graph's featured defaults on some slots); whether the Claude API credit block in ADR-058 is cleared; the ADR number.
