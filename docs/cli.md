# Pokémon Champions team builder — CLI

CLI usage guide. Project scope, architecture, and 0.2 status live in the [root README](../README.md).

Interactive CLI for the VGC team-building recommender. Assumes project deps are already installed (`uv sync` or equivalent).

## Quick start

```bash
python -m recommender --new
```

On first run (or any new session), you get a **bootstrap** prompt asking for a direction, an anchor, which Pokémon you have available, or `you pick`. Reply in plain text at the `>` prompt. The next turn is another plain-text block (candidates, a build to confirm, and so on).

A typical turn looks like:

1. The CLI prints a prompt (and a footer like `Reply with a direction, anchor, available pool, or 'you pick'.`).
2. You type a reply after `>`.
3. The CLI prints the next prompt or result.

The thread id is printed on stderr at startup: `(thread team-…)`.

**Bootstrap free-form replies need an LLM provider** (default: Ollama). See [LLM provider setup](#llm-provider-setup). Without one, empty-team intake fails closed.

**Matchup verification and coverage/threat analysis need the calc service running.** See [Calc service setup](#calc-service-setup). Without it, `single_locked` degrades to lower-confidence estimates; `multi_locked` fails closed with a clear error rather than presenting anything.

## CLI flags

Entry point: `python -m recommender` (`recommender/cli.py`).

| Flag | What it does |
|------|----------------|
| `--new` | Start a new session (new thread id). Mutually exclusive with `--thread`. |
| `--thread ID` | Resume that exact thread. Exits with code 2 and `Unknown thread: …` if it does not exist. Mutually exclusive with `--new`. |
| `--list-threads` | List known threads (id, phase, locked count, pending kind, incomplete/complete) and exit. Prints `(no threads)` if none. |
| `--format ID` | Format id for **new** sessions. Default: `[Gen 9 Champions] VGC 2026 Reg M-B`. |
| `--provider {ollama,anthropic,none}` | Override `POKEMON_CHAMPIONS_LLM_PROVIDER` for this process. If omitted, the env var is used; if that is also unset, the default is **`ollama`**. |
| `--db PATH` | Override the SQLite checkpoint DB path for this process (else `POKEMON_CHAMPIONS_CHECKPOINT_DB` / platform default). |

With **no** `--new` / `--thread`, the CLI resumes the newest incomplete thread, or starts a new one if none exist.

## Session persistence

Sessions are stored in a SQLite checkpoint database.

**Default location** (`recommender/checkpointer.py`):

- **macOS:** `~/Library/Application Support/pokemon-champions-agents/checkpoints.db`
- **Linux / other:** `$XDG_DATA_HOME/pokemon-champions-agents/checkpoints.db` (or `~/.local/share/pokemon-champions-agents/checkpoints.db` if `XDG_DATA_HOME` is unset)

**Override:**

- Env: `POKEMON_CHAMPIONS_CHECKPOINT_DB` (path; `~` is expanded)
- Flag: `--db PATH` (wins for that process)

**Resuming in practice:**

- No flags → newest incomplete thread, or a fresh session if nothing incomplete exists
- `--thread ID` → that thread only
- `--new` → always a new thread (`team-` + hex uuid)

Ctrl+C at the prompt saves and exits (`Interrupted. Session saved under thread …`). Interrupt mid-turn may leave the last completed checkpoint slightly behind that input.

## LLM provider setup

Used for **empty-team bootstrap intake** (parsing free-form direction / pool replies). Other turns do not require a live LLM.

Set via `--provider` or `POKEMON_CHAMPIONS_LLM_PROVIDER` (default when both unset: `ollama`).

### `ollama` (default)

1. Install the optional extra: `uv sync --extra ollama` (needs `langchain-ollama`).
2. Run a local [Ollama](https://ollama.com) instance with a model available.
3. Set `BOOTSTRAP_OLLAMA_MODEL` to that model name.

If the model env is unset, startup warns: `BOOTSTRAP_OLLAMA_MODEL is unset; bootstrap intake parser not configured.` If the package is missing: `langchain-ollama unavailable: …`.

### `anthropic`

1. Install the optional extra: `uv sync --extra anthropic` (needs `langchain-anthropic`).
2. Set `BOOTSTRAP_ANTHROPIC_MODEL` to the model id.
3. Set `ANTHROPIC_API_KEY`.

Missing model or key produces a startup warning naming the unset variable. Missing package: `langchain-anthropic unavailable: …`.

### `none`

Disables the bootstrap parser. Startup warning:

> Bootstrap intake parser disabled (provider=none); empty-team free-form replies will fail-closed until a provider is configured.

Replying to the bootstrap prompt then surfaces `Bootstrap intake error: bootstrap intake parser is not configured`.

## Calc service setup

A separate local Node process that runs verified damage calculations (`@smogon/calc`). Matchup verification and team-wide coverage/threat analysis call it over HTTP. Without it, those paths degrade to labeled static estimates where possible (`single_locked`) or fail closed (`multi_locked`, ADR-029) rather than inventing numbers.

### How to start

From the repo root (Node deps installed via `npm install`):

```bash
npm start
```

That runs `tsx services/calc/server.ts`. A healthy process logs:

```text
calc-service listening on http://127.0.0.1:4173
```

Default bind is `127.0.0.1:4173` (override the port with `PORT`). The CLI probes `http://127.0.0.1:4173` by default.

The CLI does **not** auto-start the service (orphaned processes on crash/Ctrl+C, port conflicts, portability, and a possible future hosted deploy). Start it yourself before a session that needs calcs.

### If it is not running

At startup the CLI prints to stderr:

> Calc service not reachable at http://127.0.0.1:4173 — matchup verification and coverage/threat analysis will fail until it's started. Recommendations will degrade to labeled static estimates where possible, or fail closed.

Startup still succeeds. Observable mid-session behavior:

- **`single_locked`:** labeled-degraded path — lower-confidence / static estimates, discovery error banner when applicable
- **`multi_locked`:** fail-closed with a clear error (ADR-029); no candidate list is presented

## Meta commands

Typed at the `>` prompt (exact match after strip):

| Command | Effect |
|---------|--------|
| `:q` / `:quit` / `quit` | Exit the REPL. |
| `:thread` | Print the current thread id. |
| `:team` | Print locked roster members (`Team: (no locked members)` if none). |
| `:new` / `:reset` | Start a new session and print its first turn. |

Anything else is treated as an answer to the current pending question (if any).

## What a normal session looks like

Illustrative walkthrough (abbreviated; wording matches the real prompts):

1. **Start:** `python -m recommender --new`  
   You see the bootstrap question (“What direction or anchor… or say 'you pick.'”) and the footer about direction / pool / `you pick`.

2. **Answer bootstrap:** e.g. `rain with Pelipper` or `you pick`.  
   Next: numbered **candidate** options (species, role hints, evidence line) and  
   `Reply with a species name, 1/2/3, 'yes' for the default, or 'defer'.`

3. **Pick a candidate:** `1` or a species name.  
   You may get a **full build** to confirm (ability, item, nature, moves, spread) and  
   `Reply 'yes' to accept, or 'defer' to skip.`

4. **Confirm:** `yes` locks that slot.  
   Later slots may ask for a **completion preference** (`Prefer next slot orientation:` + numbered options) or more candidates / builds.

5. **Across the team:** each locked member shows up under `:team`. When the team is complete (or there is no pending question), you see the roster summary instead of a question prompt.

6. **Leave and return:** quit with `:q`. Later, `python -m recommender` (no flags) resumes the newest incomplete thread.

## When something goes wrong

Messages below are the real CLI / presentation text.

| What you see | Meaning |
|--------------|---------|
| `Didn't catch that.` | Your reply did not match the pending question; the same prompt is shown again underneath. |
| `No pending question to answer; start :new or wait for a prompt.` | There is nothing to answer right now (e.g. team complete / no presentation). Use `:new` to start over. |
| Evidence line ending in `(calc_unavailable)` or `(static_type_estimate, calc_unavailable)` | Matchup calc was unavailable; candidates may still appear with labeled static / degraded evidence. |
| `Discovery error [calc_unavailable] at …: … (retryable=…)` | Calc failed on a path that surfaces a structured discovery error (sometimes with no candidate list). |
| `Bootstrap intake error: bootstrap intake parser is not configured` | No working LLM provider for free-form bootstrap (see [LLM provider setup](#llm-provider-setup)). |
| `Bootstrap intake error: …` | Other intake / parse failure from the provider. |
| Startup warning about `BOOTSTRAP_OLLAMA_MODEL` / `BOOTSTRAP_ANTHROPIC_MODEL` / `ANTHROPIC_API_KEY` / missing langchain package | Parser was not configured; bootstrap free-form will fail until fixed. |
| `Calc service not reachable at http://127.0.0.1:4173 — …` | Calc service was down at CLI startup (see [Calc service setup](#calc-service-setup)); session still starts. |
| `Unknown thread: …` | `--thread` id is not in the checkpoint DB. |
| `Interrupted. Session saved under thread …` | Ctrl+C at the input prompt; session kept. |

List threads with `python -m recommender --list-threads` (optionally `--db …`) if you need to find an id to resume.
