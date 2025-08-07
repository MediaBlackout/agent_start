from __future__ import annotations

"""Agent orchestration module for MEDIA BLACKOUT LLC.

This module simulates a multi-agent workflow using ULID-based message
tracking. It demonstrates the lifecycle Neo intake → Morpheus planning
→ Trinity execution → Neo closeout. All messages conform to the
specified schema and are stored for auditing.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import ulid


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def new_id() -> str:
    """Return a new ULID string."""
    return str(ulid.new())


def utc_now() -> str:
    """Return current UTC time in ISO8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Message:
    """Represents an audit log entry for agent communication."""

    response_id: str
    prev_response_id: Optional[str]
    parent_id: Optional[str]
    step_id: str
    agent: str
    timestamp: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class Orchestrator:
    """Central message bus coordinating agents and recording history."""

    def __init__(self) -> None:
        self.log: Dict[str, Dict[str, Any]] = {}

    # -------------------------- Logging ---------------------------------
    def record(self, message: Message) -> None:
        """Store a message in the log indexed by response_id."""
        self.log[message.response_id] = message.to_dict()

    def new_message(
        self,
        *,
        agent: str,
        step_id: str,
        payload: Dict[str, Any],
        prev_response_id: Optional[str],
        parent_id: Optional[str],
    ) -> Message:
        """Create and record a new message."""
        msg = Message(
            response_id=new_id(),
            prev_response_id=prev_response_id,
            parent_id=parent_id,
            step_id=step_id,
            agent=agent,
            timestamp=utc_now(),
            payload=payload,
        )
        self.record(msg)
        return msg

    def save_log(self, path: str) -> None:
        """Persist the conversation log to a JSON file."""
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.log, fh, indent=2)

    # ----------------------- Orchestration ------------------------------
    def run(self, request: str) -> Dict[str, Dict[str, Any]]:
        """Execute the full agent lifecycle for a request."""
        neo = Neo(self)
        morpheus = Morpheus(self)
        trinity = Trinity(self)

        intake_msg = neo.intake(request)
        plan_msg = morpheus.plan(request, intake_msg.response_id)

        try:
            results, last_id = trinity.execute(plan_msg)
        except RuntimeError as exc:  # Escalation path
            fail_payload = {"error": str(exc), "status": "failed"}
            last_msg = self.new_message(
                agent="Neo",
                step_id="neo.closeout.1",
                payload=fail_payload,
                prev_response_id=plan_msg.response_id,
                parent_id=plan_msg.response_id,
            )
            return self.log

        neo.closeout(last_id, results)
        return self.log


# ---------------------------------------------------------------------------
# Agent implementations
# ---------------------------------------------------------------------------

class Neo:
    """Handles intake and closeout steps."""

    def __init__(self, bus: Orchestrator) -> None:
        self.bus = bus

    def intake(self, request: str) -> Message:
        """Capture a user request and start a new run."""
        payload = {"request": request}
        msg = self.bus.new_message(
            agent="Neo",
            step_id="neo.intake.1",
            payload=payload,
            prev_response_id=None,
            parent_id=None,
        )
        return msg

    def closeout(self, prev_id: str, results: List[Dict[str, Any]]) -> Message:
        """Finalize the conversation and archive results."""
        payload = {"results": results, "status": "complete"}
        msg = self.bus.new_message(
            agent="Neo",
            step_id="neo.closeout.1",
            payload=payload,
            prev_response_id=prev_id,
            parent_id=prev_id,
        )
        return msg


class Morpheus:
    """Creates a plan of tasks for Trinity."""

    def __init__(self, bus: Orchestrator) -> None:
        self.bus = bus

    def plan(self, request: str, prev_id: str) -> Message:
        """Generate an execution plan for Trinity."""
        tasks = [
            {
                "task_id": "task-1",
                "description": "Gather matrix intel",
            },
            {
                "task_id": "task-2",
                "description": "Secure extraction route",
            },
        ]
        payload = {"plan": tasks, "original_request": request}
        msg = self.bus.new_message(
            agent="Morpheus",
            step_id="morpheus.plan.1",
            payload=payload,
            prev_response_id=prev_id,
            parent_id=prev_id,
        )
        return msg


class Trinity:
    """Executes tasks produced by Morpheus."""

    def __init__(self, bus: Orchestrator) -> None:
        self.bus = bus

    def execute(self, plan_msg: Message) -> Tuple[List[Dict[str, Any]], str]:
        """Run tasks with retry logic and return results and last response ID."""
        results: List[Dict[str, Any]] = []
        prev_id = plan_msg.response_id
        plan_id = plan_msg.response_id

        for index, task in enumerate(plan_msg.payload["plan"], 1):
            step_id = f"trinity.exec.{index}"
            attempt = 0
            while True:
                attempt += 1
                try:
                    if task["task_id"] == "task-2" and attempt == 1:
                        raise RuntimeError("temporary failure")
                    output = f"completed {task['description']}"
                    payload = {
                        "task_id": task["task_id"],
                        "status": "succeeded",
                        "output": output,
                        "attempt": attempt,
                    }
                    msg = self.bus.new_message(
                        agent="Trinity",
                        step_id=step_id if attempt == 1 else f"{step_id}.retry",
                        payload=payload,
                        prev_response_id=prev_id,
                        parent_id=plan_id,
                    )
                    results.append(payload)
                    prev_id = msg.response_id
                    break
                except Exception as exc:  # Retry path
                    fail_payload = {
                        "task_id": task["task_id"],
                        "status": "failed",
                        "error": str(exc),
                        "attempt": attempt,
                    }
                    fail_msg = self.bus.new_message(
                        agent="Trinity",
                        step_id=step_id,
                        payload=fail_payload,
                        prev_response_id=prev_id,
                        parent_id=plan_id,
                    )
                    prev_id = fail_msg.response_id
                    if attempt >= 2:
                        escalate_payload = {
                            "task_id": task["task_id"],
                            "status": "escalated",
                            "reason": "retries exhausted",
                        }
                        self.bus.new_message(
                            agent="Trinity",
                            step_id=f"{step_id}.escalate",
                            payload=escalate_payload,
                            prev_response_id=prev_id,
                            parent_id=plan_id,
                        )
                        raise RuntimeError(
                            f"Task {task['task_id']} escalation required"
                        )
        return results, prev_id


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    orchestrator = Orchestrator()
    conversation = orchestrator.run("Retrieve the keymaker")
    print(json.dumps(conversation, indent=2))
