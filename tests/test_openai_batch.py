import asyncio
from types import SimpleNamespace

import agent_start.openai_batch as ob


class DummyChoice:
    def __init__(self, content: str) -> None:
        self.message = SimpleNamespace(content=content)


class DummyResp:
    def __init__(self, n: int) -> None:
        self.choices = [DummyChoice(f"resp {i}") for i in range(n)]


async def dummy_acreate(model, messages):
    return DummyResp(len(messages))


def test_batch_completion(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(ob.openai.ChatCompletion, "acreate", dummy_acreate)
    out = asyncio.run(ob.batch_chat_completion(["a", "b"]))
    assert out == ["resp 0", "resp 1"]
