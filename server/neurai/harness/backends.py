"""LLM backends: Ollama (local) and OpenRouter (cloud, consent-gated).

Both speak a common shape: chat(messages, tools) -> BackendReply. Tool calls
are normalized to {name, arguments(dict), id} regardless of provider format.

Tool-loop histories are PROVIDER-NEUTRAL (built by the harness):

    {"role": "assistant", "content": ..., "tool_calls":
        [{"id", "name", "arguments"(dict)}]}
    {"role": "tool", "tool_call_id": ..., "name": ..., "content": ...}

Each backend converts that to its own wire format in _wire_messages() —
Ollama's {"function": {...}} shape vs OpenAI's tool_calls[].id/type/function
with STRING arguments and tool_call_id pairing. This is what lets a loop
fall back cloud→local mid-task (rule 4) without the history being wrong for
either provider.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from neurai.config import get_config
from neurai.db import get_db


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    # Pairing id for OpenAI-wire tool results; generated for providers that
    # don't supply one (Ollama) so the pairing survives provider switches.
    id: str = ""


@dataclass
class BackendReply:
    text: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class BackendError(Exception):
    pass


class OllamaBackend:
    """Local models via Ollama's /api/chat. Also serves embeddings (BGE-M3)."""

    source = "local"

    def __init__(self, base_url: str | None = None, model: str | None = None):
        cfg = get_config()
        self.base_url = (base_url or cfg.ollama_url).rstrip("/")
        db = get_db()
        self.model = model or db.get_setting("local_chat_model") or cfg.local_chat_model

    @staticmethod
    def _wire_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Neutral history → Ollama wire format."""
        out = []
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                out.append({
                    "role": "assistant",
                    "content": msg.get("content", "") or "",
                    "tool_calls": [
                        {"function": {"name": tc["name"], "arguments": tc["arguments"]}}
                        for tc in msg["tool_calls"]
                    ],
                })
            elif msg.get("role") == "tool":
                out.append({"role": "tool", "content": msg.get("content", "")})
            else:
                out.append(msg)
        return out

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: float | None = None,
        options: dict[str, Any] | None = None,
    ) -> BackendReply:
        cfg = get_config()
        if timeout is None:
            timeout = cfg.ollama_timeout
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._wire_messages(messages),
            "stream": False,
            "keep_alive": cfg.ollama_keep_alive,
        }
        if cfg.ollama_think.lower() in ("true", "false"):
            payload["think"] = cfg.ollama_think.lower() == "true"
        if tools:
            payload["tools"] = tools
        if options:
            payload["options"] = options
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(f"{self.base_url}/api/chat", json=payload)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            raise BackendError(f"Ollama unreachable or failed: {e}") from e
        msg = data.get("message", {})
        calls = [
            ToolCall(
                name=tc["function"]["name"],
                arguments=tc["function"].get("arguments") or {},
                # Ollama has no call ids — generate one so the tool-result
                # pairing survives a later switch to the OpenAI wire format
                id=f"call_{uuid.uuid4().hex[:12]}",
            )
            for tc in (msg.get("tool_calls") or [])
        ]
        return BackendReply(text=msg.get("content", "") or "", model=self.model, tool_calls=calls)

    async def embed(self, texts: list[str], model: str | None = None, timeout: float = 120.0) -> list[list[float]]:
        cfg = get_config()
        emb_model = model or get_db().get_setting("embed_model") or cfg.embed_model
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": emb_model, "input": texts},
                )
                r.raise_for_status()
                return r.json()["embeddings"]
        except httpx.HTTPError as e:
            raise BackendError(f"Ollama embed failed: {e}") from e


class OpenRouterBackend:
    """Frontier models via OpenRouter (OpenAI-compatible API). Only ever
    constructed after the consent policy has passed (D3)."""

    source = "cloud"

    def __init__(self, model: str | None = None):
        from neurai.security import get_secret

        cfg = get_config()
        db = get_db()
        self.base_url = cfg.openrouter_url.rstrip("/")
        # D8: the API key lives in the DPAPI-backed secret store, never in the
        # settings table or config files. Env var is a dev-only override.
        self.api_key = get_secret("openrouter_key") or cfg.openrouter_key
        self.model = model or db.get_setting("cloud_chat_model") or cfg.cloud_chat_model
        if not self.api_key:
            raise BackendError("OpenRouter API key not configured")

    @staticmethod
    def _wire_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Neutral history → OpenAI wire format: tool_calls carry
        id/type/function with STRING arguments; results are role:"tool" with
        the matching tool_call_id."""
        out = []
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                out.append({
                    "role": "assistant",
                    "content": msg.get("content") or None,
                    "tool_calls": [
                        {
                            "id": tc["id"] or f"call_{uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ],
                })
            elif msg.get("role") == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                })
            else:
                out.append(msg)
        return out

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 120.0,
        options: dict[str, Any] | None = None,
    ) -> BackendReply:
        payload: dict[str, Any] = {"model": self.model, "messages": self._wire_messages(messages)}
        if tools:
            payload["tools"] = tools
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            raise BackendError(f"OpenRouter failed: {e}") from e
        # OpenRouter can return HTTP 200 with an error body (moderation,
        # upstream provider failures) — that must degrade to local (rule 4),
        # not raise KeyError out of the harness.
        if "error" in data:
            raise BackendError(f"OpenRouter error: {data['error']}")
        try:
            choice = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise BackendError(f"OpenRouter returned unexpected response shape: {e}") from e
        calls = []
        for tc in choice.get("tool_calls") or []:
            args = tc["function"].get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            calls.append(ToolCall(
                name=tc["function"]["name"], arguments=args,
                id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
            ))
        return BackendReply(text=choice.get("content") or "", model=self.model, tool_calls=calls)
