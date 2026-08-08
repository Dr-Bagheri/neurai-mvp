"""Model Harness (D3): one interface every task module calls.

`complete(task, messages, constraints)` decides which model serves a request:

    1. No network / air-gapped / meeting or workspace local-only? → local
    2. Cloud not enabled globally?                                → local
    3. Cloud enabled + consented?                                 → OpenRouter
    4. Cloud call fails or times out?                             → automatic
       fallback to local, response re-tagged 🏠

The 🏠/☁️ badge is the `source` field on HarnessResult — it confirms a choice
made *before* the call, not an after-the-fact disclosure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from . import connectivity
from .backends import BackendError, BackendReply, OllamaBackend, OpenRouterBackend, ToolCall
from .chunking import SINGLE_SHOT_LIMIT, map_reduce

# Tasks that benefit from a frontier model when consent allows it.
CLOUD_WORTHY_TASKS = {"summarize", "chat_agent", "minutes", "formalize", "merge_notes", "translate"}

# D15 per-task routing: the heavy family (summaries/action items/minutes)
# rides cloud_heavy_model; everything else cloud-worthy rides cloud_chat_model.
HEAVY_TASKS = {"summarize", "minutes", "merge_notes"}


def _cloud_model_for(task: str) -> str:
    from neurai.config import get_config
    from neurai.db import get_db

    cfg = get_config()
    db = get_db()
    if task in HEAVY_TASKS:
        return db.get_setting("cloud_heavy_model") or cfg.cloud_heavy_model
    return db.get_setting("cloud_chat_model") or cfg.cloud_chat_model

MAX_TOOL_ITERATIONS = 6

# Executes a validated tool call; wired to the Skill Runtime at startup so the
# harness never imports skills directly (no cycle, and the runtime keeps sole
# authority over ACLs/audit — D7).
ToolExecutor = Callable[[ToolCall, Any], Awaitable[dict[str, Any]]]


@dataclass
class HarnessResult:
    text: str
    source: str            # "local" (🏠) | "cloud" (☁️)
    model: str
    fell_back: bool = False
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Constraints:
    allow_cloud: bool = False      # per-meeting/workspace consent flag (D3/D7 rule 4)
    max_tokens: int | None = None


class Harness:
    def __init__(self) -> None:
        self._local_factory: Callable[[], Any] = OllamaBackend
        self._cloud_factory: Callable[[], Any] = OpenRouterBackend

    # test hooks
    def set_backends(self, local: Callable[[], Any], cloud: Callable[[], Any]) -> None:
        self._local_factory = local
        self._cloud_factory = cloud

    # -- routing policy (the four rules, in order) ---------------------------

    def _use_cloud(self, task: str, constraints: Constraints) -> bool:
        if not constraints.allow_cloud:
            return False
        if not connectivity.cloud_allowed():
            return False
        if task not in CLOUD_WORTHY_TASKS:
            return False
        return connectivity.probe_cloud()

    async def _chat(
        self,
        task: str,
        messages: list[dict[str, Any]],
        constraints: Constraints,
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[BackendReply, str, bool]:
        """Returns (reply, source, fell_back)."""
        if self._use_cloud(task, constraints):
            try:
                # D15: pick the frontier model by task family; stub factories
                # in tests may not accept the kwarg
                try:
                    backend = self._cloud_factory(model=_cloud_model_for(task))
                except TypeError:
                    backend = self._cloud_factory()
                reply = await backend.chat(messages, tools=tools)
                return reply, "cloud", False
            except BackendError:
                # Rule 4: mid-task degradation is handled, not exceptional.
                pass
            backend = self._local_factory()
            reply = await backend.chat(messages, tools=tools)
            return reply, "local", True
        backend = self._local_factory()
        reply = await backend.chat(messages, tools=tools)
        return reply, "local", False

    # -- public API ----------------------------------------------------------

    async def complete(
        self,
        task: str,
        messages: list[dict[str, Any]],
        constraints: Constraints | None = None,
    ) -> HarnessResult:
        constraints = constraints or Constraints()
        reply, source, fell_back = await self._chat(task, messages, constraints)
        return HarnessResult(text=reply.text, source=source, model=reply.model, fell_back=fell_back)

    async def summarize_long(
        self,
        task: str,
        system_prompt: str,
        text: str,
        constraints: Constraints | None = None,
        reduce_prompt: str | None = None,
    ) -> HarnessResult:
        """Map-reduce over long inputs (D3). Cloud-routed calls get the whole
        text in one shot when it fits the frontier context; local goes through
        chunking."""
        constraints = constraints or Constraints()
        if self._use_cloud(task, constraints) or len(text) <= SINGLE_SHOT_LIMIT:
            return await self.complete(
                task,
                [{"role": "system", "content": system_prompt},
                 {"role": "user", "content": text}],
                constraints,
            )

        sources: set[str] = set()
        models: set[str] = set()
        fell_back = False

        async def _map(chunk: str, i: int, n: int) -> str:
            nonlocal fell_back
            reply, src, fb = await self._chat(
                task,
                [{"role": "system", "content": system_prompt},
                 {"role": "user", "content": f"(بخش {i + 1} از {n})\n\n{chunk}"}],
                constraints,
            )
            sources.add(src)
            models.add(reply.model)
            fell_back = fell_back or fb
            return reply.text

        async def _reduce(notes: list[str]) -> str:
            merged_prompt = reduce_prompt or (
                "یادداشت‌های بخش‌های مختلف یک جلسه در ادامه آمده است. "
                "آن‌ها را در یک خروجی منسجم و بدون تکرار ادغام کن."
            )
            reply, src, fb = await self._chat(
                task,
                [{"role": "system", "content": merged_prompt},
                 {"role": "user", "content": "\n\n---\n\n".join(notes)}],
                constraints,
            )
            sources.add(src)
            models.add(reply.model)
            return reply.text

        text_out = await map_reduce(text, _map, _reduce)
        source = "cloud" if sources == {"cloud"} else "local"
        return HarnessResult(
            text=text_out, source=source,
            model=", ".join(sorted(models)), fell_back=fell_back,
        )

    async def tool_loop(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        execute: ToolExecutor,
        context: Any,
        constraints: Constraints | None = None,
        max_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> HarnessResult:
        """Standard tool-use loop (D7): model proposes a call → Skill Runtime
        validates/executes → result goes back → repeat until a text answer.

        Consent propagates through the loop (D7 rule 4): the same constraints
        gate the driver model on every iteration, and `context` carries the
        user identity + consent into every skill execution.
        """
        constraints = constraints or Constraints()
        history = list(messages)
        trace: list[dict[str, Any]] = []
        any_fallback = False
        source = "local"
        model = ""

        for _ in range(max_iterations):
            reply, source, fb = await self._chat("chat_agent", history, constraints, tools=tools)
            any_fallback = any_fallback or fb
            model = reply.model
            if not reply.tool_calls:
                return HarnessResult(
                    text=reply.text, source=source, model=model,
                    fell_back=any_fallback, tool_trace=trace,
                )
            # provider-neutral turns — each backend converts to its own wire
            # format (_wire_messages), so a mid-loop cloud→local fallback
            # never sends a history shaped for the other provider
            history.append({
                "role": "assistant",
                "content": reply.text,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in reply.tool_calls
                ],
            })
            for tc in reply.tool_calls:
                result = await execute(tc, context)
                trace.append({"tool": tc.name, "arguments": tc.arguments, "result": result})
                import json as _json
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": _json.dumps(result, ensure_ascii=False),
                })

        return HarnessResult(
            text="نتیجه‌ی نهایی در تعداد مراحل مجاز به دست نیامد.",
            source=source, model=model, fell_back=any_fallback, tool_trace=trace,
        )


_harness: Harness | None = None


def get_harness() -> Harness:
    global _harness
    if _harness is None:
        _harness = Harness()
    return _harness


def set_harness(h: Harness | None) -> None:
    """Test hook."""
    global _harness
    _harness = h
