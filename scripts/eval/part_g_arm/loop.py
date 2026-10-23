"""Headless arm loop: one user message in, one final message out, every tool call recorded.

LangGraph agent<->tools graph over ChatOllama with the arm's real tools (recommender.arm_tools).
The final text is the last model message's content only: the harness appends nothing to it, and the
model's reasoning (if any) is stored separately.
"""

from __future__ import annotations

import os
import time
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from recommender.arm_tools import TOOL_SPECS, ArmTools, dumps, to_jsonable
from recommender.calc_client import CalcClient

from scripts.eval.part_g_arm.config import ArmConfig


REASK = ("Before answering, call a lookup tool for the facts in the question, or call no_lookup_needed with a reason "
         "and a category if the request needs no lookup.")


class _State(TypedDict):
    messages: Annotated[list, add_messages]
    turns: int
    stop_reason: str
    tool_calls: list[dict[str, Any]]
    invalid_tool_calls: list[dict[str, Any]]
    reasoning: list[str]
    errors: list[str]
    reasked: bool
    rejected_first_turn: str


def build_llm(cfg: ArmConfig) -> ChatOllama:
    return ChatOllama(
        model=cfg.model, temperature=cfg.temperature, reasoning=cfg.think, num_ctx=cfg.num_ctx,
        num_predict=cfg.num_predict, client_kwargs={"timeout": cfg.call_timeout_s},
    )


class ArmLoop:
    def __init__(self, cfg: ArmConfig, *, llm: Any | None = None, tools: ArmTools | None = None) -> None:
        if cfg.fixed_now_utc:
            os.environ["RECOMMENDER_FIXED_NOW_UTC"] = cfg.fixed_now_utc
        self.cfg = cfg
        self.tools = tools or ArmTools(regulation=cfg.regulation, allow_live=cfg.allow_live, calc=CalcClient(cfg.calc_base_url))
        specs = [t for t in TOOL_SPECS if cfg.no_lookup_tool or t["function"]["name"] != "no_lookup_needed"]
        self.llm = (llm or build_llm(cfg)).bind_tools(specs)
        self.system = SystemMessage(cfg.prompt_text())
        self._deadline = 0.0
        g = StateGraph(_State)
        g.add_node("agent", self._agent)
        g.add_node("tools", self._run_tools)
        g.add_edge(START, "agent")
        g.add_conditional_edges("agent", self._route, {"tools": "tools", "agent": "agent", "end": END})
        g.add_edge("tools", "agent")
        self.graph = g.compile()

    def _agent(self, s: _State) -> dict[str, Any]:
        if time.monotonic() > self._deadline:
            return {"stop_reason": "item_timeout"}
        try:
            ai: AIMessage = self.llm.invoke([self.system, *s["messages"]])
        except Exception as exc:  # noqa: BLE001 - recorded, not raised
            return {"stop_reason": "model_error", "errors": [*s["errors"], f"{type(exc).__name__}: {exc}"]}
        if self.cfg.enforce_first_turn_tool and s["turns"] == 0 and not ai.tool_calls:
            # Reject once: the text is kept in the record but not shown to the model again.
            return {"turns": 1, "reasked": True, "rejected_first_turn": ai.content, "messages": [HumanMessage(REASK)]}
        out: dict[str, Any] = {"messages": [ai], "turns": s["turns"] + 1}
        if ai.additional_kwargs.get("reasoning_content"):
            out["reasoning"] = [*s["reasoning"], ai.additional_kwargs["reasoning_content"]]
        if ai.invalid_tool_calls:
            out["invalid_tool_calls"] = [*s["invalid_tool_calls"], *to_jsonable([dict(c) for c in ai.invalid_tool_calls])]
        return out

    def _route(self, s: _State) -> str:
        if s["stop_reason"] or not s["messages"]:
            return "end"
        if isinstance(s["messages"][-1], HumanMessage):
            return "agent"  # the re-ask after a rejected first turn
        if not isinstance(s["messages"][-1], AIMessage):
            return "end"
        if not s["messages"][-1].tool_calls:
            return "end"
        if s["turns"] >= self.cfg.max_turns:
            return "end"  # run_item reports it as max_turns: the last message still asks for a tool
        return "tools"

    def _run_tools(self, s: _State) -> dict[str, Any]:
        msgs, recs = [], list(s["tool_calls"])
        for call in s["messages"][-1].tool_calls:
            t0 = time.perf_counter()
            result = self.tools.call(call["name"], call["args"])
            recs.append({"name": call["name"], "args": call["args"], "result": to_jsonable(result),
                         "ok": result.get("status") != "error" and not result.get("error_kind"), "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
            msgs.append(ToolMessage(dumps(result), tool_call_id=call["id"]))
        return {"messages": msgs, "tool_calls": recs}

    def run_item(self, prompt: str) -> dict[str, Any]:
        t0 = time.monotonic()
        self._deadline = t0 + self.cfg.item_timeout_s
        init: _State = {"messages": [HumanMessage(prompt)], "turns": 0, "stop_reason": "", "tool_calls": [],
                        "invalid_tool_calls": [], "reasoning": [], "errors": [], "reasked": False, "rejected_first_turn": ""}
        final = self.graph.invoke(init, {"recursion_limit": 4 * self.cfg.max_turns + 10})
        last = final["messages"][-1]
        ended_on_tool_request = isinstance(last, AIMessage) and bool(last.tool_calls)
        stop = final["stop_reason"] or ("max_turns" if ended_on_tool_request else "final")
        text = last.content if isinstance(last, AIMessage) and not ended_on_tool_request and stop == "final" else ""
        return {"prompt": prompt, "final_text": text, "stop_reason": stop, "tool_calls": final["tool_calls"],
                "invalid_tool_calls": final["invalid_tool_calls"], "turns": final["turns"],
                "wall_s": round(time.monotonic() - t0, 2), "errors": final["errors"], "reasoning": final["reasoning"],
                "abstentions": [{"reason": c["args"].get("reason"), "category": c["args"].get("category")}
                                for c in final["tool_calls"] if c["name"] == "no_lookup_needed"],
                "enforcement": {"reasked": final["reasked"], "rejected_first_turn_text": final["rejected_first_turn"]}}
