import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).resolve().parents[1]))
from conversation_manager import Orchestrator


def test_run_generates_valid_chain():
    orch = Orchestrator()
    log = orch.run("Retrieve the keymaker")

    assert len(log) == 6

    entries = list(log.values())

    first = entries[0]
    assert first["prev_response_id"] is None
    assert first["agent"] == "Neo"
    assert first["step_id"].startswith("neo.intake")

    plan = entries[1]
    plan_id = plan["response_id"]

    prev = first
    for msg in entries[1:]:
        assert msg["prev_response_id"] == prev["response_id"]
        prev_time = datetime.fromisoformat(prev["timestamp"].replace("Z", "+00:00"))
        curr_time = datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))
        assert curr_time >= prev_time
        if msg["agent"] == "Trinity":
            assert msg["parent_id"] == plan_id
        else:
            assert msg["parent_id"] == msg["prev_response_id"]
        prev = msg

    last = entries[-1]
    assert last["agent"] == "Neo"
    assert last["step_id"].startswith("neo.closeout")
    assert last["payload"]["status"] == "complete"
