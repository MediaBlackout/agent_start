from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from orchestrator import Orchestrator

app = FastAPI(title="Orchestration Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()


@app.post("/task")
async def create_task(data: dict, background_tasks: BackgroundTasks):
    goal = data.get("goal")
    background_tasks.add_task(orchestrator.start, goal)
    return {"status": "accepted", "goal": goal}


@app.get("/status")
async def status():
    return {
        "state": orchestrator.state.name,
        "current_step": orchestrator.current_step,
        "log": orchestrator.log,
    }


@app.post("/approve")
async def approve(data: dict):
    decision = data.get("decision", "approved")
    orchestrator.approve(decision)
    return {"status": "recorded", "decision": decision}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
