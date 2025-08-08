import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
from multi_agent_conversation import ConversationManager


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_send_and_handoff(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(json)
        resp_id = f"resp{len(calls)}"
        data = {
            "id": resp_id,
            "output": {
                "text": f"reply {len(calls)}",
                "reasoning": f"reasoning {len(calls)}",
            },
        }
        return FakeResponse(data)

    monkeypatch.setattr("multi_agent_conversation.requests.post", fake_post)

    mgr = ConversationManager(model="gpt-test", api_key="test-key")
    reply1 = mgr.send(agent="Neo", content="hello")
    mgr.handoff("Neo", "Trinity", "context from Neo")
    reply2 = mgr.send(agent="Trinity", content="task")

    history = mgr.get_history()
    assert history[0].role == "user"
    assert history[1].response_id == "resp1"
    assert history[2].agent == "Trinity" and history[2].role == "system"
    assert history[3].agent == "Trinity" and history[3].role == "user"
    assert history[4].response_id == "resp2"
    assert mgr.last_response_ids == {"Neo": "resp1", "Trinity": "resp2"}
    assert reply1.reasoning == "reasoning 1"
    assert reply2.content == "reply 2"
