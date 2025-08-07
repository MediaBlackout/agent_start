from __future__ import annotations

"""Multi-agent conversation management module for MEDIA BLACKOUT LLC.

This module provides classes to coordinate conversations among multiple
agents using OpenAI's Responses API. It tracks conversation state,
handles chain-of-thought (CoT) continuity, and offers hooks for
persisting history to various backends.

Example:
    >>> manager = ConversationManager(model="gpt-5", api_key="sk-...")
    >>> manager.send(agent="Neo", content="Hello", role="user")
    >>> manager.handoff("Neo", "Trinity", "Neo greeted you")
    >>> reply = manager.send(agent="Trinity", content="How can I help?",
    ...                    role="assistant")
    >>> print(reply.content)
"""

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests


@dataclass
class Message:
    """Represents a single utterance in the conversation."""

    role: str
    agent: str
    content: str
    timestamp: datetime
    response_id: Optional[str] = None
    reasoning: Optional[str] = None


class ConversationManager:
    """Coordinates multi-agent conversations with CoT support."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        """Initialize the manager.

        Args:
            model: Model identifier for the Responses API.
            api_key: API key used for authentication.
            base_url: Base URL for the OpenAI API endpoint.
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
        """Send content on behalf of an agent and capture the response.

        Args:
            agent: Name of the agent sending the message.
            content: Message text.
            role: Role of the sender ("user" or "assistant").
            reasoning_effort: Desired reasoning effort level.
            text_verbosity: Output verbosity setting.
            tools: Optional tool definitions for the request.
            timeout: Request timeout in seconds.

        Returns:
            The assistant's reply as a :class:`Message` instance.
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

        output_text = data.get("output", {}).get("text", "")
        reasoning = data.get("output", {}).get("reasoning")
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
            from_agent: Agent passing the task.
            to_agent: Agent receiving the task.
            context: Optional context or instructions for the next agent.
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
        """Return the full conversation history."""
        return list(self.messages)

    # ------------------------------------------------------------------
    # Persistence stubs
    # ------------------------------------------------------------------
    def save_to_file(self, path: str) -> None:
        """Persist conversation history to a JSON file."""
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([asdict(m) for m in self.messages], fh, default=str, indent=2)

    def load_from_file(self, path: str) -> None:
        """Load conversation history from a JSON file."""
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
        """Stub for DynamoDB persistence."""
        raise NotImplementedError("Implement DynamoDB persistence as needed")


if __name__ == "__main__":
    # Minimal usage example demonstrating two agents.
    manager = ConversationManager(model="gpt-5", api_key="YOUR_API_KEY")
    manager.send(agent="Neo", content="What is the mission?", role="user")
    manager.handoff("Neo", "Trinity", "Neo asked about the mission")
    manager.send(agent="Trinity", content="The mission is on standby.")
    for message in manager.get_history():
        print(message)
