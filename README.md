# agent_start

This repository contains a small orchestration service demonstrating how multiple specialized agents can be coordinated to accomplish complex goals. The project uses FastAPI to expose endpoints for starting new tasks and monitoring progress.

## Running the Server

```bash
python app.py
```

Once running, trigger a task with:

```bash
curl -X POST http://localhost:8000/task -H 'Content-Type: application/json' -d '{"goal": "your goal"}'
```

Monitor progress via `GET /status`. Tasks that require confirmation can be approved or denied by POSTing to `/approve`.

See `docs/MEDIA_BLACKOUT_AI.md` for guidance on expanding this prototype into a production‑ready orchestration system for MEDIA BLACKOUT LLC.
