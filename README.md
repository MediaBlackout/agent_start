# agent_start

This repository contains an example Orchestration Agent service. The orchestrator
coordinates multiple specialist agents to achieve high level goals. A small
FastAPI server exposes endpoints to trigger tasks and monitor progress.

Run the server with:

```bash
python app.py
```

Then POST to `/task` with a JSON body `{"goal": "your goal"}` to start.
