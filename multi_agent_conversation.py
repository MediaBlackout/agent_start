from __future__ import annotations

"""Conversation management using OpenAI Responses API.

This module coordinates multiple agents and preserves chain-of-thought
continuity by tracking response IDs per agent. Conversation history is
kept in memory with optional persistence hooks.
"""

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests


@dataclass
class Message:
    """Represents a single message in a conversation."""

    role: str
    agent: str
    content: str
    timestamp: datetime
    response_id: Optional[str] = None
    reasoning: Optional[str] = None


class ConversationManager:
    """Handles multi-agent conversations with CoT continuity."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        """Initialize a conversation manager.

        Args:
            model: Target model for the Responses API.
            api_key: Optional API key for authentication.
            base_url: Base URL for the OpenAI API.
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.conversation_id = str(uuid.uuid4())
        self.messages: List[Message] = []
        self.last_response_ids: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Core messaging
    # ------------------------------------------------------------------
    def send(
        self,
        agent: str,
        content: str,
        *,
        role: str = "user",
        reasoning_effort: str = "medium",
        text_verbosity: str = "medium",
        tools: Optional[List[Dict[str, Any]]] = None,
        timeout: int = 30,
    ) -> Message:
        """Send content from an agent and capture the response.

        Args:
            agent: Agent name initiating the call.
            content: Message text.
            role: Sender role ("user" or "assistant").
            reasoning_effort: Requested reasoning effort.
            text_verbosity: Desired verbosity of text output.
            tools: Optional tool specifications for the request.
            timeout: Request timeout in seconds.

        Returns:
            The assistant's reply as a :class:`Message`.
        """
        user_msg = Message(
            role=role,
            agent=agent,
            content=content,
            timestamp=datetime.utcnow(),
        )
        self.messages.append(user_msg)

        payload: Dict[str, Any] = {
            "model": self.model,
            "input": content,
            "reasoning": {"effort": reasoning_effort},
            "text": {"verbosity": text_verbosity},
        }
        if tools:
            payload["tools"] = tools

        prev_id = self.last_response_ids.get(agent)
        if prev_id:
            payload["previous_response_id"] = prev_id

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            f"{self.base_url}/responses",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

        output = data.get("output", {})
        output_text = output.get("text", "")
        reasoning = output.get("reasoning")
        response_id = data.get("id")

        reply = Message(
            role="assistant",
            agent=agent,
            content=output_text,
            timestamp=datetime.utcnow(),
            response_id=response_id,
            reasoning=reasoning,
        )
        self.messages.append(reply)
        if response_id:
            self.last_response_ids[agent] = response_id
        return reply

    # ------------------------------------------------------------------
    # Conversation utilities
    # ------------------------------------------------------------------
    def handoff(self, from_agent: str, to_agent: str, context: str = "") -> None:
        """Record a handoff between agents.

        Args:
            from_agent: Agent passing control.
            to_agent: Agent receiving control.
            context: Optional instructions for the recipient.
        """
        prev_id = self.last_response_ids.get(from_agent)
        msg = Message(
            role="system",
            agent=to_agent,
            content=context,
            timestamp=datetime.utcnow(),
            response_id=prev_id,
        )
        self.messages.append(msg)

    def get_history(self) -> List[Message]:
        """Return a copy of the conversation history."""
        return list(self.messages)

    # ------------------------------------------------------------------
    # Persistence stubs
    # ------------------------------------------------------------------
    def save_to_file(self, path: str) -> None:
        """Persist the conversation history to JSON."""
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([asdict(m) for m in self.messages], fh, default=str, indent=2)

    def load_from_file(self, path: str) -> None:
        """Load conversation history from JSON."""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.messages = [
            Message(
                role=m["role"],
                agent=m["agent"],
                content=m["content"],
                timestamp=datetime.fromisoformat(m["timestamp"]),
                response_id=m.get("response_id"),
                reasoning=m.get("reasoning"),
            )
            for m in data
        ]

    def save_to_dynamodb(self, table: Any) -> None:  # pragma: no cover - stub
        """Placeholder for DynamoDB persistence."""
        raise NotImplementedError("Implement DynamoDB persistence if needed")


if __name__ == "__main__":  # pragma: no cover
    manager = ConversationManager(model="gpt-5", api_key="YOUR_API_KEY")
    manager.send(agent="Neo", content="What is the mission?", role="user")
    manager.handoff("Neo", "Trinity", "Neo greeted you")
    manager.send(agent="Trinity", content="The mission is on standby.")
    for message in manager.get_history():
        print(message)
