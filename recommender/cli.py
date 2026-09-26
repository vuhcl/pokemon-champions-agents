"""Interactive CLI REPL for the team-building recommender (ADR-010)."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Mapping

from recommender.calc_client import calc_startup_warning
from recommender.graph import compile_cli_graph
from recommender.llm_provider import resolve_llm_parsers
from recommender.present_text import (
    NO_PENDING_MESSAGE,
    NO_TEAM_REVIEW_MESSAGE,
    format_builds,
    format_no_pending,
    format_roster,
    format_team_review,
    format_turn,
    resolve_team_review_sections,
)
from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG
from recommender.session import (
    DEFAULT_FORMAT_ID,
    list_thread_summaries,
    mint_thread_id,
    resolve_thread_id,
    thread_config,
    thread_exists,
)


def invoke_user_text(graph, config, text: str) -> Mapping[str, Any]:
    """Stuff raw user text as pending_input. Propagates NotImplementedError."""
    return graph.invoke({"pending_input": text}, config)


# (aliases, takes_subarg, help_line) — handle_line and format_help share this.
_META_COMMANDS: tuple[tuple[tuple[str, ...], bool, str], ...] = (
    ((":q", ":quit", "quit"), False, "Exit the REPL."),
    ((":new", ":reset"), False, "Start a new session."),
    ((":thread",), False, "Print the current thread id."),
    ((":team",), False, "Print locked roster members."),
    ((":builds",), False, "Print locked-slot builds."),
    (
        (":review",),
        True,
        "Print cached team review (optional: threats, coverage, spofs).",
    ),
    ((":help",), False, "List CLI meta-commands."),
)


def format_help() -> str:
    return "\n".join(
        f"{' / '.join(aliases)}  {help_line}"
        for aliases, _, help_line in _META_COMMANDS
    )


def _match_meta(stripped: str) -> tuple[str, str] | None:
    """Return (canonical alias, subarg) or None. Exact match except takes_subarg rows."""
    for aliases, takes_subarg, _ in _META_COMMANDS:
        if takes_subarg:
            for alias in aliases:
                sub = _meta_subarg(stripped, alias)
                if sub is not None:
                    return aliases[0], sub
        elif stripped in aliases:
            return aliases[0], ""
    return None


def _meta_subarg(stripped: str, command: str) -> str | None:
    """If ``stripped`` is ``:command`` or ``:command <word>``, return sub-arg (``""`` if bare).

    Otherwise return None. Command match is case-insensitive; sub-arg is lowercased.
    """
    cmd = command.lower()
    lower = stripped.lower()
    if lower == cmd:
        return ""
    prefix = cmd + " "
    if lower.startswith(prefix):
        return stripped.split(None, 1)[1].strip().lower()
    return None


def _start_new_session(graph, format_id: str) -> tuple[str, dict, Mapping[str, Any]]:
    thread_id = mint_thread_id()
    config = thread_config(thread_id)
    state = graph.invoke({"format_id": format_id}, config)
    return thread_id, config, state


def handle_line(
    graph,
    config: dict,
    state: Mapping[str, Any],
    line: str,
    *,
    format_id: str,
    thread_id: str,
) -> tuple[Mapping[str, Any], dict, str, str | None, bool]:
    """Process one user line.

    Returns ``(state, config, thread_id, output_or_none, should_exit)``.
    """

    stripped = line.strip()
    if not stripped:
        return state, config, thread_id, None, False
    matched = _match_meta(stripped)
    if matched is not None:
        canonical, review_arg = matched
        if canonical == ":q":
            return state, config, thread_id, None, True
        if canonical == ":new":
            thread_id, config, state = _start_new_session(graph, format_id)
            return state, config, thread_id, format_turn(state), False
        if canonical == ":thread":
            return state, config, thread_id, thread_id, False
        if canonical == ":team":
            return state, config, thread_id, format_roster(state), False
        if canonical == ":builds":
            return state, config, thread_id, format_builds(state), False
        if canonical == ":review":
            review = state.get("last_team_review")
            if review is None:
                output = NO_TEAM_REVIEW_MESSAGE
            else:
                sects, hint = resolve_team_review_sections(review_arg)
                output = format_team_review(
                    review,
                    team_draft=state.get("team_draft") or [],
                    include_error=True,
                    sections=sects,
                    show_detail_hint=hint,
                )
            return state, config, thread_id, output, False
        if canonical == ":help":
            return state, config, thread_id, format_help(), False
        raise RuntimeError(f"unhandled meta command: {canonical}")
    if stripped.startswith(":"):
        cmd = stripped.split()[0]
        return (
            state,
            config,
            thread_id,
            f"Unknown command: {cmd}. Try :help.",
            False,
        )

    if (
        state.get("pending_presentation") is None
        and state.get("candidate_discovery_error") is not None
    ):
        return state, config, thread_id, format_no_pending(state), False

    try:
        state = invoke_user_text(graph, config, stripped)
    except NotImplementedError:
        return state, config, thread_id, NO_PENDING_MESSAGE, False
    except Exception:
        return state, config, thread_id, CLASSIFY_FAIL_USER_MSG, False

    # pending_response means unmatched only; full_build abandon emits build_abandoned.
    unmatched = state.get("turn_intent") == "pending_response"
    return state, config, thread_id, format_turn(state, unmatched=unmatched), False


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m recommender",
        description="Pokémon Champions team-building recommender (CLI)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--new", action="store_true", help="Start a new session")
    group.add_argument("--thread", metavar="ID", help="Resume an explicit thread id")
    parser.add_argument(
        "--list-threads",
        action="store_true",
        help="List known threads and exit",
    )
    parser.add_argument(
        "--format",
        default=DEFAULT_FORMAT_ID,
        dest="format_id",
        help=f"Format id for new sessions (default: {DEFAULT_FORMAT_ID})",
    )
    parser.add_argument(
        "--provider",
        choices=("ollama", "anthropic", "none"),
        default=None,
        help="Override POKEMON_CHAMPIONS_LLM_PROVIDER for this process",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Override checkpoint DB path (else POKEMON_CHAMPIONS_CHECKPOINT_DB / default)",
    )
    return parser.parse_args(argv)


def _print_thread_list(graph, saver) -> None:
    summaries = list_thread_summaries(graph, saver)
    if not summaries:
        print("(no threads)")
        return
    for row in summaries:
        pending = row.pending_kind or "-"
        flag = "incomplete" if row.incomplete else "complete"
        print(
            f"{row.thread_id}\t{row.phase}\tlocked={row.locked_count}\t"
            f"pending={pending}\t{flag}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    bootstrap_parser, turn_parser, warning = resolve_llm_parsers(args.provider)
    if warning:
        print(warning, file=sys.stderr)
    calc_warning = calc_startup_warning()
    if calc_warning:
        print(calc_warning, file=sys.stderr)

    graph, saver = compile_cli_graph(
        path=args.db,
        bootstrap_intake_parser=bootstrap_parser,
        turn_intent_parser=turn_parser,
    )
    try:
        if args.list_threads:
            _print_thread_list(graph, saver)
            return 0

        if args.thread:
            mode: str = "explicit"
            if not thread_exists(saver, args.thread):
                print(f"Unknown thread: {args.thread}", file=sys.stderr)
                return 2
        elif args.new:
            mode = "new"
        else:
            mode = "resume"

        summaries = list_thread_summaries(graph, saver)
        thread_id, is_new = resolve_thread_id(
            mode=mode,  # type: ignore[arg-type]
            explicit_id=args.thread,
            summaries=summaries,
        )
        config = thread_config(thread_id)

        if is_new:
            state = graph.invoke({"format_id": args.format_id}, config)
        else:
            state = graph.get_state(config).values

        print(format_turn(state))
        print(f"(thread {thread_id})", file=sys.stderr)

        while True:
            try:
                line = input("> ")
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                print(
                    f"\nInterrupted. Session saved under thread {thread_id}."
                )
                return 130

            try:
                state, config, thread_id, output, should_exit = handle_line(
                    graph,
                    config,
                    state,
                    line,
                    format_id=args.format_id,
                    thread_id=thread_id,
                )
            except KeyboardInterrupt:
                print(
                    "\nInterrupted mid-turn; last completed checkpoint may "
                    f"lag this input. Thread {thread_id}."
                )
                return 130

            if should_exit:
                return 0
            if output is not None:
                print(output)
    finally:
        saver.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
