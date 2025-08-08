# agent_start

This repository contains a ULID-based agent orchestration demo for MEDIA BLACKOUT LLC.
It simulates a multi-agent workflow demonstrating Neo intake, Morpheus planning,
Trinity execution with retry/escalation, and Neo closeout. All messages are stored
with full traceability.

## Installation

```bash
pip install -r requirements.txt
```

## Running the demo

```bash
python conversation_manager.py
```

The script prints the JSON conversation log for auditing.

## OpenAI Responses conversation manager

The `multi_agent_conversation.py` module interfaces with OpenAI's
Responses API to coordinate multiple agents while preserving
chain-of-thought continuity.

```bash
python multi_agent_conversation.py  # requires API key
```

## Testing

Run unit tests with:

```bash
pytest
```
