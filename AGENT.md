# Repository Overview

This project contains multiple utilities and agents used by MEDIA BLACKOUT LLC.
The key components include:

- **Weather Agent** (`weather_agent.py`, `nws_client.py`, `data_processor.py`,
  `response_formatter.py`, `main.py`): provides weather data retrieval from the
  National Weather Service with a FastAPI server and optional WebSocket support.
- **Code Generation Agent** (`agent.py`, `agent-1.1.py`, `agent_zero.py`):
  utilities for generating code with OpenAI and committing it to GitHub,
  including email notifications via AWS SES.
- **CLI Utilities** (`todo_cli.py`, `use_prompt_response.py`): command line
  helpers for managing a todo list and interacting with saved OpenAI prompts.
- **Batching Support** (`openai_batch.py`, `use_prompt_response.py`): helper
  functions and CLI options to submit JSONL files of requests to OpenAI's
  Batches API for cost-effective processing.
- **Miscellaneous** (`TEST_1` directory, templates, timing helpers): various
  experiments and supporting scripts.

## Planned Next Steps

1. **Asynchronous Batch Results** – add utilities to poll for batch completion
   and collect generated outputs automatically.
2. **Integrate Batch Calls** – update existing agents to prefer the batching
   workflow for large volumes of prompts, reducing per-request cost.
3. **Testing and CI** – create unit tests for the batching pipeline and set up
   continuous integration to ensure reliability across all modules.
