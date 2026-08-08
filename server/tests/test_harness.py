"""Harness routing policy (D3): local by default, cloud only under consent,
automatic fallback when the cloud dies mid-task, map-reduce on long input."""
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
    db.set_setting("cloud_enabled", "1")
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


def test_split_text_boundaries():
    from neurai.harness.chunking import split_text

    text = "\n".join(f"پاراگراف {i} " + "الف" * 50 for i in range(400))
    chunks = split_text(text, chunk_chars=1000, overlap=100)
    assert all(len(c) <= 1000 for c in chunks)
    joined = "".join(chunks)
    assert "پاراگراف 399" in joined  # nothing lost at the tail
