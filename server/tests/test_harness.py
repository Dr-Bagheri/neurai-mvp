"""Harness routing policy (D3): local by default, cloud only under consent,
automatic fallback when the cloud dies mid-task, map-reduce on long input."""
import json

import anyio
import pytest

from neurai.harness.backends import BackendError, BackendReply
from neurai.harness.harness import Constraints, Harness


class StubLocal:
    source = "local"
    calls = 0

    async def chat(self, messages, tools=None, timeout=None, options=None):
        StubLocal.calls += 1
        return BackendReply(text="local answer", model="stub-8b")


class StubCloud:
    source = "cloud"
    fail = False
    calls = 0

    async def chat(self, messages, tools=None, timeout=None, options=None):
        StubCloud.calls += 1
        if StubCloud.fail:
            raise BackendError("network cable pulled")
        return BackendReply(text="cloud answer", model="stub-frontier")


@pytest.fixture()
def harness(app_env, monkeypatch):
    from neurai.harness import connectivity

    StubLocal.calls = StubCloud.calls = 0
    StubCloud.fail = False
    h = Harness()
    h.set_backends(StubLocal, StubCloud)
    # pretend the network probe succeeds; policy gates still apply
    monkeypatch.setattr(connectivity, "probe_cloud", lambda *a, **k: True)
    return h


def _enable_cloud():
    from neurai.db import get_db

    db = get_db()
    # D15: server_mode is the one cloud switch (set directly — the REST path
    # is probe-gated, which is tested in test_online_mode.py)
    db.set_setting("server_mode", "online")
    db.set_setting("connectivity_profile", "auto")


def test_local_by_default(harness):
    result = anyio.run(harness.complete, "summarize", [{"role": "user", "content": "hi"}])
    assert result.source == "local"
    assert StubCloud.calls == 0


def test_no_consent_means_local_even_with_cloud_enabled(harness):
    _enable_cloud()
    result = anyio.run(
        harness.complete, "summarize", [{"role": "user", "content": "hi"}],
        Constraints(allow_cloud=False),
    )
    assert result.source == "local"
    assert StubCloud.calls == 0


def test_cloud_with_consent(harness):
    _enable_cloud()
    result = anyio.run(
        harness.complete, "summarize", [{"role": "user", "content": "hi"}],
        Constraints(allow_cloud=True),
    )
    assert result.source == "cloud"
    assert result.text == "cloud answer"


def test_air_gapped_never_touches_cloud(harness):
    from neurai.db import get_db

    _enable_cloud()
    get_db().set_setting("connectivity_profile", "air_gapped")
    result = anyio.run(
        harness.complete, "summarize", [{"role": "user", "content": "hi"}],
        Constraints(allow_cloud=True),
    )
    assert result.source == "local"
    assert StubCloud.calls == 0


def test_fallback_when_cloud_fails(harness):
    """The 'pull the network cable mid-task' behavior: cloud errors fall back
    to local and the response is re-tagged 🏠."""
    _enable_cloud()
    StubCloud.fail = True
    result = anyio.run(
        harness.complete, "summarize", [{"role": "user", "content": "hi"}],
        Constraints(allow_cloud=True),
    )
    assert result.source == "local"
    assert result.fell_back is True
    assert result.text == "local answer"


def test_map_reduce_on_long_input(harness):
    long_text = "این یک جمله آزمایشی است. " * 3000  # ≫ SINGLE_SHOT_LIMIT
    result = anyio.run(
        harness.summarize_long, "summarize", "خلاصه کن", long_text,
    )
    assert result.source == "local"
    # map calls (many chunks) + 1 reduce call
    assert StubLocal.calls > 2


def _openrouter_harness(monkeypatch, response_json, status_code=200):
    """Real OpenRouterBackend + real Harness, HTTP layer mocked; local side
    is the stub so fallback is observable."""
    import httpx as httpx_real

    import neurai.harness.backends as backends_mod
    from neurai.harness.backends import OpenRouterBackend
    from neurai.harness import connectivity
    from neurai.security import set_secret

    set_secret("openrouter_key", "sk-or-test")
    _enable_cloud()
    monkeypatch.setattr(connectivity, "probe_cloud", lambda *a, **k: True)

    def handler(request):
        return httpx_real.Response(status_code, json=response_json)

    real_client = httpx_real.AsyncClient

    def patched_client(**kwargs):
        kwargs["transport"] = httpx_real.MockTransport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(backends_mod.httpx, "AsyncClient", patched_client)

    h = Harness()
    h.set_backends(StubLocal, OpenRouterBackend)
    return h


def test_openrouter_200_error_body_falls_back(harness, monkeypatch):
    """0.1.7 regression: OpenRouter returns HTTP 200 with {"error": ...}
    (moderation/upstream failure) — must degrade to local (rule 4), never
    raise KeyError past the harness."""
    h = _openrouter_harness(monkeypatch, {"error": {"message": "moderation", "code": 403}})
    result = anyio.run(
        h.complete, "summarize", [{"role": "user", "content": "hi"}],
        Constraints(allow_cloud=True),
    )
    assert result.source == "local"
    assert result.fell_back is True
    assert result.text == "local answer"


def test_openrouter_malformed_body_falls_back(harness, monkeypatch):
    h = _openrouter_harness(monkeypatch, {"unexpected": "shape"})
    result = anyio.run(
        h.complete, "summarize", [{"role": "user", "content": "hi"}],
        Constraints(allow_cloud=True),
    )
    assert result.source == "local" and result.fell_back is True


def test_openrouter_happy_path_parses_tool_calls(harness, monkeypatch):
    h = _openrouter_harness(monkeypatch, {
        "choices": [{"message": {
            "content": "",
            "tool_calls": [{"function": {
                "name": "list_meetings",
                "arguments": "{\"limit\": 5}",   # OpenAI-style stringified JSON
            }}],
        }}],
    })

    async def run():
        reply, source, fell_back = await h._chat(
            "summarize", [{"role": "user", "content": "hi"}], Constraints(allow_cloud=True),
        )
        return reply, source, fell_back

    reply, source, fell_back = anyio.run(run)
    assert source == "cloud" and fell_back is False
    assert reply.tool_calls[0].name == "list_meetings"
    assert reply.tool_calls[0].arguments == {"limit": 5}  # parsed, not a string


def test_cloud_tool_loop_second_iteration_is_openai_compliant(harness, monkeypatch):
    """0.1.8: the payload OpenRouter receives on the SECOND loop iteration
    (first tool round-trip) must be OpenAI wire format — assistant turn with
    tool_calls[].id/type/function (STRING arguments), tool result with
    role:"tool" + matching tool_call_id. This is the request that used to
    400 and silently degrade every cloud agent loop to local."""
    import httpx as httpx_real

    import neurai.harness.backends as backends_mod
    from neurai.harness import connectivity
    from neurai.harness.backends import OpenRouterBackend
    from neurai.security import set_secret

    set_secret("openrouter_key", "sk-or-test")
    _enable_cloud()
    monkeypatch.setattr(connectivity, "probe_cloud", lambda *a, **k: True)

    requests_seen = []

    def handler(request):
        body = json.loads(request.content)
        requests_seen.append(body)
        if len(requests_seen) == 1:
            return httpx_real.Response(200, json={"choices": [{"message": {
                "content": None,
                "tool_calls": [{"id": "call_or_1", "type": "function", "function": {
                    "name": "list_meetings", "arguments": "{\"limit\": 3}"}}],
            }}]})
        return httpx_real.Response(200, json={"choices": [{"message": {
            "content": "سه جلسه دارید."}}]})

    real_client = httpx_real.AsyncClient

    def patched_client(**kwargs):
        kwargs["transport"] = httpx_real.MockTransport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(backends_mod.httpx, "AsyncClient", patched_client)

    h = Harness()
    h.set_backends(StubLocal, OpenRouterBackend)

    async def execute(tc, context):
        return {"meetings": [1, 2, 3]}

    result = anyio.run(
        h.tool_loop,
        [{"role": "user", "content": "جلساتم رو بشمار"}],
        [{"type": "function", "function": {"name": "list_meetings",
                                           "description": "", "parameters": {"type": "object"}}}],
        execute, None, Constraints(allow_cloud=True),
    )
    assert result.source == "cloud"
    assert result.fell_back is False          # the round-trip did NOT degrade
    assert result.text == "سه جلسه دارید."
    assert len(requests_seen) == 2

    second = requests_seen[1]["messages"]
    assistant = [m for m in second if m["role"] == "assistant" and m.get("tool_calls")]
    assert assistant, "assistant tool_call turn must be in the second payload"
    tc = assistant[-1]["tool_calls"][0]
    assert tc["id"] == "call_or_1"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "list_meetings"
    assert isinstance(tc["function"]["arguments"], str)      # STRING on the wire
    assert json.loads(tc["function"]["arguments"]) == {"limit": 3}

    tool_msgs = [m for m in second if m["role"] == "tool"]
    assert tool_msgs and tool_msgs[-1]["tool_call_id"] == "call_or_1"


def test_ollama_wire_format_from_neutral_history():
    """The same neutral history renders to Ollama's shape: {"function": ...}
    without id/type, tool results without tool_call_id."""
    from neurai.harness.backends import OllamaBackend

    neutral = [
        {"role": "user", "content": "سلام"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_x", "name": "list_meetings", "arguments": {"limit": 3}}]},
        {"role": "tool", "tool_call_id": "call_x", "name": "list_meetings",
         "content": "{\"meetings\": []}"},
    ]
    wire = OllamaBackend._wire_messages(neutral)
    assert wire[0] == neutral[0]
    assert wire[1]["tool_calls"] == [
        {"function": {"name": "list_meetings", "arguments": {"limit": 3}}}]
    assert "id" not in json.dumps(wire[1])
    assert wire[2] == {"role": "tool", "content": "{\"meetings\": []}"}


def test_split_text_boundaries():
    from neurai.harness.chunking import split_text

    text = "\n".join(f"پاراگراف {i} " + "الف" * 50 for i in range(400))
    chunks = split_text(text, chunk_chars=1000, overlap=100)
    assert all(len(c) <= 1000 for c in chunks)
    joined = "".join(chunks)
    assert "پاراگراف 399" in joined  # nothing lost at the tail
