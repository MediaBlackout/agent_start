"""Helpers for batching OpenAI chat completions."""

from __future__ import annotations

import os
from typing import List

try:
    import openai
except ImportError:  # pragma: no cover - optional
    openai = None
import structlog

logger = structlog.get_logger(__name__)


async def batch_chat_completion(
    prompts: List[str], model: str = "gpt-3.5-turbo"
) -> List[str]:
    """Send multiple prompts in a single OpenAI request."""
    if not os.getenv("OPENAI_API_KEY") or openai is None:
        logger.warning("OPENAI_API_KEY not set; returning stub responses")
        return [f"stub: {p}" for p in prompts]

    messages = [{"role": "user", "content": p} for p in prompts]
    resp = await openai.ChatCompletion.acreate(model=model, messages=messages)
    return [choice.message.content for choice in resp.choices]


async def _test() -> None:  # pragma: no cover - manual
    res = await batch_chat_completion(["hello"])
    assert isinstance(res, list)


if __name__ == "__main__":  # pragma: no cover - manual
    import asyncio

    asyncio.run(_test())
