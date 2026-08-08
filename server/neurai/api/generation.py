"""In-flight generation registry (D5 amendment: stop button).

Design: an explicit cancel endpoint rather than client-abort propagation —
deterministic across proxies and works from a different browser tab. The
chat route runs its LLM work inside an asyncio task registered here per
chat; POST /api/chats/{id}/cancel cancels that task, which cancels the
in-flight httpx request to Ollama/OpenRouter (the connection closes, Ollama
aborts generation and frees the CPU). The route distinguishes user-requested
cancellation from a client disconnect via the `user_cancelled` flag and
stores «متوقف شد» as the message state instead of an error.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class _Entry:
    task: asyncio.Task
    user_cancelled: bool = field(default=False)


class GenerationRegistry:
    def __init__(self) -> None:
        self._entries: dict[int, _Entry] = {}

    def register(self, chat_id: int, task: asyncio.Task) -> None:
        self._entries[chat_id] = _Entry(task)

    def unregister(self, chat_id: int) -> None:
        self._entries.pop(chat_id, None)

    def was_user_cancelled(self, chat_id: int) -> bool:
        entry = self._entries.get(chat_id)
        return entry.user_cancelled if entry else False

    def cancel(self, chat_id: int) -> bool:
        """Cancel the in-flight generation for a chat. True if one existed."""
        entry = self._entries.get(chat_id)
        if entry is None or entry.task.done():
            return False
        entry.user_cancelled = True
        entry.task.cancel()
        return True


_registry: GenerationRegistry | None = None


def get_generation_registry() -> GenerationRegistry:
    global _registry
    if _registry is None:
        _registry = GenerationRegistry()
    return _registry
