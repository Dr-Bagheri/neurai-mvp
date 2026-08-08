"""LLM backends: Ollama (local) and OpenRouter (cloud, consent-gated).

Both speak a common shape: chat(messages, tools) -> BackendReply. Tool calls
are normalized to {name, arguments(dict)} regardless of provider format.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from neurai.config import get_config
from neurai.db import get_db


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


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

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 300.0,
        options: dict[str, Any] | None = None,
    ) -> BackendReply:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
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

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 120.0,
        options: dict[str, Any] | None = None,
    ) -> BackendReply:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
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
        choice = data["choices"][0]["message"]
        calls = []
        for tc in choice.get("tool_calls") or []:
            args = tc["function"].get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            calls.append(ToolCall(name=tc["function"]["name"], arguments=args))
        return BackendReply(text=choice.get("content") or "", model=self.model, tool_calls=calls)
