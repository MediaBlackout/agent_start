"""Utilities for submitting batched requests to OpenAI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Dict, List

from openai import OpenAI


def build_jsonl(prompts: Iterable[str], prompt_id: str, version: str) -> List[str]:
    """Convert prompts into JSONL lines expected by the batch endpoint."""
    lines = []
    for message in prompts:
        req = {
            "prompt": {"id": prompt_id, "version": version},
            "input": message,
        }
        lines.append(json.dumps(req))
    return lines


def write_jsonl(lines: Iterable[str], file_path: str | Path) -> str:
    """Write JSONL lines to a file and return the path."""
    path = Path(file_path)
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    return str(path)


def create_batch(
    client: OpenAI,
    file_path: str | Path,
    *,
    endpoint: str = "/v1/responses",
    completion_window: str = "24h",
) -> object:
    """Upload a JSONL file and create a batch job."""
    with open(file_path, "rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")
    return client.batches.create(
        input_file_id=uploaded.id,
        endpoint=endpoint,
        completion_window=completion_window,
    )
