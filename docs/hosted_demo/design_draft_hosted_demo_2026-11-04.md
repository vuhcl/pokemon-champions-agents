# Design draft: hosted, gamified, bring-your-own-model demo (v0, revision 2)

Status: draft after four fresh-context reviews (clarity, fit with code, key security, failure modes), 2026-11-04. Basis: ADR-086 (`adr_086_hosted_demo_draft_2026-11-04.md`). Repo reading: `/home/claude/vuhcl/pokemon-champions-agents`, commit 3016a89 (Nov 1; may lag main). Nothing here is built. Items marked **[D]** are decisions for Vu; the proposed default is stated and is used until Vu changes it.

## 1. Goal and non-goals

Goal: a polished, reliable web page where a visitor, using their own model key, tries to get the team-building agent to reproduce a target team (round 1, guided), then does it again in as few turns as possible (round 2). The score is computed by code.

Non-goals (v0): leaderboard, accounts, stored history, custom endpoints, comparing models, anything from phase 2 (evaluation) or phase 3.

Round 2 measures **efficiency of the dialogue** with this graph, not team-building skill (see section 5). The page says so.

## 2. What the code does (read; one timing run, nothing else executed)

Verified against commit 3016a89 by the reviewers, with file:line.

1. The product path is a LangGraph graph with two injected parsers (bootstrap intake, turn intent): `compile_cli_graph` in `recommender/graph.py:178`. The visitor's model parses text into intents; the deterministic graph builds the team. The eval arm (`scripts/eval/part_g_arm`) is a separate tool-calling harness and is not the demo path.
2. Parsers are bound at compile time (`graph.py:86-92`, `functools.partial` on `classify_input`); no other node holds a parser. Compiling takes about 0.044 s. **Decision: compile one graph per session**, sharing one checkpointer through `compile_graph(checkpointer=shared_saver, ...)` (`graph.py:168-175`). `compile_cli_graph` must not be used: it opens a new SQLite file per call.
3. The per-visitor key needs no change to `resolve_llm_parsers`: the builders `build_anthropic_bootstrap_intake_parser` (`bootstrap.py:212`) and `build_anthropic_turn_intent_parser` (`turn_intent.py:1298`) forward `**chat_kwargs` to `ChatAnthropic`, so `api_key=` is passed directly. `resolve_llm_parsers` (`llm_provider.py:59-80`) reads env vars and is not used by the web layer.
4. **Never put a credential in `config["configurable"]`.** LangGraph copies string configurable values into checkpoint metadata (`langgraph/checkpoint/base/__init__.py:765-775`) and tracing metadata; its only filter is a name match on key/token/secret/password/auth (`langgraph/_internal/_config.py:424-440`). `config` carries `thread_id` only.
5. Session identity: `mint_thread_id()` returns `team-<uuid4 hex>`; `thread_config(thread_id)` is the config. The CLI's resume logic is not used, and the web layer must never call `list_thread_summaries` (`session.py:49` documents a deadlock with nested queries during a listing).
6. Checkpointer today: `SqliteSaver` on one connection with `check_same_thread=False` (`checkpointer.py:112`); the library serializes access with a lock. Safe across threads for sync invokes, process-local, async methods raise `NotImplementedError`. **Decision (Vu, 2026-11-04): Redis**, so the UI can show a live thinking/pending status. I could not find a recorded settlement in the repo (`architecture_decisions.md` still defers Postgres/Redis; ADR-086 item 9 said "Redis favored if streaming is wanted"); this decision is now recorded in ADR-086. Not verified: that a LangGraph Redis checkpointer exists at the installed LangGraph version, that it accepts the project's msgpack allowlist (`checkpointer.py:58-84`), and what the status channel is (Redis pub/sub or a polled status key). That is a spike at the start of stream 2.
7. The end-to-end test takes **3** messages from an empty team to one locked slot, one intent per message. That is an example path, **not a floor**: the visitor's model can express several intents in one message, and the eval request set's one-intent-per-row shape is an eval design choice (tractable to run and to judge), not a limit of the model. What decides the real floor is the demo graph's parser schema. The path in the test (`tests/recommender/test_cli_repl.py:867-910`): the first invoke is system-only and yields a bootstrap prompt; message 1 (parsed by the visitor's model) yields candidate selection; message 2 ("yes") yields full-build confirmation; message 3 ("yes") locks. Messages 2 and 3 need no model. A reviewer's code reading said the demo graph locks at most one slot per message (one turn-intent per message; a batch lock carries one `slot_index`). **Vu observed otherwise in the eval arm**: a request row asking for Gholdengo ended up locking six slots in one turn, and the model handles several intents per message. The arm is a tool-calling harness, so the open question is the demo graph's parser schema, not the model. If the schema allows one intent per message, a visitor's compound message is parsed into one action and the rest is dropped, which the page must handle (the dropped part is a failure case, not a silent loss). Treat "several slots per message" as likely for the model and unverified for the demo graph. A scripted run through the demo graph, with a compound message, settles it before N is set.
8. The CLI guards the web layer repeats (`cli.py:154-165`): no pending presentation with no turn-intent parser raises `NotImplementedError` (`NO_PENDING_MESSAGE`); with a parser wired, that case goes to gap-fill instead. A state with `candidate_discovery_error` and no pending presentation is answered by `format_no_pending(state)`. Other exceptions show `CLASSIFY_FAIL_USER_MSG`.
9. `state["turn"]` is incremented when the graph finishes a user message (`nodes.py:177`); a message that raises is never checkpointed and never counted.
10. Team state is `state["team_draft"]`: six `Slot`s of `Attr(value, locked, ...)`; a value can be present while `locked` is false; a provisional slot is held outside `team_draft` until confirmation. A fully locked slot refuses a second lock (`nodes.py:925-926`).
11. Rendering (`present_text.py`) is text-only; the team panel reads `team_draft` directly. Default format `DEFAULT_FORMAT_ID = "[Gen 9 Champions] VGC 2026 Reg M-C"`; some tests use Reg M-B. **[D6]** below.
12. **The two arm-tool defects reach the product path.** (a) `_apply_lock_single` (`nodes.py:972-1016`) and `_apply_locks_batch` validate species and item only; `check_set` runs in `commit_full_slot` (`nodes.py:848`) and `nodes_classify.py:819`. A moveset lock through gap-fill (`attr` in `_SLOT_ATTRS` includes moveset, `turn_intent.py:448-451`) would skip the learnset check; whether a model emits it is unverified. (b) `_tier1_direct` (`reconcile.py:679-685`) is case-sensitive against `Rain/Sun/Sand/Snow`, the product path stores components unnormalized, and the parser prompt itself says `components=["sun"]` (`turn_intent.py:135`). Both are launch blockers (section 10).

## 3. Architecture

- **Browser:** single-page app: target card, chat, live team panel, turn counter, score, glossary, key field with the disclaimer.
- **API** (provisional; thin service, sync handlers in a threadpool, one worker):
  - `POST /session` body `{provider, model, api_key}` returns `{session_token, state_view}`. Builds that visitor's parsers and graph in memory.
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

**Turn:** the increase in `state["turn"]` across a successful invoke. The page shows only that number. A refused action (illegal pick, `NO_PENDING_MESSAGE`) is a successful invoke and counts; this blocks free probing. These do not count: provider errors, timeouts, parser failure (`CLASSIFY_FAIL_USER_MSG`; nothing is checkpointed), 409s, hint use in round 1.

**Round 1:** guided; hints free; any number of turns; ends at six of six.

**Round 2:** fresh thread, same target; prompt text provisional ("Now you can be a Pokémon Champion yourself! Next, why don't you try to do it in as few turns as possible?"). Ends at six of six; the result is turns taken. Vu's view: the fastest route is to ask for the team outright, so the floor may be well below 3 messages per slot. What I verified: the product path has per-species featured sets (`featured_or_common_set`, used by `propose.py` and `slot_fill.py`) as default builds, not a whole-team lookup. Not verified: whether one message naming all six species and sets can lock six slots (section 2 item 7). A scripted run with a fake parser settles it and gives the floor, shown next to the visitor's turns if it turns out to be informative. **Expected floor: 2 turns (Vu, 2026-11-04)**: one turn to draft the whole team with full builds, one to lock it in. A perfect round 2 is therefore 2, and pasting the full target in turn 1 is the intended best play, not a trick. That removes the trivial-win rationale for a message-length cap; N is dropped unless the scripted run shows a problem (for example the parser dropping part of a long message). Not verified: that the demo graph can draft six full builds in one turn and lock them in one confirmation (it has a `full_build_confirmation` step per slot today). The scripted run checks whether 2 is reachable. Things to check in that run: (a) if the target's sets equal the featured defaults, naming six species wins in a few turns, so targets should be chosen with that in mind; (b) the message cap N (characters, set after the run) matters only if a long compound message can lock several slots. Hints are off in round 2. A give-up button ends round 2 and shows the team and the target side by side.

**Best result** is kept in the browser only. A server restart pauses a running round until the key is re-entered.

## 6. Help layer

Static authored copy, no model-written explanations: a glossary of about ten terms as tooltips; clickable starter messages (each maps to message text); a hint button returning one authored line per stage; tool or graph results supply specifics. Copy is reviewed by Vu. **Lock-in reminder (authored, required):** the score counts locked fields only (section 5), so a drafted team that is not locked scores zero. The page says so in three places: (1) in the round 1 and round 2 intro text ("Drafted is not locked: your team only counts once you lock it in"); (2) in the team panel, where drafted and locked fields look different and a banner appears whenever a drafted team has unlocked fields ("Your team is drafted but not locked yet. Lock it in to be scored"), with a one-click "Lock it in" starter message; (3) at the end of a round, if the visitor gives up with unlocked fields, the result screen names them. Exact wording is Vu's. The banner is driven by the `locked` flags in the state view, not by the model's text. **Frequency (Vu: don't nag):** the intro line shows once per round. **Trigger (Vu, simplest rule):** the banner shows only when the drafted team already satisfies the grader and only locking is missing: the score function run over drafted values (ignoring lock flags) gives six of six, while the locked-only score is below six. This covers a fully drafted, partly locked team, and it cannot fire while the draft is still wrong or incomplete, so it does not fire on every edit. Dismissing it hides it for the rest of the round; it also appears on the give-up screen if the condition holds. No repeat toast or modal. The score function therefore takes an `include_unlocked` option, and the banner is computed from the state view, not from the model's text. Two consequences: the banner tells the visitor their draft is correct, which is acceptable in round 1 and counts as a free hint in round 2 (a visitor in round 2 learns the draft matches only by seeing the banner; accepted, since it costs no turn and the lock turn counts anyway); and a visitor whose draft is wrong gets no reminder, so the intro line carries that case. Terms used on the page are defined on the page (slot, lock, pending choice); internal words (arm, pin, `Attr`) do not appear.

## 7. Failure cases (each gets a plain message and a path that keeps the game)

| Case | Behavior | Counts as turn |
|---|---|---|
| Wrong, expired or unauthorized key | Message; visitor re-enters via `POST /key`; game kept | no |
| Provider rate limit or outage | Message; retry button | no |
| Slow turn / hung model | Progress indicator; timeout message; before reporting, check `state["turn"]` so a late checkpoint write is not silently counted; the worker is cancelled where the client allows | no |
| Parser cannot use model output | `CLASSIFY_FAIL_USER_MSG`; nothing checkpointed | no |
| Refused action (illegal pick) | Graph's own message | yes |
| Double submit, or second tab | 409 while in flight or if `expected_turn` is stale; per-session lock | no |
| `POST /round` while a message is in flight | 409 | no |
| Tab closed | No server action; idle TTL drops the key; game ends | n/a |
| Server restart | Thread kept in Redis; visitor re-enters the key and resumes | n/a |
| Unsupported or untested model | Warning before the game, not a block | n/a |

## 8. Tests

- **Unit:** score function (full, partial, empty, extra members, wrong order, mega pair, forme alias, duplicate species, locked species with unlocked item, unlocked value scoring nothing); state projection (no key fields); the CLI guards; turn counter on success and on every failure path.
- **UI:** the lock-in banner stays hidden for an incomplete or wrong draft, shows when the drafted team scores six of six with `include_unlocked` but below six locked (including a partly locked team), stays hidden after dismissal, and clears once all are locked; the score function is tested with and without `include_unlocked`; the "Lock it in" starter sends the message the graph accepts as confirmation.
- **Integration:** scripted game with a fake parser to six of six, which also measures the floor; compound-message behavior and cap enforcement; two concurrent sessions with different fake keys never share a parser; double submit and two tabs on one session; timeout leaves no counted turn; threaded invokes on the shared `SqliteSaver`; tracing-off assertion; allowlist rejects `ollama` and unlisted models; limits (body size, rate, session cap).
- **Security:** the canary scan (section 4 item 9).
- **Manual:** real key against Anthropic through every failure case; mobile width.
- **Acceptance (initial; Vu to adjust):** a first-time visitor with a valid key reaches six of six in round 1 without outside help; page usable at phone width; 10 concurrent sessions on one worker with no cross-talk; every row in section 7 produces its message.

## 9. Work split for Cursor

0. **Contract first (Elephant, before any stream):** JSON Schema for the endpoints and `state_view`, the error envelope, two sample transcripts, the target-file schema, and a fake-parser fixture. Streams 3 and 4 depend on this, not on stream 1.
1. **Engine adapter:** per-session graph (compile per session, shared saver), explicit credentials, guards, projection, score function, scripted-game floor run. Python.
2. **API and sessions:** first a spike on the Redis checkpointer and status channel (section 2 item 6); then endpoints, per-session locks and limits, timeouts, sanitized errors, tracing-off check, canary test. Python.
3. **Front end:** page, tooltips, starter messages, failure states. Vu steers the look.
4. **Target data:** target file with source, event, player and legality check against the pin. Gated on the source sites' terms.

Launch checklist: the P1 (`check_set` skip) and P2 (archetype case) fixes landed after the pin; the page states the system is shown as of the pin; the canary test passes; the disclaimer matches the code; terms of the target source read.

## 10. Decisions for Vu

Decided by Vu, 2026-11-04:
- **D1** Round 2: fewest turns; the fast route is to ask for the team outright (floor to be measured, section 5).
- **D2** Providers: Anthropic plus one more. **Which one is not chosen.** Default if not stated: OpenAI. The builder (bootstrap intake and turn intent, with explicit `api_key`) and a tested-models entry are new work in stream 1.
- **D3** Checkpointer: Redis (section 2 item 6), with a spike first.
- **D4** Hints off in round 2. **D5** No easy mode in v0.

Open:
- **D6** Which regulation the demo and target must match: Reg M-C (the default format string; proposed) or other. Some tests use Reg M-B, and the project memory still says M-B.
- **D7** The second provider.

## 11. Still open (not blocking the draft)

Hosting provider; message cap N (after the floor run); tested-models list; logging policy (proposed: no request bodies, no per-visitor logs beyond counts); target team and its terms; whether the Claude API credit block in ADR-058 is cleared; the ADR number.
